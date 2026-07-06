"""
revision_climatica.py
======================
Revisa el pronóstico (3 días) de los sectores de obra en la IX Región y
zonas aledañas, y dispara un correo de alerta si detecta condiciones
adversas (lluvia intensa, viento fuerte/huracanado, nieve, heladas/hielo,
calor extremo o radiación UV alta) con al menos 24 h de anticipación.

Fuente de datos: Open-Meteo (gratis, sin API key, https://open-meteo.com).
No existe una API pública estable de SENAPRED/DMC para alertas tempranas
por comuna (verificado en la sesión donde se creó este script), por lo
que los umbrales de UMBRALES son una aproximación a los criterios
públicos de "Aviso Meteorológico" de DMC. AJUSTAR estos valores si el
usuario cuenta con los umbrales oficiales vigentes exactos.

Destinatarios: personas marcadas con `alerta_climatica: true` en
Firebase (`personal_global` y/o `personal_obra`), configurable desde el
botón "Personal" del dashboard.

Regla de envío (misma política que el resto del sistema): las pruebas
manuales NO disparan correos reales salvo que se fuerce explícitamente,
para evitar spam a destinatarios reales en cada prueba.

Modo local : credenciales Gmail desde gmail_config.json
Modo cloud : credenciales desde env vars GMAIL_EMAIL, GMAIL_APP_PASSWORD

Uso standalone:
    python revision_climatica.py                  # dry-run (no envía)
    python revision_climatica.py --forzar-envio    # envía si hay alertas nuevas
"""

import json
import os
import re
import smtplib
import sys
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

FIREBASE = os.environ.get(
    "FIREBASE_URL", "https://scraices-dashboard-default-rtdb.firebaseio.com"
)
_LOCAL_GMAIL = Path(r"C:\Users\rodri\.claude\gmail_config.json")

# ─── SECTORES A MONITOREAR ─────────────────────────────────────────────────
# Coordenadas aproximadas; las localidades menores se intentan resolver por
# geocoding en tiempo de ejecución (ver geocodificar_sector) y estas quedan
# como respaldo si el geocoder no las encuentra.
SECTORES_FALLBACK = {
    "Villarrica":        (-39.2827, -72.2247),
    "Freire":            (-38.9636, -72.6202),
    "Gorbea":            (-39.0972, -72.6772),
    "Panguipulli":       (-39.6389, -72.3339),
    "Licanray":          (-39.4747, -72.0761),
    "Pucón":             (-39.2822, -71.9598),
    "Temuco":            (-38.7359, -72.5904),
    "Teodoro Schmidt":   (-39.0192, -73.0186),
    "Hualpín":           (-39.091339, -73.1814935),   # coordenada exacta entregada por el usuario
    "Barros Arana":      (-38.6667, -72.7333),
    "Queule":            (-39.3903, -73.2078),
    "Porma":             (-39.1209504, -73.2706258),  # coordenada exacta entregada por el usuario
    "Perquenco":         (-38.4219927, -72.3888254),  # coordenada exacta entregada por el usuario
    "Victoria":          (-38.2351416, -72.3470849),  # coordenada exacta entregada por el usuario
    "Lautaro":           (-38.5353968, -72.4387979),  # coordenada exacta entregada por el usuario
    "Padre Las Casas":   (-38.7720711, -72.589863),   # coordenada exacta entregada por el usuario
    "Cunco":             (-38.9324682, -72.0362298),  # coordenada exacta entregada por el usuario
}

# ─── UMBRALES DE CONDICIÓN ADVERSA (ajustables — ver nota en el docstring) ──
UMBRALES = {
    "lluvia_intensa": {"var": "precipitation_sum",  "op": ">=", "valor": 30, "unidad": "mm/24h", "label": "Lluvia intensa"},
    "viento_fuerte":  {"var": "wind_gusts_10m_max",  "op": ">=", "valor": 60, "unidad": "km/h",   "label": "Viento fuerte / huracanado"},
    "nieve":          {"var": "snowfall_sum",        "op": ">=", "valor": 5,  "unidad": "cm/24h", "label": "Nieve"},
    "helada":         {"var": "temperature_2m_min",  "op": "<=", "valor": 0,  "unidad": "°C",     "label": "Helada / riesgo de hielo"},
    "calor_extremo":  {"var": "temperature_2m_max",  "op": ">=", "valor": 32, "unidad": "°C",     "label": "Calor extremo"},
    "radiacion_uv":   {"var": "uv_index_max",         "op": ">=", "valor": 6,  "unidad": "índice UV", "label": "Radiación UV alta"},
}

DIAS_ANTICIPACION = (1, 2)  # índices del pronóstico diario: mañana y pasado mañana (>= 24h)


def is_cloud() -> bool:
    return bool(os.environ.get("GOOGLE_REFRESH_TOKEN") or os.environ.get("GITHUB_ACTIONS"))


def _slug(nombre: str) -> str:
    nfd = unicodedata.normalize("NFD", nombre)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w]", "_", ascii_str).strip("_")


def geocodificar_sector(nombre: str):
    """Resuelve lat/lon vía Open-Meteo Geocoding API. None si no encuentra.

    Se pide un `count` amplio y se filtra por country_code=CL en el cliente,
    porque la API aplica el filtro countryCode DESPUÉS de truncar a `count`
    resultados globales — con count bajo, filtrar en el servidor deja 0
    resultados aunque exista una localidad chilena con ese nombre.
    """
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": nombre, "count": 10, "language": "es"},
            timeout=15,
        )
        r.raise_for_status()
        resultados = [x for x in (r.json().get("results") or []) if x.get("country_code") == "CL"]
        if resultados:
            return resultados[0]["latitude"], resultados[0]["longitude"]
    except Exception as e:
        print(f"  [geocoding] {nombre}: {e}")
    return None


# Alias de búsqueda para geocoding cuando el nombre usado en el dashboard
# difiere del nombre registrado en la base de datos de localidades (GeoNames).
GEOCODE_ALIAS = {
    "Licanray": "Lican Ray",
}


def construir_sectores() -> dict:
    sectores = {}
    for nombre, fallback in SECTORES_FALLBACK.items():
        coords = geocodificar_sector(GEOCODE_ALIAS.get(nombre, nombre))
        if coords:
            sectores[nombre] = coords
        else:
            print(f"  [info] '{nombre}' no está en la base de geocoding — usando coordenada de respaldo ya confirmada.")
            sectores[nombre] = fallback
    return sectores


def fetch_forecast(lat: float, lon: float) -> dict:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "snowfall_sum,windspeed_10m_max,wind_gusts_10m_max,uv_index_max",
            "forecast_days": 3,
            "timezone": "America/Santiago",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["daily"]


def evaluar_sector(nombre: str, daily: dict) -> list:
    eventos = []
    fechas = daily.get("time", [])
    for i in DIAS_ANTICIPACION:
        if i >= len(fechas):
            continue
        fecha = fechas[i]
        for tipo, u in UMBRALES.items():
            valores = daily.get(u["var"]) or []
            if i >= len(valores) or valores[i] is None:
                continue
            valor = valores[i]
            cumple = valor >= u["valor"] if u["op"] == ">=" else valor <= u["valor"]
            if cumple:
                eventos.append({
                    "sector": nombre, "fecha": fecha, "tipo": tipo,
                    "label": u["label"], "valor": valor, "unidad": u["unidad"],
                })
    return eventos


def _fetch_firebase(endpoint: str) -> dict:
    r = requests.get(f"{FIREBASE}/{endpoint}.json", timeout=30)
    return r.json() or {}


def cargar_estado() -> dict:
    return _fetch_firebase("alerta_climatica_estado")


def guardar_estado(estado: dict) -> None:
    requests.put(f"{FIREBASE}/alerta_climatica_estado.json", json=estado, timeout=20)


def filtrar_nuevos(eventos: list, estado: dict):
    """Un evento es 'nuevo' si la fecha del evento cambió respecto a la última
    notificación registrada para ese sector+tipo (evita reenviar el mismo
    aviso en cada corrida mientras el pronóstico no cambie)."""
    nuevos = []
    estado_actualizado = dict(estado)
    for ev in eventos:
        clave = f"{_slug(ev['sector'])}_{ev['tipo']}"
        if estado.get(clave) != ev["fecha"]:
            nuevos.append(ev)
        estado_actualizado[clave] = ev["fecha"]
    return nuevos, estado_actualizado


def obtener_destinatarios() -> dict:
    """correo → nombre, para todas las personas con alerta_climatica=true
    en personal_global o personal_obra (deduplicado por correo)."""
    destinatarios = {}

    pg = _fetch_firebase("personal_global")
    for _, p in (pg or {}).items():
        if isinstance(p, dict) and p.get("alerta_climatica") and p.get("correo", "").strip():
            destinatarios[p["correo"].strip()] = p.get("nombre", "")

    po = _fetch_firebase("personal_obra")
    for _, personas in (po or {}).items():
        if not isinstance(personas, dict):
            continue
        for _, p in personas.items():
            if isinstance(p, dict) and p.get("alerta_climatica") and p.get("correo", "").strip():
                destinatarios[p["correo"].strip()] = p.get("nombre", "")

    return destinatarios


def _get_gmail():
    if os.environ.get("GMAIL_APP_PASSWORD"):
        return os.environ["GMAIL_EMAIL"], os.environ["GMAIL_APP_PASSWORD"]
    cfg = json.loads(_LOCAL_GMAIL.read_text())
    return cfg["email"], cfg["app_password"]


def _recomendacion_temporada(fecha=None) -> str:
    """Texto de recomendaciones según la temporada del año (hemisferio sur).
    Otoño/invierno (marzo-agosto): foco en viento/lluvia/heladas y caminos.
    Primavera/verano (septiembre-febrero): foco en exposición solar/calor."""
    from datetime import date as _date

    mes = (fecha or _date.today()).month
    if mes in (3, 4, 5, 6, 7, 8):
        return (
            "Procurar los resguardos respectivos referente a velocidad de circulación y evaluación de las condiciones del camino.\n\n"
            "Evaluar según las condiciones climáticas, la necesidad de suspender y reorganizar faenas que se vean complicadas de ejecutar "
            "en las viviendas producto de las condiciones climáticas de vientos/lluvias/heladas.\n\n"
            "Se agradece su máxima atención a las condiciones imperantes y evaluación de riesgos asociados."
        )
    return (
        "Procurar los resguardos respectivos referente a la exposición al sol, considerar el uso de ropa de manga larga, "
        "coletos protectores y lentes oscuros. Cuidar la hidratación permanente y coordinar los trabajos al exterior en horas de menor calor.\n\n"
        "Se agradece su máxima atención a las condiciones imperantes y evaluación de riesgos asociados."
    )


def _cuerpo_correo(nombre: str, eventos: list) -> str:
    por_sector = {}
    for ev in sorted(eventos, key=lambda e: (e["sector"], e["fecha"])):
        por_sector.setdefault(ev["sector"], []).append(ev)

    bloques = []
    for sector, evs in por_sector.items():
        lineas = "\n".join(
            f"    - {e['fecha']}: {e['label']} ({e['valor']} {e['unidad']})" for e in evs
        )
        bloques.append(f"  {sector}:\n{lineas}")

    detalle = "\n\n".join(bloques)

    return f"""Estimado/a {nombre},

Se detectaron condiciones climáticas adversas en los próximos días en los siguientes sectores de obra:

{detalle}

{_recomendacion_temporada()}

Alerta generada automáticamente a partir del pronóstico de Open-Meteo — Panel de Control SG Raíces.
Los umbrales usados son una referencia aproximada a criterios públicos de aviso meteorológico; ante duda, verificar con el boletín oficial de la Dirección Meteorológica de Chile (DMC) / SENAPRED.
"""


# Colores/íconos por tipo de condición (mismo lenguaje visual que el correo de
# resumen semanal de ejecutar_informes_cloud.py: fondo #f1efe8, header #0b0b0b,
# acento raices-red #8B2332).
_TIPO_ESTILO = {
    "lluvia_intensa": ("#eaf1fb", "#1d4ed8", "🌧️"),
    "viento_fuerte":  ("#fff2e6", "#c2410c", "💨"),
    "nieve":          ("#e6f7fb", "#0e7490", "❄️"),
    "helada":         ("#eef0fc", "#4338ca", "🧊"),
    "calor_extremo":  ("#fdeaea", "#b91c1c", "🔥"),
    "radiacion_uv":   ("#fef9e0", "#a16207", "☀️"),
}


def _cuerpo_correo_html(nombre: str, eventos: list, fecha_display: str) -> str:
    por_sector = {}
    for ev in sorted(eventos, key=lambda e: (e["sector"], e["fecha"])):
        por_sector.setdefault(ev["sector"], []).append(ev)

    n_sectores = len(por_sector)
    n_eventos = len(eventos)

    tarjetas_html = ""
    for sector, evs in por_sector.items():
        pills = ""
        for e in evs:
            bg, color, icono = _TIPO_ESTILO.get(e["tipo"], ("#f1efe8", "#52514e", "⚠️"))
            pills += (
                f'<span style="display:inline-block;background:{bg};color:{color};'
                f'border-radius:6px;padding:3px 9px;font-size:11px;font-weight:600;'
                f'margin:3px 6px 3px 0;">{icono} {e["label"]} · {e["fecha"]} · {e["valor"]} {e["unidad"]}</span>'
            )
        tarjetas_html += f"""
        <tr><td style="padding:6px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;
            border-radius:0 6px 6px 0;border:1px solid #e1e0d9;border-left:4px solid #8B2332;">
            <tr><td style="padding:12px 16px;">
              <div style="font-size:14px;font-weight:700;color:#0b0b0b;margin-bottom:6px;">📍 {sector}</div>
              <div>{pills}</div>
            </td></tr>
          </table>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1efe8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1efe8;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:#0b0b0b;border-radius:10px 10px 0 0;padding:28px 32px;">
    <div style="font-size:11px;font-weight:600;color:#898781;letter-spacing:.1em;
      text-transform:uppercase;margin-bottom:6px;">SG Raíces · Control de obras</div>
    <div style="font-size:22px;font-weight:700;color:#ffffff;">⚠️ Alerta Climática</div>
    <div style="font-size:13px;color:#c3c2b7;margin-top:4px;">
      {n_sectores} sector(es) afectados &nbsp;·&nbsp; {fecha_display}
    </div>
  </td></tr>

  <!-- KPI ROW -->
  <tr><td style="background:#ffffff;padding:0 32px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
      <tr>
        <td width="33%" style="text-align:center;padding:16px 8px;background:#fdeaea;border-radius:8px;">
          <div style="font-size:32px;font-weight:700;color:#8B2332;">{n_sectores}</div>
          <div style="font-size:11px;color:#8B2332;font-weight:600;text-transform:uppercase;
            letter-spacing:.05em;">Sectores</div>
        </td>
        <td width="6px"></td>
        <td width="33%" style="text-align:center;padding:16px 8px;background:#f1efe8;border-radius:8px;">
          <div style="font-size:32px;font-weight:700;color:#0b0b0b;">{n_eventos}</div>
          <div style="font-size:11px;color:#5f5e5a;font-weight:600;text-transform:uppercase;
            letter-spacing:.05em;">Condiciones</div>
        </td>
        <td width="6px"></td>
        <td width="33%" style="text-align:center;padding:16px 8px;background:#fff2e6;border-radius:8px;">
          <div style="font-size:22px;font-weight:700;color:#c2410c;">24-48h</div>
          <div style="font-size:11px;color:#c2410c;font-weight:600;text-transform:uppercase;
            letter-spacing:.05em;">Anticipación</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- SALUDO -->
  <tr><td style="background:#ffffff;padding:0 32px;">
    <div style="font-size:14px;color:#0b0b0b;">Estimado/a <strong>{nombre}</strong>,</div>
    <div style="font-size:13px;color:#5f5e5a;margin-top:6px;">
      Se detectaron condiciones climáticas adversas en los próximos días en los siguientes sectores de obra:
    </div>
    <div style="height:1px;background:#e1e0d9;margin:16px 0 4px;"></div>
  </td></tr>

  <!-- SECTORES -->
  <tr><td style="background:#ffffff;padding:8px 32px 4px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      {tarjetas_html}
    </table>
  </td></tr>

  <!-- RECOMENDACIONES -->
  <tr><td style="background:#ffffff;padding:8px 32px 28px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff8e6;
      border:1px solid #f0dfa8;border-radius:8px;">
      <tr><td style="padding:16px 18px;">
        <div style="font-size:13px;font-weight:700;color:#8a6d1a;margin-bottom:8px;">⚠️ Recomendaciones</div>
        <div style="font-size:13px;color:#5f4f16;line-height:1.6;">
          {_recomendacion_temporada().replace(chr(10) + chr(10), "<br><br>")}
        </div>
      </td></tr>
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0b0b0b;border-radius:0 0 10px 10px;padding:16px 32px;text-align:center;">
    <div style="font-size:11px;color:#898781;">
      Alerta generada automáticamente a partir del pronóstico de Open-Meteo · Panel de Control SG Raíces
    </div>
    <div style="font-size:10px;color:#5f5e5a;margin-top:4px;">
      Umbrales de referencia — ante duda, verificar con el boletín oficial DMC / SENAPRED.
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def enviar_alerta(remitente: str, app_pw: str, correo_dest: str, nombre: str, eventos: list, fecha_display: str):
    sectores_n = len({e["sector"] for e in eventos})
    asunto = f"⚠️ Alerta Climática — {sectores_n} sector(es) — {fecha_display}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"SG Raices Control <{remitente}>"
    msg["To"] = correo_dest
    msg["Subject"] = asunto
    msg.attach(MIMEText(_cuerpo_correo(nombre, eventos), "plain", "utf-8"))
    msg.attach(MIMEText(_cuerpo_correo_html(nombre, eventos, fecha_display), "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(remitente, app_pw)
        server.sendmail(remitente, [correo_dest], msg.as_string())


def main(forzar_envio: bool = None, solo_para: str = None):
    from datetime import date

    if forzar_envio is None:
        forzar_envio = os.environ.get("FORZAR_ENVIO") == "1"

    print("Resolviendo sectores...")
    sectores = construir_sectores()

    print("\nConsultando pronóstico (Open-Meteo, 3 días)...")
    eventos_totales = []
    for nombre, (lat, lon) in sectores.items():
        try:
            daily = fetch_forecast(lat, lon)
            eventos_totales.extend(evaluar_sector(nombre, daily))
        except Exception as e:
            print(f"  [error] {nombre}: {e}")

    print(f"\n{'='*60}")
    if eventos_totales:
        print(f"Condiciones adversas detectadas (próximos 1-2 días): {len(eventos_totales)}")
        for ev in eventos_totales:
            print(f"  {ev['sector']:<18} {ev['fecha']}  {ev['label']:<30} {ev['valor']} {ev['unidad']}")
    else:
        print("Sin condiciones adversas detectadas en el pronóstico.")
    print(f"{'='*60}")

    if solo_para:
        # Modo prueba individual: no consulta ni actualiza el estado de
        # deduplicación — así una prueba a una sola persona no "consume"
        # el aviso que le corresponde al resto del equipo en la corrida real.
        if not eventos_totales:
            print("\n[PRUEBA] Sin condiciones adversas — no se envía correo de prueba.")
            return
        nombre_destino = None
        for correo, nombre in obtener_destinatarios().items():
            if correo.lower() == solo_para.lower():
                nombre_destino = nombre
                break
        destinatarios = {solo_para: nombre_destino or solo_para}
        nuevos = eventos_totales
        print(f"\n[PRUEBA] Enviando SOLO a: {solo_para}")
    else:
        estado = cargar_estado()
        nuevos, estado_actualizado = filtrar_nuevos(eventos_totales, estado)

        if not nuevos:
            print("\nNo hay eventos nuevos respecto a la última notificación — no se envía correo.")
            return

        print(f"\nEventos NUEVOS a notificar: {len(nuevos)}")
        destinatarios = obtener_destinatarios()
        if not destinatarios:
            print("Hay eventos nuevos pero no hay destinatarios con 'alerta_climatica' activado en el dashboard.")
            return

    fecha_display = date.today().strftime("%d.%m.%Y")

    if not forzar_envio:
        print(f"\n[DRY-RUN] Se enviaría alerta a {len(destinatarios)} destinatario(s):")
        for correo, nombre in destinatarios.items():
            print(f"  {nombre:<28} {correo}")
        print("(No se envían correos reales fuera del cron programado o sin --forzar-envio)")
        return

    remitente, app_pw = _get_gmail()
    errores = []
    for correo, nombre in destinatarios.items():
        try:
            print(f"  Enviando a {nombre} ({correo})...", end=" ")
            enviar_alerta(remitente, app_pw, correo, nombre or correo, nuevos, fecha_display)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            errores.append((correo, str(e)))

    if not solo_para:
        guardar_estado(estado_actualizado)
    print(f"\nEnvíos completados: {len(destinatarios) - len(errores)} OK, {len(errores)} errores")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    forzar = "--forzar-envio" in sys.argv
    solo_para_arg = None
    if "--solo-para" in sys.argv:
        idx = sys.argv.index("--solo-para")
        if idx + 1 < len(sys.argv):
            solo_para_arg = sys.argv[idx + 1]
    main(forzar_envio=forzar or None, solo_para=solo_para_arg)

"""
revision_climatica.py
======================
Revisa el pronóstico (3 días) de los sectores de obra en la IX Región y
zonas aledañas, y dispara un correo de alerta si detecta condiciones
adversas (lluvia intensa, viento fuerte/huracanado, nieve, heladas/hielo
o calor extremo) con al menos 24 h de anticipación.

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
    "Hualpín":           (-38.9333, -73.1667),
    "Barros Arana":      (-38.6667, -72.7333),
    "Queule":            (-39.3903, -73.2078),
    "Porma":             (-39.2827, -72.2247),  # sin geocodificar — usa Villarrica como aproximación, CONFIRMAR con el usuario
}

# ─── UMBRALES DE CONDICIÓN ADVERSA (ajustables — ver nota en el docstring) ──
UMBRALES = {
    "lluvia_intensa": {"var": "precipitation_sum",  "op": ">=", "valor": 30, "unidad": "mm/24h", "label": "Lluvia intensa"},
    "viento_fuerte":  {"var": "wind_gusts_10m_max",  "op": ">=", "valor": 60, "unidad": "km/h",   "label": "Viento fuerte / huracanado"},
    "nieve":          {"var": "snowfall_sum",        "op": ">=", "valor": 5,  "unidad": "cm/24h", "label": "Nieve"},
    "helada":         {"var": "temperature_2m_min",  "op": "<=", "valor": 0,  "unidad": "°C",     "label": "Helada / riesgo de hielo"},
    "calor_extremo":  {"var": "temperature_2m_max",  "op": ">=", "valor": 32, "unidad": "°C",     "label": "Calor extremo"},
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
            print(f"  [aviso] No se pudo geocodificar '{nombre}' — usando coordenadas de respaldo (confirmar).")
            sectores[nombre] = fallback
    return sectores


def fetch_forecast(lat: float, lon: float) -> dict:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "snowfall_sum,windspeed_10m_max,wind_gusts_10m_max",
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

Se recomienda tomar los resguardos correspondientes con anticipación.

Alerta generada automáticamente a partir del pronóstico de Open-Meteo — Panel de Control SG Raíces.
Los umbrales usados son una referencia aproximada a criterios públicos de aviso meteorológico; ante duda, verificar con el boletín oficial de la Dirección Meteorológica de Chile (DMC) / SENAPRED.
"""


def enviar_alerta(remitente: str, app_pw: str, correo_dest: str, nombre: str, eventos: list, fecha_display: str):
    sectores_n = len({e["sector"] for e in eventos})
    asunto = f"⚠️ Alerta Climática — {sectores_n} sector(es) — {fecha_display}"

    msg = MIMEMultipart()
    msg["From"] = f"SG Raices Control <{remitente}>"
    msg["To"] = correo_dest
    msg["Subject"] = asunto
    msg.attach(MIMEText(_cuerpo_correo(nombre, eventos), "plain", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(remitente, app_pw)
        server.sendmail(remitente, [correo_dest], msg.as_string())


def main(forzar_envio: bool = None):
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

    guardar_estado(estado_actualizado)
    print(f"\nEnvíos completados: {len(destinatarios) - len(errores)} OK, {len(errores)} errores")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    forzar = "--forzar-envio" in sys.argv
    main(forzar_envio=forzar or None)

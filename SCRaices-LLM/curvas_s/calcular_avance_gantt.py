"""
calcular_avance_gantt.py
========================
Lee la pestaña 'Datos Control' de cada Gantt de control (Google Sheets),
calcula el promedio de avance real (%col D) y el avance programado (usando
la curva S PCT_SEMANA de cada proyecto con fechas de inicio col C), y escribe
el resultado en Firebase RTDB:

  avance_gantt/{pid} = {
      pct:       <float, 1 decimal>,   # promedio avance real (%)
      pct_prog:  <float, 1 decimal>,   # avance programado segun curva S a hoy
      n:         <int>,                # beneficiarios con valor > 0
      total:     <int>,                # total beneficiarios leídos
      fuente:    "Datos Control",
      actualizado: "YYYY-MM-DD",
  }

Ejecutar: python calcular_avance_gantt.py
Integrado en ejecutar_curvas_cloud.py (POST_SCRIPTS).
"""

import sys
import logging
import requests
from datetime import date, datetime, timedelta
from googleapiclient.discovery import build
import curvas_cloud_utils as _ccu

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
FIREBASE_URL = "https://scraices-dashboard-default-rtdb.firebaseio.com/avance_gantt.json"

# Spreadsheet ID de cada Gantt de control (mismos que actualizar_gantt_programa.py)
PROYECTOS = {
    "P31":  "1kgroktRIto3gGGnvmXGMgoetXT-Rv8JFue1K9eNlNMg",
    "P38":  "151wIDnZn8_b7egJKLQKUcD6QDCflEWF5OlAU9KWgc-M",
    "P126": "1IwBN7CpDvKVAvaRuYHNUfkQ0e98cJMVFDKFrntv3oNw",
    "P39":  "1GiaZ1i3BN3mbgFmg16Ze5E25R0jEmYULtCWRy6cKaHo",
    "P127": "1bgT-83Aea0DlyeQ6OvitGDZfm3jLRQUV0GooVP-G8EI",
    "P12":  "1SLu5lQTAzhHOUuorM3jbxSBes7vMyIB9mMXCihQ6A40",
    "P14":  "1B4wO-UkIDDyFvwRYjMAGksJvKqtNblwl_IirLl3qA6E",
    "P116": "1z9kNq9uo363NrWqCojGfGpP326FDj3V60irWxtMMbU8",
    "P119": "1t_1j62f_3l1nrlufmvhnV-o1WTplv0OnQL_JdVaWgKA",
    "P131": "1n5F-P5cy8Wj5BujllzdnwCrKwGsfIkdvHxcyd6YwscU",
    "P28":  "18XkRb7RAF52Aqj4immGebME-d9sODY0HgxIKWcBGrlg",
    # ── Proyectos futuros — descomentar y reemplazar TODO con el ID de la planilla Gantt ──
    # "P118": "TODO",  # El Canelo             — Rural Araucanía 2024
    # "P123": "TODO",  # Peumayen 2023          — Rural Araucanía 2024
    # "P128": "TODO",  # Com. José Carvajal     — Rural Araucanía 2024
    # "P129": "TODO",  # Nuevo Gorbea           — Rural Araucanía 2024
    # "P132": "TODO",  # Com. Fermín Manquilef  — Rural Araucanía 2024
    # "P145": "TODO",  # Perkenko 2025          — Rural Araucanía 2025
    # "P146": "TODO",  # Demanda Villarrica 2025
    # "P147": "TODO",  # Ruka Antü              — Rural Araucanía 2025
    # "P150": "TODO",  # Llaima Antu            — Rural Araucanía 2025
    # "P152": "TODO",  # Ayün Ruka              — Rural Araucanía 2025
    # "P153": "TODO",  # Vilcún Mapu            — Rural Araucanía 2025
    # "P154": "TODO",  # Com. José Carvajal 2   — Rural Araucanía 2025
    # "P155": "TODO",  # Los Arrayanes          — Rural Araucanía 2025
    # "P156": "TODO",  # Poyen Ruka             — Rural Araucanía 2025
    # "P164": "TODO",  # Conún Huenu            — Rural Araucanía 2026
    # "P166": "TODO",  # Malalhue               — Rural Araucanía 2026
    # "P167": "TODO",  # Witran Donguil         — Rural Araucanía 2026
    # "P168": "TODO",  # Raíces de Perquenco    — Rural Araucanía 2026
    # "P170": "TODO",  # Los Copihues de Cunco  — Rural Araucanía 2026
    # "P171": "TODO",  # Raíces de Trovolhue    — Rural Araucanía 2026
    # "P172": "TODO",  # Raíces Costeras        — Rural Araucanía 2026
}

# Parámetros de la Curva S por proyecto (copiados de cada curvas_automatico_*.py)
PROYECTO_CURVAS = {
    "P14": {
        "pct_semana": [0, 2, 7, 11, 16, 20, 25, 30, 34, 39, 43, 48, 52, 57, 61,
                       66, 70, 75, 80, 84, 89, 93, 98, 100, 100, 100],
        "duracion": 154,
    },
    "P116": {
        "pct_semana": [0, 5, 9, 14, 18, 23, 27, 32, 36, 41, 45, 50,
                       55, 59, 64, 68, 73, 77, 82, 86, 91, 95, 100, 100],
        "duracion": 147,
    },
    "P38": {
        "pct_semana": [0, 2, 5, 9, 14, 18, 23, 27, 32, 36, 41, 45, 50, 55, 59, 64,
                       68, 73, 77, 82, 86, 91, 95, 100, 100, 100, 100, 100, 100, 100,
                       100, 100, 100],
        "duracion": 224,
    },
    "P31": {
        "pct_semana": [0, 2, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45,
                       48, 52, 55, 58, 61, 64, 67, 70, 73, 76, 79, 82, 85, 88, 91, 94,
                       97, 98, 100, 100],
        "duracion": 221,
    },
    "P12": {
        "pct_semana": [0, 4, 7, 11, 14, 18, 21, 25, 29, 32, 36, 39, 43, 46, 50,
                       54, 57, 61, 64, 68, 71, 75, 79, 82, 86, 89, 93, 96, 100, 100],
        "duracion": 245,
    },
    "P119": {
        "pct_semana": [0, 4, 7, 11, 14, 18, 21, 25, 29, 32, 36, 39, 43, 46, 50,
                       54, 57, 61, 64, 68, 71, 75, 79, 82, 86, 89, 93, 96, 100, 100],
        "duracion": 245,
    },
    "P131": {
        "pct_semana": [0, 3, 6, 8, 11, 14, 17, 19, 22, 25, 28, 31, 33, 36, 39, 42,
                       44, 47, 50, 53, 56, 58, 61, 64, 67, 69, 72, 75, 78, 81, 83,
                       86, 89, 92, 94, 97, 100, 100],
        "duracion": 245,
    },
    "P28": {
        "pct_semana": [0,  2,  4,  7, 10, 13, 17, 21, 25, 30, 35, 40, 45, 50, 55,
                       60, 65, 70, 74, 78, 82, 85, 88, 90, 92, 94, 96, 97, 98, 99,
                       100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
        "duracion": 308,
    },
    "P127": {
        "pct_semana": [0, 4, 7, 11, 14, 18, 21, 25, 29, 32, 36, 39, 43, 46, 50,
                       54, 57, 61, 64, 68, 71, 75, 79, 82, 86, 89, 93, 96, 100, 100,
                       100, 100, 100, 100, 100, 100],
        "duracion": 245,
    },
    "P39": {
        "pct_semana": [0,  2,  3,  5,  7,  9, 12, 14, 17, 20, 23, 27, 30, 34, 37,
                       41, 44, 48, 51, 55, 58, 62, 65, 68, 71, 75, 78, 81, 84, 87,
                       89, 91, 93, 95, 96, 97, 98, 99, 100, 100, 100, 100, 100, 100,
                       100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
        "duracion": 392,
    },
    "P126": {
        "pct_semana": [0, 4, 9, 13, 17, 22, 26, 30, 35, 39, 43, 48, 52, 57, 61, 65,
                       70, 74, 78, 83, 87, 91, 96, 100, 100],
        "duracion": 147,
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades Curva S
# ─────────────────────────────────────────────────────────────────────────────

def _parse_inicio(val) -> date | None:
    """Parsea fecha de col C: acepta serial number de Sheets o string DD/MM/YYYY."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        # Google Sheets serial: días desde 30/12/1899
        try:
            return (date(1899, 12, 30) + timedelta(days=int(val)))
        except Exception:
            return None
    s = str(val).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _pct_programada(dia: int, pct_semana: list) -> float:
    """Interpola el avance programado para 'dia' días usando la tabla PCT_SEMANA."""
    if dia <= 0:
        return 0.0
    semana = dia / 7.0
    idx = int(semana)
    frac = semana - idx
    if idx >= len(pct_semana) - 1:
        return 100.0
    return pct_semana[idx] + frac * (pct_semana[idx + 1] - pct_semana[idx])


def _calc_pct_prog(inicios: list, hoy: date, pct_semana: list) -> float | None:
    """Avance programado promedio = media de _pct_programada(dias_desde_inicio)."""
    if not inicios:
        return None
    vals = [_pct_programada((hoy - ini).days, pct_semana) for ini in inicios]
    return round(sum(vals) / len(vals), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura Datos Control
# ─────────────────────────────────────────────────────────────────────────────

def _leer_datos_control(sheets_svc, spreadsheet_id, pid) -> dict | None:
    """
    Lee la hoja 'Datos Control':
      col A = grupo, col B = nombre, col C = inicio, col D = % real
    Calcula pct (avance real promedio) y pct_prog (avance programado a hoy).
    """
    try:
        meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_names = [s["properties"]["title"] for s in meta["sheets"]]
    except Exception as e:
        log.error(f"  {pid}: error obteniendo hojas → {e}")
        return None

    hoja = None
    for nombre in ["Datos Control", "datos control", "DatosControl"]:
        if nombre in sheet_names:
            hoja = nombre
            break

    if not hoja:
        log.warning(f"  {pid}: no se encontró 'Datos Control' en {sheet_names[:5]}")
        return None

    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{hoja}'!A1:D200",
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        ).execute()
    except Exception as e:
        log.error(f"  {pid}: error leyendo '{hoja}': {e}")
        return None

    rows = result.get("values", [])
    if len(rows) < 5:
        log.warning(f"  {pid}: muy pocas filas en '{hoja}' ({len(rows)})")
        return None

    hoy = date.today()
    curvas_cfg = PROYECTO_CURVAS.get(pid)

    valores_real   = []
    inicios_validos = []

    for row in rows[4:]:  # filas 5+: datos beneficiarios
        if len(row) < 2:
            continue
        grupo  = str(row[0]).strip() if row[0] else ""
        nombre = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if not grupo or not nombre:
            continue

        # % real (col D)
        pct_raw = row[3] if len(row) > 3 else 0
        try:
            pct = float(str(pct_raw).replace("%", "").strip())
        except (ValueError, TypeError):
            pct = 0.0
        valores_real.append(pct)

        # inicio (col C) — para calcular avance programado
        if curvas_cfg and len(row) > 2:
            ini = _parse_inicio(row[2])
            if ini:
                inicios_validos.append(ini)

    if not valores_real:
        log.warning(f"  {pid}: sin beneficiarios con datos en '{hoja}'")
        return None

    n_con_valor = sum(1 for v in valores_real if v > 0)
    promedio    = round(sum(valores_real) / len(valores_real), 1)

    # Avance programado
    pct_prog = None
    if curvas_cfg and inicios_validos:
        pct_prog = _calc_pct_prog(inicios_validos, hoy, curvas_cfg["pct_semana"])
        log.info(
            f"  {pid}: real={promedio}%  prog={pct_prog}%  "
            f"({len(inicios_validos)}/{len(valores_real)} benef. con inicio)"
        )
    else:
        log.info(
            f"  {pid}: [{hoja}] {len(valores_real)} benef. | "
            f"{n_con_valor} con avance > 0 | promedio = {promedio}%"
        )

    resultado = {
        "pct":         promedio,
        "n":           n_con_valor,
        "total":       len(valores_real),
        "fuente":      "Datos Control",
        "actualizado": hoy.isoformat(),
    }
    if pct_prog is not None:
        resultado["pct_prog"] = pct_prog

    return resultado


def main():
    log.info("=== calcular_avance_gantt ===")
    creds = _ccu.get_credentials()
    sheets_svc = build("sheets", "v4", credentials=creds)

    resultado = {}
    for pid, sid in PROYECTOS.items():
        log.info(f"Leyendo {pid}...")
        datos = _leer_datos_control(sheets_svc, sid, pid)
        if datos:
            resultado[pid] = datos

    if not resultado:
        log.error("Sin datos para ningún proyecto. Abortando escritura en Firebase.")
        sys.exit(1)

    log.info(f"Escribiendo {len(resultado)} proyectos en Firebase → avance_gantt/")
    resp = requests.put(FIREBASE_URL, json=resultado, timeout=30)
    if resp.status_code == 200:
        log.info("Firebase actualizado OK.")
        for pid, d in resultado.items():
            prog_str = f"  prog={d['pct_prog']}%" if "pct_prog" in d else ""
            log.info(f"  {pid}: real={d['pct']}%{prog_str}  ({d['n']}/{d['total']} benef.)")
    else:
        log.error(f"Error Firebase: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)

    log.info("=== Listo ===")


if __name__ == "__main__":
    main()

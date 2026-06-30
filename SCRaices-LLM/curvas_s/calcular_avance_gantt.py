"""
calcular_avance_gantt.py
========================
Lee la pestaña 'Datos Control' de cada Gantt de control (Google Sheets),
calcula el promedio de avance real (%col D) de todos los beneficiarios
y escribe el resultado en Firebase RTDB:

  avance_gantt/{pid} = {
      pct:       <float, 1 decimal>,   # promedio avance real (%)
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
from datetime import date
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
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _leer_datos_control(sheets_svc, spreadsheet_id, pid) -> dict | None:
    """
    Lee la hoja 'Datos Control' y devuelve el avance promedio.
    Columna D (índice 3) = % real del beneficiario.
    Filas 5+ (índice 4+) = datos de beneficiarios.
    """
    # Obtener hojas disponibles para encontrar 'Datos Control'
    try:
        meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_names = [s["properties"]["title"] for s in meta["sheets"]]
    except Exception as e:
        log.error(f"  {pid}: error obteniendo hojas → {e}")
        return None

    # Buscar hoja 'Datos Control' o variante
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
        ).execute()
    except Exception as e:
        log.error(f"  {pid}: error leyendo '{hoja}': {e}")
        return None

    rows = result.get("values", [])
    if len(rows) < 5:
        log.warning(f"  {pid}: muy pocas filas en '{hoja}' ({len(rows)})")
        return None

    valores = []
    for row in rows[4:]:  # filas 5+ (índice 4): beneficiarios
        if len(row) < 2:
            continue
        grupo  = str(row[0]).strip() if row[0] else ""
        nombre = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if not grupo or not nombre:
            continue
        pct_raw = row[3] if len(row) > 3 else 0
        try:
            pct = float(str(pct_raw).replace("%", "").strip())
        except (ValueError, TypeError):
            pct = 0.0
        valores.append(pct)

    if not valores:
        log.warning(f"  {pid}: sin beneficiarios con datos en '{hoja}'")
        return None

    n_con_valor = sum(1 for v in valores if v > 0)
    promedio    = round(sum(valores) / len(valores), 1)

    log.info(
        f"  {pid}: [{hoja}] {len(valores)} benef. | "
        f"{n_con_valor} con avance > 0 | promedio = {promedio}%"
    )
    return {
        "pct":         promedio,
        "n":           n_con_valor,
        "total":       len(valores),
        "fuente":      "Datos Control",
        "actualizado": date.today().isoformat(),
    }


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
            log.info(f"  {pid}: {d['pct']}% ({d['n']}/{d['total']} benef.)")
    else:
        log.error(f"Error Firebase: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)

    log.info("=== Listo ===")


if __name__ == "__main__":
    main()

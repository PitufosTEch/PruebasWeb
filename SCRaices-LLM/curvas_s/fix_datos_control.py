"""
fix_datos_control.py — Actualiza fechas INICIO en 'Datos Control' de todos los proyectos.

Lee las fechas de inicio individuales desde la Gantt de cada proyecto y las compara
con lo que hay en 'Datos Control'. Si difieren, escribe la fecha correcta.
No modifica grupos, no modifica % avance.
"""

import os
import sys
import unicodedata
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_sheets_service():
    import curvas_cloud_utils as utils
    from googleapiclient.discovery import build

    creds = utils.get_credentials(["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# ── Normalización ─────────────────────────────────────────────────────────────

def _norm(nombre):
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_t = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_t.upper().split())


# ── Configuración por proyecto ────────────────────────────────────────────────
#
# name_col  : índice de columna (0-based) donde está el nombre del beneficiario
# ini_col   : índice de columna (0-based) donde está la fecha INICIO
# grupo_cols: lista de índices a revisar (en orden) para detectar header "GRUPO X"
#
# Para trovolhue el nombre se construye concatenando apellidos(col2)+nombres(col3).

PROJECTS = [
    {
        "label":       "P119 Ñuke Mapu",
        "sid":         "1t_1j62f_3l1nrlufmvhnV-o1WTplv0OnQL_JdVaWgKA",
        "gantt_hoja":  "Ñuke Mapu",
        "gantt_range": "A1:J60",
        "name_col":    3,
        "ini_col":     8,
        "grupo_cols":  [1, 0, 3],
        "extra_grupos": {"REZAGADOS"},
    },
    {
        "label":       "P38 Aliwen",
        "sid":         "151wIDnZn8_b7egJKLQKUcD6QDCflEWF5OlAU9KWgc-M",
        "gantt_hoja":  "% Avance",
        "gantt_range": "A1:Z25",
        "name_col":    2,
        "ini_col":     7,
        "grupo_cols":  [2],
    },
    {
        "label":       "P39 El Coihue",
        "sid":         "1GiaZ1i3BN3mbgFmg16Ze5E25R0jEmYULtCWRy6cKaHo",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     10,
        "grupo_cols":  [0, 2, 3],
    },
    {
        "label":       "P127 Nuevo Cunco",
        "sid":         "1bgT-83Aea0DlyeQ6OvitGDZfm3jLRQUV0GooVP-G8EI",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     10,
        "grupo_cols":  [0, 2, 3],
    },
    {
        "label":       "P12 Juan Huilcan",
        "sid":         "1SLu5lQTAzhHOUuorM3jbxSBes7vMyIB9mMXCihQ6A40",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     8,
        "grupo_cols":  [3, 0, 2],
    },
    {
        "label":       "P14 Com. Madihue",
        "sid":         "1B4wO-UkIDDyFvwRYjMAGksJvKqtNblwl_IirLl3qA6E",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     7,
        "grupo_cols":  [3, 0, 2],
    },
    {
        "label":       "P126 El Maitén",
        "sid":         "1IwBN7CpDvKVAvaRuYHNUfkQ0e98cJMVFDKFrntv3oNw",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     10,
        "grupo_cols":  [0, 2, 3],
    },
    {
        "label":       "P131 Raíces Melipeuco",
        "sid":         "1n5F-P5cy8Wj5BujllzdnwCrKwGsfIkdvHxcyd6YwscU",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    2,
        "ini_col":     6,
        "grupo_cols":  [2, 3, 0],
    },
    {
        "label":       "P116 Sonia Quilaleo",
        "sid":         "1z9kNq9uo363NrWqCojGfGpP326FDj3V60irWxtMMbU8",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:L60",
        "name_col":    3,
        "ini_col":     7,
        "grupo_cols":  [3, 0, 2],
    },
    {
        "label":       "P31 Trovolhue",
        "sid":         "1kgroktRIto3gGGnvmXGMgoetXT-Rv8JFue1K9eNlNMg",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:BG60",
        "name_col":    None,   # nombre = row[2] + row[3] (apellidos + nombres)
        "ini_col":     4,
        "grupo_cols":  [2, 3, 0],
        "trovolhue":   True,
    },
    {
        "label":       "P28 Elsa Pinchulaf",
        "sid":         "18XkRb7RAF52Aqj4immGebME-d9sODY0HgxIKWcBGrlg",
        "gantt_hoja":  "Programa de obra",
        "gantt_range": "A1:BZ60",
        "name_col":    3,
        "ini_col":     8,
        "grupo_cols":  [3, 0, 2],
    },
]

EXCLUIR = {"BENEFICIARIO", "CARTA GANTT", "BENEFICIARIO ", "PROGRAMA", "CORRE.", ""}


def _es_numero(s):
    try:
        float(s.replace("%", "").replace(",", "."))
        return True
    except ValueError:
        return False


def _leer_gantt(sheets_svc, proj):
    hoja   = proj["gantt_hoja"]
    rng    = f"'{hoja}'!{proj['gantt_range']}"
    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=proj["sid"],
        range=rng,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    rows = r.get("values", [])

    gantt_map = {}       # {nombre_norm: fecha_str}
    grupo_actual = None
    extra = proj.get("extra_grupos", set())

    for row in rows:
        if not row:
            continue

        # Detectar header de grupo
        grupo_cols = proj["grupo_cols"]
        for ci in grupo_cols:
            if ci < len(row):
                cell = str(row[ci]).strip().upper()
                if cell.startswith("GRUPO") or cell in extra:
                    grupo_actual = cell if cell.startswith("GRUPO") else f"GRUPO {cell}"
                    break

        # Construir nombre
        if proj.get("trovolhue"):
            ap = str(row[2]).strip() if len(row) > 2 else ""
            no = str(row[3]).strip() if len(row) > 3 else ""
            nombre_raw = (ap + " " + no).strip() if no else ap
        else:
            nc = proj["name_col"]
            nombre_raw = str(row[nc]).strip() if len(row) > nc else ""

        ic = proj["ini_col"]
        inicio_raw = str(row[ic]).strip() if len(row) > ic else ""

        if not nombre_raw or not grupo_actual:
            continue
        if nombre_raw.upper().startswith("GRUPO"):
            continue
        if nombre_raw.upper() in EXCLUIR:
            continue
        if _es_numero(nombre_raw):
            continue

        nn = _norm(nombre_raw)
        if nn:
            gantt_map[nn] = inicio_raw

    return gantt_map


def _leer_datos_control(sheets_svc, sid):
    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=sid,
        range="'Datos Control'!A1:D200",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    return r.get("values", [])


def _fix_project(sheets_svc, proj):
    label = proj["label"]
    log.info(f"\n{'='*60}")
    log.info(f"  {label}")
    log.info(f"{'='*60}")

    gantt_map = _leer_gantt(sheets_svc, proj)
    if not gantt_map:
        log.warning(f"  [SKIP] No se pudo leer Gantt de {label}")
        return 0

    log.info(f"  Gantt: {len(gantt_map)} beneficiarios leídos")

    dc_rows = _leer_datos_control(sheets_svc, proj["sid"])
    if not dc_rows:
        log.warning(f"  [SKIP] 'Datos Control' vacío en {label}")
        return 0

    updates = []  # list of (fila_1based, nombre, fecha_gantt, fecha_dc)

    for i, row in enumerate(dc_rows):
        # Datos Control empieza en fila 1 (índice 0), encabezados en las primeras ~4 filas
        if len(row) < 2:
            continue
        nombre_dc = str(row[1]).strip() if len(row) > 1 else ""
        if not nombre_dc:
            continue
        nn = _norm(nombre_dc)
        if nn not in gantt_map:
            continue

        fecha_gantt = gantt_map[nn].strip()
        if not fecha_gantt:
            continue

        fecha_dc = str(row[2]).strip() if len(row) > 2 else ""

        if fecha_dc != fecha_gantt:
            updates.append((i + 1, nombre_dc, fecha_gantt, fecha_dc))

    if not updates:
        log.info(f"  OK — sin diferencias de fecha en {label}")
        return 0

    log.info(f"  {len(updates)} fecha(s) a corregir:")
    for fila, nombre, f_gantt, f_dc in updates:
        log.info(f"    fila {fila}: {nombre}  DC={f_dc!r} → Gantt={f_gantt!r}")

    # Batch update col C con las fechas corregidas
    data = []
    for fila, nombre, f_gantt, f_dc in updates:
        data.append({
            "range": f"'Datos Control'!C{fila}",
            "values": [[f_gantt]],
        })

    sheets_svc.spreadsheets().values().batchUpdate(
        spreadsheetId=proj["sid"],
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    ).execute()

    log.info(f"  ✓ {len(updates)} celda(s) actualizadas en {label}")
    return len(updates)


def main():
    log.info("=== fix_datos_control.py ===")
    log.info(f"Procesando {len(PROJECTS)} proyectos...\n")

    sheets_svc = _get_sheets_service()
    total = 0
    errores = []

    for proj in PROJECTS:
        try:
            n = _fix_project(sheets_svc, proj)
            total += n
        except Exception as e:
            log.error(f"  ERROR en {proj['label']}: {e}")
            errores.append(proj["label"])

    log.info(f"\n{'='*60}")
    log.info(f"  TOTAL: {total} fecha(s) corregida(s) en {len(PROJECTS)} proyectos")
    if errores:
        log.warning(f"  ERRORES en: {errores}")
    log.info("=== fin ===")


if __name__ == "__main__":
    main()

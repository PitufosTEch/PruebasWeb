"""
curvas_automatico_maiten.py  -  Automatizacion semanal Curvas S - Proyecto El Maiten (P126)
============================================================================================
- Fecha de control:  date.today() (automatica)
- Datos de avance:   leidos desde AppSheet (proyecto P126) via Playwright
  Fallback:          hoja 'Datos Control' del spreadsheet El Maiten
- Genera 8 graficos PNG (6 grupos + total + todos grupos)
- Actualiza Drive, insertar IMAGE() en hoja 'Curvas S', marca PENDIENTE

Ejecucion manual:  python curvas_automatico_maiten.py
Ejecucion auto:    Tarea programada en Windows Task Scheduler (lunes 08:15)

Primera ejecucion:
  Si AppSheet no tiene auth guardada, ejecutar primero:
    setup_appsheet_auth.bat  (doble clic)
  El script creara las hojas 'Datos Control' y 'Curvas S' automaticamente.
"""

import os
import sys
import json
import logging
import traceback
from pathlib import Path
from datetime import date, timedelta, datetime

# AppSheet reader (Playwright-based)
try:
    from leer_appsheet import leer_avance_maiten
    APPSHEET_DISPONIBLE = True
except ImportError:
    APPSHEET_DISPONIBLE = False

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from scipy.special import expit
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import curvas_cloud_utils as _ccu
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1IwBN7CpDvKVAvaRuYHNUfkQ0e98cJMVFDKFrntv3oNw"
TOKEN_FILE     = _ccu.TOKEN_FILE
OUTPUT_DIR     = _ccu.get_output_dir()
DRIVE_IDS_FILE = None  # gestionado por _ccu (Firebase en cloud, JSON en local)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DPI_EXPORT = 200   # 10"x5.1" -> 2000x1020 px, optimo para celda 755x385

# Curva S programada semanal El Maiten (35 semanas = 245 dias)
PCT_SEMANA = [0, 4, 7, 11, 14, 18, 21, 25, 29, 32, 36, 39, 43, 46, 50,
              54, 57, 61, 64, 68, 71, 75, 79, 82, 86, 89, 93, 96, 100, 100,
              100, 100, 100, 100, 100, 100]
DURACION_DIAS = 245

COLORES = {
    "GRUPO 1":         "#1a6eb5",
    "GRUPO 2":         "#e07b00",
    "GRUPO 3":         "#2ca02c",
    "GRUPO 4":         "#d62728",
    "GRUPO 5":         "#9467bd",
    "GRUPO REZAGADOS": "#8c564b",
}

# Nombres de archivos de graficos (orden define layout 2 col en Sheets)
# col = i % 2,  row = i // 2
CHART_NAMES = [
    "CurvaS_GRUPO_1_Maiten.png",            # col=0, row=0
    "CurvaS_GRUPO_2_Maiten.png",            # col=1, row=0
    "CurvaS_GRUPO_3_Maiten.png",            # col=0, row=1
    "CurvaS_GRUPO_4_Maiten.png",            # col=1, row=1
    "CurvaS_GRUPO_5_Maiten.png",            # col=0, row=2
    "CurvaS_GRUPO_REZAGADOS_Maiten.png",    # col=1, row=2
    "CurvaS_TOTAL_Maiten.png",              # col=0, row=3
    "CurvaS_Todos_Grupos_Maiten.png",       # col=1, row=3
]

# Datos de beneficiarios para setup inicial de 'Datos Control'
# Formato: (grupo, nombre, inicio_dd/mm/yyyy)
BENEFICIARIOS_SETUP = [
    # ── GRUPO 1 ──
    ("GRUPO 1", "CARRILLO MILLAVIL ALBERTO SEGUNDO",    "06/05/2026"),
    ("GRUPO 1", "CHIHUAILAF QUILAQUEO CLAUDIA TAMARA",  "06/05/2026"),
    ("GRUPO 1", "LOPEZ MARTINEZ GUILLERMO ERNESTO",     "13/05/2026"),
    ("GRUPO 1", "LIENQUEO JARAMILLO JOSE AVELINO",      "20/05/2026"),
    # ── GRUPO 2 ──
    ("GRUPO 2", "VIDAL SUAZO ELSA NELLY",               "03/06/2026"),
    ("GRUPO 2", "DUMULEF ALIANTE JOSE RAFAEL",          "03/06/2026"),
    ("GRUPO 2", "ESPINOZA MENIL JUAN LEONIDAS",         "10/06/2026"),
    ("GRUPO 2", "DUMULEF MILLANAO LIDIA DEL CARMEN",    "10/06/2026"),
    ("GRUPO 2", "MARTINEZ CHANDIA DAGOBERTO ORLANDO",   "17/06/2026"),
    # ── GRUPO 3 ──
    ("GRUPO 3", "VALDEBENITO MELLADO ENOMISIA DEL CARMEN", "24/06/2026"),
    ("GRUPO 3", "LINEROS FUENTES ERICA ISABEL",         "24/06/2026"),
    ("GRUPO 3", "CATRILEO LEFIMIL JUAN BAUTISTA",       "01/07/2026"),
    ("GRUPO 3", "ILLESCA PENA LORNA GLADYS",            "01/07/2026"),
    ("GRUPO 3", "REYES REYES MARIA ANGELICA",           "08/07/2026"),
    ("GRUPO 3", "ARAVENA RAINAO MARTA",                 "08/07/2026"),
    # ── GRUPO 4 ──
    ("GRUPO 4", "SMITH ERNST ALEX ROBERTO",             "22/07/2026"),
    ("GRUPO 4", "PILQUIAN LLANCACURA FIDELINA ELIANA",  "22/07/2026"),
    ("GRUPO 4", "HUENCHUFIL SILVA ROLANDO ALFREDO",     "29/07/2026"),
    # ── GRUPO 5 ──
    ("GRUPO 5", "HUILCAN LEFIN JOSE ESTEBAN",           "05/08/2026"),
    ("GRUPO 5", "HUILCAN LEFIU JUAN SEGUNDO",           "05/08/2026"),
    ("GRUPO 5", "BARAHONA QUILAQUEO MARIA LUISA",       "12/08/2026"),
    ("GRUPO 5", "AZOCAR BRAVO NORMA ESTER",             "12/08/2026"),
    # ── GRUPO REZAGADOS ──
    ("GRUPO REZAGADOS", "AGUAYO PARRA JORGE HERNAN",              "19/08/2026"),
    ("GRUPO REZAGADOS", "ALIANTE DUMULEF JUAN ALFONSO",           "26/08/2026"),
    ("GRUPO REZAGADOS", "ANTILAF PICHUN DELIA LUISA",             "26/08/2026"),
    ("GRUPO REZAGADOS", "CADIN CADIN JOSE HERNESTO",              "02/09/2026"),
    ("GRUPO REZAGADOS", "CONA LINCON ALBERTO CAYUMAN",            "09/09/2026"),
    ("GRUPO REZAGADOS", "GARCES SOLDADO TERESA",                  "09/09/2026"),
    ("GRUPO REZAGADOS", "PAINEMILLA HUARAPIL CARMEN RITA",        "09/09/2026"),
]

# ─────────────────────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────────────────────
log = _ccu.setup_logging("maiten")


# ─────────────────────────────────────────────────────────────────────────────
# DRIVE IDs persistidos en archivo JSON
# ─────────────────────────────────────────────────────────────────────────────
def _load_drive_ids():
    return _ccu.load_drive_ids("maiten")


def _save_drive_ids(ids):
    _ccu.save_drive_ids("maiten", ids)


def get_credentials():
    return _ccu.get_credentials(SCOPES)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SETUP INICIAL DE HOJAS
# ─────────────────────────────────────────────────────────────────────────────
def _get_sheet_gid(sheets_svc, nombre):
    """Retorna el GID de la hoja con el nombre dado, o None si no existe."""
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] == nombre:
            return sheet["properties"]["sheetId"]
    return None


def setup_hojas(sheets_svc):
    """
    Crea 'Datos Control' y 'Curvas S' si no existen.
    Puebla 'Datos Control' con los beneficiarios iniciales (solo si la hoja es nueva).
    """
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existentes = {s["properties"]["title"] for s in meta["sheets"]}

    requests = []
    crear_datos_control = "Datos Control" not in existentes
    crear_curvas_s      = "Curvas S" not in existentes

    if crear_datos_control:
        requests.append({"addSheet": {"properties": {"title": "Datos Control"}}})
        log.info("Creando hoja 'Datos Control'...")
    if crear_curvas_s:
        requests.append({"addSheet": {"properties": {"title": "Curvas S"}}})
        log.info("Creando hoja 'Curvas S'...")

    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": requests},
        ).execute()
        log.info("Hojas creadas.")

    # Poblar 'Datos Control' si era nueva
    if crear_datos_control:
        filas = [
            ["ESTADO", "OK"],
            ["FECHA_CONTROL", ""],
            [],
            ["GRUPO", "NOMBRE", "INICIO", "%_REAL"],
        ]
        for grupo, nombre, inicio in BENEFICIARIOS_SETUP:
            filas.append([grupo, nombre, inicio, 0])

        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="'Datos Control'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": filas},
        ).execute()
        log.info(f"'Datos Control' poblada con {len(BENEFICIARIOS_SETUP)} beneficiarios.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. LEER DATOS
# ─────────────────────────────────────────────────────────────────────────────
def _normalizar_nombre(nombre):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


# ─────────────────────────────────────────────────────────────────────────────
# 3b. SINCRONIZAR GRUPOS DESDE PROGRAMA DE OBRA
# ─────────────────────────────────────────────────────────────────────────────
# Columnas relevantes en 'Programa de obra': D=BENEFICIARIO, K=INICIO, L=TERMINO
# Filas de grupo (p.ej. "GRUPO 1") marcan el inicio de cada sección.
# Esta función detecta si algún beneficiario cambió de grupo entre el
# "Programa de obra" (fuente de verdad) y "Datos Control", y actualiza
# el sheet en caso de diferencias. Se llama cada lunes antes de leer datos.
# ─────────────────────────────────────────────────────────────────────────────
def sincronizar_grupos_desde_gantt(sheets_svc):
    log.info("Verificando movimientos de grupo en 'Programa de obra'...")

    # 1. Leer Programa de obra (columnas A:L, filas 1-60)
    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Programa de obra'!A1:L60",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    prog_rows = r.get("values", [])

    # Construir mapa: nombre_normalizado → (grupo, inicio_str)
    grupo_actual = None
    gantt_map = {}  # nombre_norm → {"grupo": str, "inicio": str}
    for row in prog_rows:
        if not row:
            continue
        # Detectar cabeceras de grupo (col A o col C con texto "GRUPO X")
        for col_idx in [0, 2, 3]:
            if col_idx < len(row):
                cell = str(row[col_idx]).strip().upper()
                if cell.startswith("GRUPO"):
                    grupo_actual = cell
                    break
        nombre_raw = str(row[3]).strip() if len(row) > 3 else ""
        inicio_raw = str(row[10]).strip() if len(row) > 10 else ""
        if (not nombre_raw or nombre_raw.upper().startswith("GRUPO")
                or nombre_raw.upper() in ("BENEFICIARIO", "CARTA GANTT", "")
                or not grupo_actual):
            continue
        # Omitir filas de totales/programa
        try:
            float(nombre_raw.replace("%", "").replace(",", "."))
            continue
        except ValueError:
            pass
        nombre_norm = _normalizar_nombre(nombre_raw)
        if nombre_norm:
            gantt_map[nombre_norm] = {"grupo": grupo_actual, "inicio": inicio_raw}

    if not gantt_map:
        log.warning("  No se pudo leer estructura de grupos desde 'Programa de obra'.")
        return

    # 2. Leer Datos Control actual
    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D50",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    dc_rows = dc.get("values", [])

    # Detectar cambios
    cambios = []
    for i, row in enumerate(dc_rows[4:], start=5):  # fila real en sheet = i+1 (1-indexed)
        if len(row) < 2 or not row[0].strip() or not row[1].strip():
            continue
        grupo_dc = str(row[0]).strip().upper()
        nombre_dc = str(row[1]).strip()
        nombre_norm = _normalizar_nombre(nombre_dc)
        if nombre_norm in gantt_map:
            grupo_gantt = gantt_map[nombre_norm]["grupo"]
            inicio_gantt = gantt_map[nombre_norm]["inicio"]
            if grupo_dc != grupo_gantt:
                cambios.append({
                    "fila_sheet": i,       # 1-indexed row in sheet
                    "nombre": nombre_dc,
                    "grupo_anterior": grupo_dc,
                    "grupo_nuevo": grupo_gantt,
                    "inicio_nuevo": inicio_gantt,
                    "pct": row[3] if len(row) > 3 else 0,
                })

    if not cambios:
        log.info("  Sin movimientos de grupo detectados.")
        return

    # 3. Aplicar cambios: reescribir grupos/inicio en las filas afectadas
    log.info(f"  MOVIMIENTOS DETECTADOS ({len(cambios)}):")
    requests = []
    for c in cambios:
        log.info(f"    >> {c['nombre']}: {c['grupo_anterior']} → {c['grupo_nuevo']} "
                 f"(inicio: {c['inicio_nuevo']})")
        # Actualizar col A (grupo) y col C (inicio) de la fila afectada
        fila_idx = c["fila_sheet"] - 1  # 0-indexed
        requests.append({"updateCells": {
            "range": {"sheetId": _get_dc_gid(sheets_svc),
                      "startRowIndex": fila_idx, "endRowIndex": fila_idx + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{"userEnteredValue": {"stringValue": c["grupo_nuevo"]}}]}],
            "fields": "userEnteredValue"
        }})
        if c["inicio_nuevo"]:
            requests.append({"updateCells": {
                "range": {"sheetId": _get_dc_gid(sheets_svc),
                          "startRowIndex": fila_idx, "endRowIndex": fila_idx + 1,
                          "startColumnIndex": 2, "endColumnIndex": 3},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": c["inicio_nuevo"]}}]}],
                "fields": "userEnteredValue"
            }})

    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": requests},
        ).execute()
        # Reordenar Datos Control para mantener grupos juntos
        _reordenar_datos_control(sheets_svc)
        log.info(f"  Datos Control actualizado con {len(cambios)} movimiento(s).")

    return cambios


def _get_dc_gid(sheets_svc):
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Datos Control":
            return s["properties"]["sheetId"]
    return 0


def _reordenar_datos_control(sheets_svc):
    """Reordena filas de datos por grupo para mantener consistencia visual."""
    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D50",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    rows = dc.get("values", [])
    header = rows[:4]
    datos = [r for r in rows[4:] if len(r) >= 2 and r[0].strip() and r[1].strip()]

    orden_grupos = ["GRUPO 1", "GRUPO 2", "GRUPO 3", "GRUPO 4", "GRUPO 5", "GRUPO REZAGADOS"]

    def sort_key(r):
        g = str(r[0]).strip().upper()
        try:
            return (orden_grupos.index(g), r[1])
        except ValueError:
            return (99, r[1])

    datos_ordenados = sorted(datos, key=sort_key)
    nuevas_filas = header + datos_ordenados

    sheets_svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range="'Datos Control'!A1:D50"
    ).execute()
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": nuevas_filas},
    ).execute()
    log.info("  Datos Control reordenado por grupo.")


def leer_avance_appsheet():
    if not APPSHEET_DISPONIBLE:
        log.warning("Modulo leer_appsheet no disponible.")
        return None
    try:
        log.info("Leyendo avance desde AppSheet P126 (El Maiten)...")
        datos = leer_avance_maiten()
        result = {_normalizar_nombre(k): v for k, v in datos.items()}
        log.info(f"  AppSheet P126: {len(result)} beneficiarios leidos.")
        return result
    except Exception as e:
        log.warning(f"AppSheet no disponible ({e}). Usando 'Datos Control'.")
        return None


def leer_datos_control(sheets_svc):
    """
    Lee la hoja 'Datos Control' de El Maiten.
    Fecha de control = hoy (automatica).
    % real = AppSheet P126 (o col D como fallback).
    """
    control_date = date.today()
    log.info(f"Fecha de control (hoy): {control_date.strftime('%d/%m/%Y')}")

    rng = "'Datos Control'!A1:D100"
    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rng,
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    rows = result.get("values", [])

    avance_appsheet = leer_avance_appsheet()

    grupos = {}
    sin_match = []

    for row in rows[4:]:   # datos desde fila 5 (indice 4)
        if len(row) < 3:
            continue
        grupo_raw = str(row[0]).strip()
        nombre    = str(row[1]).strip()
        inicio_s  = str(row[2]).strip()
        pct_hoja  = row[3] if len(row) > 3 else 0

        if not grupo_raw or not nombre:
            continue

        try:
            inicio = datetime.strptime(inicio_s, "%d/%m/%Y").date()
        except ValueError:
            try:
                inicio = datetime.strptime(inicio_s, "%m/%d/%Y").date()
            except ValueError:
                log.warning(f"Fecha no reconocida para {nombre}: {inicio_s!r}")
                inicio = date.today()

        if avance_appsheet:
            nombre_norm = _normalizar_nombre(nombre)
            pct = avance_appsheet.get(nombre_norm)
            if pct is None:
                apellido = nombre_norm.split()[0] if nombre_norm else ""
                for k, v in avance_appsheet.items():
                    if apellido and apellido in k:
                        pct = v
                        break
            if pct is None:
                sin_match.append(nombre)
                try:
                    pct = float(str(pct_hoja).replace("%", "").strip())
                except (ValueError, TypeError):
                    pct = 0.0
        else:
            try:
                pct = float(str(pct_hoja).replace("%", "").strip())
            except (ValueError, TypeError):
                pct = 0.0

        grupos.setdefault(grupo_raw, []).append((nombre, inicio, float(pct)))

    if sin_match:
        log.warning(f"Sin match AppSheet: {', '.join(sin_match)}")

    fuente = "AppSheet" if avance_appsheet else "'Datos Control'"
    log.info(f"Beneficiarios: {sum(len(v) for v in grupos.values())} "
             f"en {len(grupos)} grupos | avance desde: {fuente}")
    return control_date, grupos


# ─────────────────────────────────────────────────────────────────────────────
# 4. LOGICA DE CURVAS S
# ─────────────────────────────────────────────────────────────────────────────
def pct_programada(dia):
    if dia <= 0:
        return 0.0
    semana = dia / 7.0
    idx = int(semana)
    frac = semana - idx
    if idx >= len(PCT_SEMANA) - 1:
        return 100.0
    return PCT_SEMANA[idx] + frac * (PCT_SEMANA[idx + 1] - PCT_SEMANA[idx])


def s_curve_real(t_days, pct_real, t_control):
    if t_control <= 0 or pct_real == 0:
        return 0.0
    t_norm = t_days / t_control
    k = 8.0
    val     = expit(k * (t_norm - 0.5))
    val_max = expit(k * 0.5)
    val_min = expit(k * (-0.5))
    return float(np.clip((val - val_min) / (val_max - val_min) * pct_real, 0, pct_real))


def _estimar_inicio_efectivo(control, pct_real):
    """
    Cuando un beneficiario tiene inicio >= control pero pct_real > 0,
    estima retroactivamente la fecha de inicio segun PCT_SEMANA.
    """
    if pct_real <= 0:
        return control
    pct_capped = min(float(pct_real), 99.9)
    for semana in range(len(PCT_SEMANA) - 1):
        p0, p1 = PCT_SEMANA[semana], PCT_SEMANA[semana + 1]
        if p0 <= pct_capped <= p1:
            frac = (pct_capped - p0) / max(0.1, p1 - p0)
            dias_estimados = max(7, int((semana + frac) * 7))
            return control - timedelta(days=dias_estimados)
    return control - timedelta(days=int(DURACION_DIAS * 0.9))


def proyectar_fin(inicio, pct_real, control):
    if pct_real <= 10:
        return inicio + timedelta(days=DURACION_DIAS)
    inicio_ef  = min(inicio, control)
    dias_trans = max(1, (control - inicio_ef).days)
    tasa       = pct_real / dias_trans
    dias_rest  = (100 - pct_real) / tasa
    return control + timedelta(days=int(dias_rest))


def build_group_curves(beneficiarios, control):
    # Opcion B: si inicio >= control pero pct_real > 0, estimar inicio efectivo
    beneficiarios_adj = []
    for nombre, inicio, pct in beneficiarios:
        if inicio >= control and pct > 0:
            inicio_eff = _estimar_inicio_efectivo(control, pct)
            log.info(f"    [inicio_eff] {nombre}: planif={_fmt_date(inicio)} "
                     f"-> eff={_fmt_date(inicio_eff)} ({pct:.0f}% real)")
            beneficiarios_adj.append((nombre, inicio_eff, pct))
        else:
            beneficiarios_adj.append((nombre, inicio, pct))
    beneficiarios = beneficiarios_adj

    inicio_grupo   = min(b[1] for b in beneficiarios)
    fines_prog     = [b[1] + timedelta(days=DURACION_DIAS) for b in beneficiarios]
    fin_proyecto   = max(fines_prog)
    fines_real     = [proyectar_fin(b[1], b[2], control) for b in beneficiarios]
    fin_proyectado = max(fines_real)

    fecha_fin = max(fin_proyecto, fin_proyectado) + timedelta(days=14)
    fechas = [inicio_grupo + timedelta(days=d)
              for d in range((fecha_fin - inicio_grupo).days + 1)]

    prog_list, real_list, proj_list = [], [], []
    for fecha in fechas:
        vp, vr, vproj = [], [], []
        for _, inicio, pct in beneficiarios:
            dias = (fecha - inicio).days
            vp.append(pct_programada(dias))
            if fecha <= control:
                t_ctrl = max(1, (control - inicio).days)
                vr.append(s_curve_real(max(0, dias), pct, t_ctrl))
            if fecha >= control:
                if pct <= 0:
                    vproj.append(pct_programada(dias))
                else:
                    dias_ctrl = max(1, (control - inicio).days)
                    vproj.append(min(100, (pct / dias_ctrl) * max(0, dias)))
        prog_list.append(np.mean(vp))
        real_list.append(np.mean(vr) if vr else None)
        proj_list.append(np.mean(vproj) if vproj else None)

    return fechas, prog_list, real_list, proj_list, fin_proyectado


# ─────────────────────────────────────────────────────────────────────────────
# 5. GENERAR GRAFICOS
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_date(d):
    return d.strftime("%d/%m/%Y")


def generar_grafico_grupo(nombre_grupo, beneficiarios, control, outdir):
    color = COLORES.get(nombre_grupo, "#333333")
    fechas, prog, real_hist, proj, fin_proy = build_group_curves(beneficiarios, control)

    pct_real_avg  = np.mean([b[2] for b in beneficiarios])
    idx_ctrl      = (control - fechas[0]).days
    pct_prog_ctrl = prog[idx_ctrl] if 0 <= idx_ctrl < len(prog) else 0.0

    fig, ax = plt.subplots(figsize=(10, 5.1))  # 2000x1020 px @ 200 DPI, optimo para celda 755x385
    ax.set_facecolor("#f8f9fa")
    fig.patch.set_facecolor("#ffffff")

    ax.plot(fechas, prog, color="#1f77b4", linewidth=2.5, linestyle="--",
            label="% Programado", zorder=3)

    rf = [f for f, v in zip(fechas, real_hist) if v is not None]
    rv = [v for v in real_hist if v is not None]
    ax.plot(rf, rv, color=color, linewidth=3, label="% Real (suavizado)", zorder=4)

    pf = [f for f, v in zip(fechas, proj) if v is not None]
    pv = [v for v in proj if v is not None]
    ax.plot(pf, pv, color="#d62728", linewidth=2, linestyle=":",
            label="% Proyectado", zorder=3)

    ax.axvline(control, color="#ff7f0e", linewidth=2, linestyle="-.",
               label=f"Fecha Control ({_fmt_date(control)})", zorder=5)

    if fin_proy <= fechas[-1]:
        ax.axvline(fin_proy, color="#9467bd", linewidth=1.5, linestyle=":",
                   label=f"Termino Proyectado ({_fmt_date(fin_proy)})", zorder=4)

    if 0 <= idx_ctrl < len(prog):
        _diff = pct_real_avg - prog[idx_ctrl]
        _signo = "+" if _diff >= 0 else ""
        ax.annotate(
            f"Prog: {prog[idx_ctrl]:.1f}%\nReal: {pct_real_avg:.1f}%\nDesv: {_signo}{_diff:.1f}%",
            xy=(control, prog[idx_ctrl]),
            xytext=(control + timedelta(days=14), prog[idx_ctrl] + 8),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6",
                      edgecolor="#ff7f0e", linewidth=1.0, alpha=0.95),
        )

    fin_prog_grupo = max(b[1] for b in beneficiarios) + timedelta(days=DURACION_DIAS)
    ax.set_xlim(fechas[0] - timedelta(days=7), fechas[-1] + timedelta(days=7))
    ax.set_ylim(-2, 108)
    ax.set_ylabel("Avance (%)", fontsize=12)
    ax.set_xlabel("Fecha", fontsize=12)
    ax.set_title(
        f"Curva S - {nombre_grupo} - El Maiten ({len(beneficiarios)} viviendas)\n"
        f"Inicio: {_fmt_date(min(b[1] for b in beneficiarios))}  |  "
        f"Fin Prog.: {_fmt_date(fin_prog_grupo)}  |  "
        f"Fin Proy.: {_fmt_date(fin_proy)}",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.grid(axis="y", alpha=0.4, linestyle="--")
    ax.grid(axis="x", alpha=0.2, linestyle=":")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax.axvspan(fechas[0], control, alpha=0.04, color="green")
    ax.axvspan(control, fechas[-1], alpha=0.04, color="red")

    plt.tight_layout()
    tag   = nombre_grupo.replace(" ", "_")
    fname = Path(outdir) / f"CurvaS_{tag}_Maiten.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight")
    plt.close()
    log.info(f"  Grafico guardado: {fname.name}")
    return pct_real_avg, pct_prog_ctrl, min(b[1] for b in beneficiarios), fin_proy


def generar_grafico_total(grupos, control, fines_proy_global, outdir):
    todos = [b for bens in grupos.values() for b in bens]
    inicio_total   = min(b[1] for b in todos)
    fin_prog_total = max(b[1] for b in todos) + timedelta(days=DURACION_DIAS)
    fin_proy_total = max(fines_proy_global)

    fecha_fin_total = max(fin_prog_total, fin_proy_total) + timedelta(days=14)
    fechas_total = [inicio_total + timedelta(days=d)
                    for d in range((fecha_fin_total - inicio_total).days + 1)]

    prog_total, real_total_hist, proj_total = [], [], []
    for fecha in fechas_total:
        vp, vr, vproj = [], [], []
        for _, inicio, pct in todos:
            dias = (fecha - inicio).days
            vp.append(pct_programada(dias))
            if fecha <= control:
                t_ctrl = max(1, (control - inicio).days)
                vr.append(s_curve_real(max(0, dias), pct, t_ctrl))
            if fecha >= control:
                if pct <= 0:
                    vproj.append(pct_programada(dias))
                else:
                    dias_ctrl = max(1, (control - inicio).days)
                    vproj.append(min(100, (pct / dias_ctrl) * max(0, dias)))
        prog_total.append(np.mean(vp))
        real_total_hist.append(np.mean(vr) if vr else None)
        proj_total.append(np.mean(vproj) if vproj else None)

    pct_real_total = np.mean([b[2] for b in todos])
    idx_ctrl_total = (control - inicio_total).days

    fig2, ax2 = plt.subplots(figsize=(10, 5.1))  # 2000x1020 px @ 200 DPI, optimo para celda 755x385
    ax2.set_facecolor("#f8f9fa")
    fig2.patch.set_facecolor("#ffffff")

    ax2.plot(fechas_total, prog_total, color="#1f77b4", linewidth=3,
             linestyle="--", label="% Programado Total", zorder=3)
    rt_f = [f for f, v in zip(fechas_total, real_total_hist) if v is not None]
    rt_v = [v for v in real_total_hist if v is not None]
    ax2.plot(rt_f, rt_v, color="#2ca02c", linewidth=3.5,
             label="% Real Total (suavizado)", zorder=4)
    pt_f = [f for f, v in zip(fechas_total, proj_total) if v is not None]
    pt_v = [v for v in proj_total if v is not None]
    ax2.plot(pt_f, pt_v, color="#d62728", linewidth=2.5, linestyle=":",
             label="% Proyectado Total", zorder=3)

    ax2.axvline(control, color="#ff7f0e", linewidth=2.5, linestyle="-.",
                label=f"Fecha Control ({_fmt_date(control)})", zorder=5)
    ax2.axvline(fin_proy_total, color="#9467bd", linewidth=2, linestyle=":",
                label=f"Termino Proyectado ({_fmt_date(fin_proy_total)})", zorder=4)
    ax2.axvline(fin_prog_total, color="#1f77b4", linewidth=1.5, linestyle=":",
                alpha=0.6, label=f"Termino Programado ({_fmt_date(fin_prog_total)})", zorder=3)

    if 0 <= idx_ctrl_total < len(prog_total):
        prog_en_ctrl = prog_total[idx_ctrl_total]
        diff = pct_real_total - prog_en_ctrl
        signo = "+" if diff >= 0 else ""
        ax2.annotate(
            f"Prog:  {prog_en_ctrl:.1f}%\nReal:  {pct_real_total:.1f}%\n"
            f"Desv: {signo}{diff:.1f}%",
            xy=(control, prog_en_ctrl),
            xytext=(control + timedelta(days=20), prog_en_ctrl + 10),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6",
                      edgecolor="#ff7f0e", linewidth=1.0, alpha=0.95),
        )

    ax2.set_xlim(fechas_total[0] - timedelta(days=7),
                 fechas_total[-1] + timedelta(days=7))
    ax2.set_ylim(-2, 108)
    ax2.set_ylabel("Avance promedio (%)", fontsize=12)
    ax2.set_xlabel("Fecha", fontsize=12)
    ax2.set_title(
        f"Curva S Total - Proyecto El Maiten P126 ({len(todos)} viviendas)\n"
        f"Inicio: {_fmt_date(inicio_total)}  |  "
        f"Fin Programado: {_fmt_date(fin_prog_total)}  |  "
        f"Fin Proyectado: {_fmt_date(fin_proy_total)}",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax2.grid(axis="y", alpha=0.4, linestyle="--")
    ax2.grid(axis="x", alpha=0.2, linestyle=":")
    ax2.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax2.axvspan(fechas_total[0], control, alpha=0.03, color="green")
    ax2.axvspan(control, fechas_total[-1], alpha=0.03, color="red")

    plt.tight_layout()
    fname_total = Path(outdir) / "CurvaS_TOTAL_Maiten.png"
    plt.savefig(fname_total, dpi=DPI_EXPORT, bbox_inches="tight")
    plt.close()
    log.info(f"  Grafico guardado: {fname_total.name}")


def generar_grafico_todos(grupos, control, fines_proy_global, outdir):
    fig3, ax3 = plt.subplots(figsize=(10, 5.1))  # 2000x1020 px @ 200 DPI, optimo para celda 755x385
    ax3.set_facecolor("#f8f9fa")
    fig3.patch.set_facecolor("#ffffff")

    inicio_global = date(2026, 5, 1)   # inicio aprox. del proyecto

    for nombre_grupo, beneficiarios in grupos.items():
        color = COLORES.get(nombre_grupo, "#333333")
        fechas, prog, real_hist, proj, _ = build_group_curves(beneficiarios, control)
        ax3.plot(fechas, prog, color=color, linewidth=1.5, linestyle="--", alpha=0.6)
        rf = [f for f, v in zip(fechas, real_hist) if v is not None]
        rv = [v for v in real_hist if v is not None]
        ax3.plot(rf, rv, color=color, linewidth=2.5, label=nombre_grupo)
        pf = [f for f, v in zip(fechas, proj) if v is not None]
        pv = [v for v in proj if v is not None]
        ax3.plot(pf, pv, color=color, linewidth=1.8, linestyle=":", alpha=0.8)

    ax3.axvline(control, color="#ff7f0e", linewidth=2.5, linestyle="-.",
                label="Fecha Control", zorder=5)

    legend_extra = [
        Line2D([0], [0], color="gray", linestyle="--", linewidth=1.5, label="Programado"),
        Line2D([0], [0], color="gray", linestyle="-",  linewidth=2.5, label="Real (suavizado)"),
        Line2D([0], [0], color="gray", linestyle=":",  linewidth=1.8, label="Proyectado"),
    ]
    handles, labels = ax3.get_legend_handles_labels()
    ax3.legend(handles=handles + legend_extra, loc="upper left", fontsize=9, framealpha=0.95)

    ax3.set_xlim(inicio_global, max(fines_proy_global) + timedelta(days=30))
    ax3.set_ylim(-2, 108)
    ax3.set_ylabel("Avance (%)", fontsize=12)
    ax3.set_xlabel("Fecha", fontsize=12)
    ax3.set_title(
        "Curva S por Grupo - El Maiten P126\n"
        "Linea continua = Real  |  Discontinua = Programado  |  Punteado = Proyectado",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax3.grid(axis="y", alpha=0.4, linestyle="--")
    ax3.grid(axis="x", alpha=0.2, linestyle=":")
    ax3.axvspan(inicio_global, control, alpha=0.03, color="green")

    plt.tight_layout()
    fname = Path(outdir) / "CurvaS_Todos_Grupos_Maiten.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight")
    plt.close()
    log.info(f"  Grafico guardado: {fname.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. SUBIR A DRIVE
# ─────────────────────────────────────────────────────────────────────────────
def _crear_o_actualizar_drive(drive_svc, name, path_local, drive_ids):
    """Sube imagen a Drive: actualiza si ya tiene ID, crea nuevo si no."""
    media = MediaFileUpload(str(path_local), mimetype="image/png", resumable=False)
    existing_id = drive_ids.get(name, "")

    if existing_id:
        drive_svc.files().update(
            fileId=existing_id,
            body={"name": name},
            media_body=media,
        ).execute()
        log.info(f"  Actualizado: {name} -> {existing_id}")
        return existing_id
    else:
        file_meta = {"name": name, "mimeType": "image/png"}
        result = drive_svc.files().create(
            body=file_meta,
            media_body=media,
            fields="id",
        ).execute()
        new_id = result["id"]
        # Hacer publico para que Sheets pueda mostrarlo
        drive_svc.permissions().create(
            fileId=new_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()
        log.info(f"  Creado nuevo: {name} -> {new_id}")
        return new_id


def actualizar_drive(drive_svc, outdir, drive_ids):
    log.info("Actualizando archivos en Google Drive...")
    ids_actualizados = dict(drive_ids)
    for name in CHART_NAMES:
        path = Path(outdir) / name
        if not path.exists():
            log.warning(f"  No encontrado: {name}, saltando.")
            continue
        new_id = _crear_o_actualizar_drive(drive_svc, name, path, ids_actualizados)
        ids_actualizados[name] = new_id
    return ids_actualizados


# ─────────────────────────────────────────────────────────────────────────────
# 7. INSERTAR IMAGENES EN HOJA 'Curvas S'
# ─────────────────────────────────────────────────────────────────────────────
def insertar_imagenes_en_sheets(sheets_svc, drive_ids, curvas_gid):
    """Actualiza las formulas IMAGE() en la hoja 'Curvas S' de El Maiten."""
    log.info("Actualizando formulas IMAGE() en hoja 'Curvas S' El Maiten...")
    W_PX, H_PX = 755, 385
    n_cols = 2
    n_rows = (len(CHART_NAMES) + 1) // 2   # ceil(8/2) = 4

    requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": curvas_gid, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": n_cols},
            "properties": {"pixelSize": W_PX}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": curvas_gid, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": n_rows},
            "properties": {"pixelSize": H_PX}, "fields": "pixelSize"
        }},
    ]
    # Timestamp unico por ejecucion -> fuerza re-fetch en Sheets (evita cache)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for i, name in enumerate(CHART_NAMES):
        col = i % 2
        row = i // 2
        drive_id = drive_ids.get(name, "")
        if not drive_id:
            log.warning(f"  Sin Drive ID para {name}, saltando formula.")
            continue
        url = f"https://drive.google.com/uc?id={drive_id}&export=view&v={ts}"
        requests.append({"updateCells": {
            "range": {"sheetId": curvas_gid,
                      "startRowIndex": row, "endRowIndex": row + 1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rows": [{"values": [{"userEnteredValue": {
                "formulaValue": f'=IMAGE("{url}",1)'
            }}]}],
            "fields": "userEnteredValue"
        }})

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests}
    ).execute()
    log.info(f"  Formulas IMAGE() actualizadas (v={ts}).")


# ─────────────────────────────────────────────────────────────────────────────
# 8. MARCAR PENDIENTE / ACTUALIZAR PCT
# ─────────────────────────────────────────────────────────────────────────────
def marcar_pendiente(sheets_svc, timestamp_str):
    control_str = date.today().strftime("%d/%m/%Y")
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:B2",
        valueInputOption="USER_ENTERED",
        body={"values": [
            ["ESTADO",        f"PENDIENTE - {timestamp_str}"],
            ["FECHA_CONTROL", control_str],
        ]},
    ).execute()
    log.info(f"Flag PENDIENTE escrito | FECHA_CONTROL={control_str}")


def marcar_ok(sheets_svc, timestamp_str):
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:B1",
        valueInputOption="USER_ENTERED",
        body={"values": [["ESTADO", f"OK - {timestamp_str}"]]},
    ).execute()


def actualizar_pct_en_hoja(sheets_svc, grupos):
    """Escribe % real actualizados de vuelta a 'Datos Control' col D."""
    valores = []
    for bens in grupos.values():
        for _, _, pct in bens:
            valores.append([round(pct)])
    n = len(valores)
    if valores:
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'Datos Control'!D5:D{4 + n}",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        log.info(f"  % real actualizados en 'Datos Control' ({n} filas)")


# ─────────────────────────────────────────────────────────────────────────────
# 9. MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 65)
    log.info(f"INICIO CURVAS S EL MAITEN  -  {ts}")
    log.info("=" * 65)

    try:
        creds      = get_credentials()
        sheets_svc = build("sheets", "v4", credentials=creds)
        drive_svc  = build("drive",  "v3", credentials=creds)

        # Setup inicial de hojas (idempotente)
        setup_hojas(sheets_svc)

        # Sincronizar grupos desde Programa de obra (detecta movimientos)
        sincronizar_grupos_desde_gantt(sheets_svc)

        # Obtener GID de 'Curvas S'
        curvas_gid = _get_sheet_gid(sheets_svc, "Curvas S")
        if curvas_gid is None:
            raise RuntimeError("No se encontro la hoja 'Curvas S' tras el setup.")
        log.info(f"GID hoja 'Curvas S': {curvas_gid}")

        # Leer datos
        control_date, grupos = leer_datos_control(sheets_svc)

        # Actualizar % en hoja
        actualizar_pct_en_hoja(sheets_svc, grupos)

        # Crear carpeta de salida
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

        # Generar graficos por grupo
        log.info("Generando graficos por grupo...")
        fines_proy_global = []
        for nombre_grupo, beneficiarios in grupos.items():
            _, _, _, fin_proy = generar_grafico_grupo(
                nombre_grupo, beneficiarios, control_date, OUTPUT_DIR
            )
            fines_proy_global.append(fin_proy)

        # Graficos consolidados
        log.info("Generando graficos consolidados...")
        generar_grafico_total(grupos, control_date, fines_proy_global, OUTPUT_DIR)
        generar_grafico_todos(grupos, control_date, fines_proy_global, OUTPUT_DIR)

        # Subir a Drive
        drive_ids = _load_drive_ids()
        drive_ids_nuevos = actualizar_drive(drive_svc, OUTPUT_DIR, drive_ids)
        _save_drive_ids(drive_ids_nuevos)   # persistir IDs nuevos

        # Actualizar formulas IMAGE() en 'Curvas S'
        insertar_imagenes_en_sheets(sheets_svc, drive_ids_nuevos, curvas_gid)

        # Marcar pendiente
        marcar_pendiente(sheets_svc, ts)

        log.info("=" * 65)
        log.info("COMPLETADO. Curvas S El Maiten actualizadas.")
        log.info("=" * 65)

    except Exception:
        log.error("ERROR:\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

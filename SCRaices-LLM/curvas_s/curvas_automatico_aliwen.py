"""
curvas_automatico_aliwen.py  -  Automatizacion semanal Curvas S - Proyecto Aliwen (P38)
========================================================================================
- Fecha de control:  date.today() (automatica)
- Datos de avance:   leidos desde AppSheet (proyecto P38) via Playwright
  Fallback:          hoja 'Datos Control' del spreadsheet Aliwen
- Genera 2 graficos PNG, actualiza Drive, marca PENDIENTE para Apps Script

Ejecucion manual:  python curvas_automatico_aliwen.py
Ejecucion auto:    Tarea programada en Windows Task Scheduler

Primera ejecucion:
  Si AppSheet no tiene auth guardada, ejecutar primero:
    setup_appsheet_auth.bat  (doble clic)
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from datetime import date, timedelta, datetime

# AppSheet reader (Playwright-based)
try:
    from leer_appsheet import leer_avance_p38
    APPSHEET_DISPONIBLE = True
except ImportError:
    APPSHEET_DISPONIBLE = False

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
SPREADSHEET_ID = "151wIDnZn8_b7egJKLQKUcD6QDCflEWF5OlAU9KWgc-M"
TOKEN_FILE     = _ccu.TOKEN_FILE
OUTPUT_DIR     = _ccu.get_output_dir()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DPI_EXPORT = 200           # resolucion de exportacion (10"x5.1" -> 2000x1020 px, optimo para celda 755x385)
DRIVE_IDS_FILE = None  # gestionado por _ccu (Firebase en cloud, JSON en local)

# Curva S programada semanal Aliwen (32 semanas = 224 dias)
PCT_SEMANA = [0, 2, 5, 9, 14, 18, 23, 27, 32, 36, 41, 45, 50, 55, 59, 64,
              68, 73, 77, 82, 86, 91, 95, 100, 100, 100, 100, 100, 100, 100,
              100, 100, 100]
DURACION_DIAS = 224

COLORES = {
    "GRUPO 1": "#1a6eb5",
    "GRUPO 2": "#e07b00",
}

CHART_NAMES = [
    "CurvaS_GRUPO_1_Aliwen.png",
    "CurvaS_GRUPO_2_Aliwen.png",
    "CurvaS_TOTAL_Aliwen.png",
    "CurvaS_Todos_Grupos_Aliwen.png",
]

# Estructura de beneficiarios para setup y sincronizacion
BENEFICIARIOS_SETUP = [
    # GRUPO 1 - inicio escalonado desde 02/03/2026
    ("GRUPO 1", "ANTIMIDORO NATALIO BASTIAS CRUCES",      "02/03/2026"),
    ("GRUPO 1", "BELLA ISABEL CALCUMIL CURIN",             "02/03/2026"),
    ("GRUPO 1", "BENJAMIN SEGUNDO NANCUFIL HUANQUILEN",   "09/03/2026"),
    ("GRUPO 1", "DANIEL ELADIO HUANQUILEN LLONCON",       "16/03/2026"),
    # GRUPO 2 - inicio escalonado desde 09/03/2026
    ("GRUPO 2", "VALERIA DEL PILAR HUAIQUIN RIQUELME",    "16/03/2026"),
    ("GRUPO 2", "GABRIEL MANUEL NANCUFIL LONCON",          "09/03/2026"),
]

# ─────────────────────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────────────────────
log = _ccu.setup_logging("aliwen")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CREDENCIALES
# ─────────────────────────────────────────────────────────────────────────────
def get_credentials():
    return _ccu.get_credentials(SCOPES)


# ─────────────────────────────────────────────────────────────────────────────
# 2. LEER DATOS
# ─────────────────────────────────────────────────────────────────────────────
def _normalizar_nombre(nombre):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


# ─────────────────────────────────────────────────────────────────────────────
# DRIVE IDs persistidos en JSON
# ─────────────────────────────────────────────────────────────────────────────
def _load_drive_ids():
    defaults = {
        "CurvaS_GRUPO_1_Aliwen.png": "1-Ltxm29q-7cMufIHJKtM0T6ImTV_6Lyv",
        "CurvaS_TOTAL_Aliwen.png":   "1OluidlF9M2SX-ObOBW9QxzRxvY5_G5aa",
    }
    return _ccu.load_drive_ids("aliwen", defaults)


def _save_drive_ids(ids):
    _ccu.save_drive_ids("aliwen", ids)


# ─────────────────────────────────────────────────────────────────────────────
# SINCRONIZAR GRUPOS DESDE '% Avance'
# En Aliwen el Gantt se llama '% Avance'. Beneficiario en col C (idx 2),
# INICIO en col H (idx 7). Dos secciones: la primera = GRUPO 1, la segunda = GRUPO 2.
# ─────────────────────────────────────────────────────────────────────────────
def sincronizar_grupos_desde_gantt(sheets_svc):
    log.info("Verificando movimientos de grupo en '% Avance' (Aliwen)...")

    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'% Avance'!A1:Z25",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    prog_rows = r.get("values", [])

    # Construir mapa: la primera sección 'GRUPO 1' -> GRUPO 1, segunda -> GRUPO 2
    gantt_map = {}
    grupo_counter = 0
    grupo_actual = None
    for row in prog_rows:
        if not row:
            continue
        cell_c = str(row[2]).strip().upper() if len(row) > 2 else ""
        if cell_c.startswith("GRUPO"):
            grupo_counter += 1
            grupo_actual = f"GRUPO {grupo_counter}"
            continue
        nombre_raw = str(row[2]).strip() if len(row) > 2 else ""
        inicio_raw = str(row[7]).strip() if len(row) > 7 else ""
        if not nombre_raw or not grupo_actual:
            continue
        try:
            float(nombre_raw.replace("%", "").replace(",", "."))
            continue
        except ValueError:
            pass
        if nombre_raw.upper() in ("BENEFICIARIO", "CARTA GANTT", "CORRE.", "PROGRAMA", ""):
            continue
        nombre_norm = _normalizar_nombre(nombre_raw)
        if nombre_norm:
            gantt_map[nombre_norm] = {"grupo": grupo_actual, "inicio": inicio_raw}

    if not gantt_map:
        log.warning("  No se pudo leer estructura de grupos desde '% Avance'.")
        return

    # Leer Datos Control actual
    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D15",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    dc_rows = dc.get("values", [])

    cambios = []
    for i, row in enumerate(dc_rows[4:], start=5):
        if len(row) < 2 or not row[0].strip() or not row[1].strip():
            continue
        grupo_dc = str(row[0]).strip().upper()
        nombre_norm = _normalizar_nombre(str(row[1]).strip())
        if nombre_norm in gantt_map:
            grupo_gantt = gantt_map[nombre_norm]["grupo"]
            inicio_gantt = gantt_map[nombre_norm]["inicio"]
            if grupo_dc != grupo_gantt:
                cambios.append({
                    "fila_sheet": i,
                    "nombre": row[1].strip(),
                    "grupo_anterior": grupo_dc,
                    "grupo_nuevo": grupo_gantt,
                    "inicio_nuevo": inicio_gantt,
                })

    if not cambios:
        log.info("  Sin movimientos de grupo detectados.")
        return

    log.info(f"  MOVIMIENTOS DETECTADOS ({len(cambios)}):")
    for c in cambios:
        log.info(f"    >> {c['nombre']}: {c['grupo_anterior']} -> {c['grupo_nuevo']}")

    # Aplicar cambios
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    dc_gid = next(s["properties"]["sheetId"] for s in meta["sheets"]
                  if s["properties"]["title"] == "Datos Control")

    requests = []
    for c in cambios:
        fila_idx = c["fila_sheet"] - 1
        requests.append({"updateCells": {
            "range": {"sheetId": dc_gid,
                      "startRowIndex": fila_idx, "endRowIndex": fila_idx + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{"userEnteredValue": {"stringValue": c["grupo_nuevo"]}}]}],
            "fields": "userEnteredValue"
        }})
        if c["inicio_nuevo"]:
            requests.append({"updateCells": {
                "range": {"sheetId": dc_gid,
                          "startRowIndex": fila_idx, "endRowIndex": fila_idx + 1,
                          "startColumnIndex": 2, "endColumnIndex": 3},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": c["inicio_nuevo"]}}]}],
                "fields": "userEnteredValue"
            }})

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
    ).execute()
    _reordenar_datos_control_aliwen(sheets_svc)
    log.info(f"  Datos Control actualizado con {len(cambios)} movimiento(s).")
    return cambios


def _reordenar_datos_control_aliwen(sheets_svc):
    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D15",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    rows = dc.get("values", [])
    header = rows[:4]
    datos = [r for r in rows[4:] if len(r) >= 2 and r[0].strip() and r[1].strip()]
    orden = ["GRUPO 1", "GRUPO 2"]
    datos_ord = sorted(datos, key=lambda r: (
        orden.index(str(r[0]).strip().upper()) if str(r[0]).strip().upper() in orden else 9, r[1]
    ))
    sheets_svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range="'Datos Control'!A1:D15"
    ).execute()
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": header + datos_ord},
    ).execute()
    log.info("  Datos Control reordenado.")


def leer_avance_appsheet():
    if not APPSHEET_DISPONIBLE:
        log.warning("Modulo leer_appsheet no disponible.")
        return None
    try:
        log.info("Leyendo avance desde AppSheet P38 (Aliwen)...")
        datos = leer_avance_p38()
        result = {_normalizar_nombre(k): v for k, v in datos.items()}
        log.info(f"  AppSheet P38: {len(result)} beneficiarios leidos.")
        return result
    except Exception as e:
        log.warning(f"AppSheet no disponible ({e}). Usando 'Datos Control'.")
        return None


def leer_datos_control(sheets_svc):
    """
    Lee la hoja 'Datos Control' de Aliwen.
    Fecha de control = hoy (automatica).
    % real = AppSheet P38 (o col D como fallback).
    """
    control_date = date.today()
    log.info(f"Fecha de control (hoy): {control_date.strftime('%d/%m/%Y')}")

    rng = "'Datos Control'!A1:D20"
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

        # % real: AppSheet tiene prioridad
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
# 3. LOGICA DE CURVAS S
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


def proyectar_fin(inicio, pct_real, control):
    if pct_real <= 10:
        return inicio + timedelta(days=DURACION_DIAS)
    inicio_ef  = min(inicio, control)
    dias_trans = max(1, (control - inicio_ef).days)
    tasa       = pct_real / dias_trans
    dias_rest  = (100 - pct_real) / tasa
    return control + timedelta(days=int(dias_rest))


def build_group_curves(beneficiarios, control):
    inicio_grupo   = min(b[1] for b in beneficiarios)
    fin_proyecto   = max(b[1] for b in beneficiarios) + timedelta(days=DURACION_DIAS)
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
# 4. GENERAR GRAFICOS
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_date(d):
    return d.strftime("%d/%m/%Y")


def generar_grafico_grupo(nombre_grupo, beneficiarios, control, outdir):
    color = COLORES.get(nombre_grupo, "#1a6eb5")
    fechas, prog, real_hist, proj, fin_proy = build_group_curves(beneficiarios, control)

    pct_real_avg  = np.mean([b[2] for b in beneficiarios])
    idx_ctrl      = (control - fechas[0]).days
    pct_prog_ctrl = prog[idx_ctrl] if 0 <= idx_ctrl < len(prog) else 0.0

    fig, ax = plt.subplots(figsize=(10, 5.1))  # 2000x1020 px @ 200 DPI
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
        f"Curva S - {nombre_grupo} - Proyecto Aliwen ({len(beneficiarios)} viviendas)\n"
        f"Inicio: {_fmt_date(min(b[1] for b in beneficiarios))}  |  "
        f"Fin Prog.: {_fmt_date(fin_prog_grupo)}  |  "
        f"Fin Proy.: {_fmt_date(fin_proy)}",
        fontsize=13, fontweight="bold", pad=12,
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
    slug = nombre_grupo.replace(" ", "_").upper()
    fname = Path(outdir) / f"CurvaS_{slug}_Aliwen.png"
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

    pct_real_total  = np.mean([b[2] for b in todos])
    idx_ctrl_total  = (control - inicio_total).days

    fig2, ax2 = plt.subplots(figsize=(10, 5.1))  # 2000x1020 px @ 200 DPI
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
            arrowprops=dict(arrowstyle="->", color="gray", lw=1.5),
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#fffbe6",
                      edgecolor="#ff7f0e", alpha=0.95),
        )

    ax2.set_xlim(fechas_total[0] - timedelta(days=7),
                 fechas_total[-1] + timedelta(days=7))
    ax2.set_ylim(-2, 108)
    ax2.set_ylabel("Avance promedio (%)", fontsize=13)
    ax2.set_xlabel("Fecha", fontsize=13)
    ax2.set_title(
        f"Curva S Total - Proyecto Aliwen P38 ({len(todos)} viviendas)\n"
        f"Inicio: {_fmt_date(inicio_total)}  |  "
        f"Fin Programado: {_fmt_date(fin_prog_total)}  |  "
        f"Fin Proyectado: {_fmt_date(fin_proy_total)}",
        fontsize=14, fontweight="bold", pad=14,
    )
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax2.grid(axis="y", alpha=0.4, linestyle="--")
    ax2.grid(axis="x", alpha=0.2, linestyle=":")
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.95)
    ax2.axvspan(fechas_total[0], control, alpha=0.03, color="green")
    ax2.axvspan(control, fechas_total[-1], alpha=0.03, color="red")

    plt.tight_layout()
    fname_total = Path(outdir) / "CurvaS_TOTAL_Aliwen.png"
    plt.savefig(fname_total, dpi=DPI_EXPORT, bbox_inches="tight")
    plt.close()
    log.info(f"  Grafico guardado: {fname_total.name}")


def generar_grafico_todos(grupos, control, fines_proy_global, outdir):
    from matplotlib.lines import Line2D
    fig3, ax3 = plt.subplots(figsize=(10, 5.1))
    ax3.set_facecolor("#f8f9fa"); fig3.patch.set_facecolor("#ffffff")
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
    ax3.axvline(control, color="#ff7f0e", linewidth=2.5, linestyle="-.", label="Fecha Control", zorder=5)
    legend_extra = [
        Line2D([0], [0], color="gray", linestyle="--", linewidth=1.5, label="Programado"),
        Line2D([0], [0], color="gray", linestyle="-",  linewidth=2.5, label="Real (suavizado)"),
        Line2D([0], [0], color="gray", linestyle=":",  linewidth=1.8, label="Proyectado"),
    ]
    handles, labels = ax3.get_legend_handles_labels()
    ax3.legend(handles=handles + legend_extra, loc="upper left", fontsize=9, framealpha=0.95)
    todos = [b for bens in grupos.values() for b in bens]
    inicio_ref = min(b[1] for b in todos)
    ax3.set_xlim(inicio_ref - timedelta(days=7), max(fines_proy_global) + timedelta(days=21))
    ax3.set_ylim(-2, 108)
    ax3.set_ylabel("Avance (%)", fontsize=12)
    ax3.set_xlabel("Fecha", fontsize=12)
    ax3.set_title(
        "Curva S por Grupo - Proyecto Aliwen\nContinua=Real  |  Discontinua=Programado  |  Punteado=Proyectado",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax3.grid(axis="y", alpha=0.4, linestyle="--"); ax3.grid(axis="x", alpha=0.2, linestyle=":")
    ax3.axvspan(inicio_ref, control, alpha=0.03, color="green")
    plt.tight_layout()
    fname = Path(outdir) / "CurvaS_Todos_Grupos_Aliwen.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Grafico guardado: {fname.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. REDIMENSIONAR
# ─────────────────────────────────────────────────────────────────────────────
def redimensionar(outdir):
    # Redimensionado desactivado: se sube en resolucion nativa para maxima calidad
    log.info("Resolucion nativa: sin redimensionado.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. INSERTAR IMAGENES EN HOJA 'Curvas S' via formula IMAGE()
# ─────────────────────────────────────────────────────────────────────────────
CURVAS_GID = 1509578683   # gid de la hoja 'Curvas S' en Aliwen


def insertar_imagenes_en_sheets(sheets_svc, drive_ids):
    """Actualiza las formulas IMAGE() en la hoja 'Curvas S' de Aliwen (4 imagenes, 2x2)."""
    log.info("Actualizando formulas IMAGE() en hoja 'Curvas S' Aliwen...")
    # Layout 2 columnas: GRUPO_1 | GRUPO_2 / TOTAL | Todos_Grupos
    layout = [
        ("CurvaS_GRUPO_1_Aliwen.png",       0, 0),
        ("CurvaS_GRUPO_2_Aliwen.png",        1, 0),
        ("CurvaS_TOTAL_Aliwen.png",          0, 1),
        ("CurvaS_Todos_Grupos_Aliwen.png",   1, 1),
    ]
    W_PX, H_PX = 755, 385
    n_cols = max(c for _, c, _ in layout) + 1
    n_rows = max(r for _, _, r in layout) + 1

    requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": CURVAS_GID, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": n_cols},
            "properties": {"pixelSize": W_PX}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": CURVAS_GID, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": n_rows},
            "properties": {"pixelSize": H_PX}, "fields": "pixelSize"
        }},
    ]
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for name, col, row in layout:
        fid = drive_ids.get(name, "")
        if not fid:
            continue
        url = f"https://drive.google.com/uc?id={fid}&export=view&v={ts}"
        requests.append({"updateCells": {
            "range": {"sheetId": CURVAS_GID,
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
# 7. SUBIR A DRIVE
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
        file_meta = {
            "name": name,
            "mimeType": "image/png",
        }
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
    nuevos_ids = {}
    for name in CHART_NAMES:
        path = Path(outdir) / name
        if not path.exists():
            log.warning(f"  No encontrado: {path}, saltando.")
            continue
        new_id = _crear_o_actualizar_drive(drive_svc, name, path, drive_ids)
        nuevos_ids[name] = new_id
    return nuevos_ids


# ─────────────────────────────────────────────────────────────────────────────
# 7. MARCAR PENDIENTE
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
    """Escribe % real actualizados de vuelta a 'Datos Control' col D (rango dinamico)."""
    valores = []
    for bens in grupos.values():
        for _, _, pct in bens:
            valores.append([round(pct)])
    if valores:
        n = len(valores)
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'Datos Control'!D5:D{4 + n}",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        log.info(f"  % real actualizados en 'Datos Control' ({n} filas)")


# ─────────────────────────────────────────────────────────────────────────────
# 8. MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 65)
    log.info(f"INICIO CURVAS S ALIWEN  -  {ts}")
    log.info("=" * 65)

    try:
        creds      = get_credentials()
        sheets_svc = build("sheets", "v4", credentials=creds)
        drive_svc  = build("drive",  "v3", credentials=creds)

        # Sincronizar grupos desde '% Avance'
        sincronizar_grupos_desde_gantt(sheets_svc)

        # Leer datos
        control_date, grupos = leer_datos_control(sheets_svc)

        # Actualizar % en hoja (para que quede registro)
        actualizar_pct_en_hoja(sheets_svc, grupos)

        # Crear carpeta de salida
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

        # Generar graficos
        log.info("Generando graficos Aliwen...")
        fines_proy_global = []
        for nombre_grupo, beneficiarios in grupos.items():
            _, _, _, fin_proy = generar_grafico_grupo(
                nombre_grupo, beneficiarios, control_date, OUTPUT_DIR
            )
            fines_proy_global.append(fin_proy)

        generar_grafico_total(grupos, control_date, fines_proy_global, OUTPUT_DIR)
        generar_grafico_todos(grupos, control_date, fines_proy_global, OUTPUT_DIR)

        # Redimensionar
        redimensionar(OUTPUT_DIR)

        # Subir a Drive (usando JSON)
        drive_ids = _load_drive_ids()
        nuevos_ids = actualizar_drive(drive_svc, OUTPUT_DIR, drive_ids)
        drive_ids.update(nuevos_ids)
        _save_drive_ids(drive_ids)

        # Insertar/actualizar imagenes en hoja 'Curvas S'
        insertar_imagenes_en_sheets(sheets_svc, drive_ids)

        # Marcar pendiente
        marcar_pendiente(sheets_svc, ts)

        log.info("=" * 65)
        log.info("COMPLETADO. Apps Script actualizara imagenes en Sheets.")
        log.info("=" * 65)

        return nuevos_ids

    except Exception:
        log.error("ERROR:\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

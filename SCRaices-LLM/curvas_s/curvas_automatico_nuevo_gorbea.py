"""
curvas_automatico_nuevo_gorbea.py  -  Automatizacion semanal Curvas S - Proyecto P129 Nuevo Gorbea
==================================================================================================
- Fecha de control:  date.today() (automatica)
- Datos de avance:   leidos desde AppSheet (proyecto P129)
  Fallback:          hoja 'Datos Control' del spreadsheet Gantt Control (si existe)
  Fallback 2:        BENEFICIARIOS_SETUP (inicio hardcodeado, % = 0)
- Genera 6 graficos PNG (4 grupos + total + todos grupos)
- Actualiza Drive, marca PENDIENTE para Apps Script (si existe hoja Datos Control)

Ejecucion manual:  python curvas_automatico_nuevo_gorbea.py
"""

import sys
import traceback
from pathlib import Path
from datetime import date, timedelta, datetime

try:
    from leer_appsheet import leer_avance_proyecto
    APPSHEET_DISPONIBLE = True
except ImportError:
    APPSHEET_DISPONIBLE = False

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.special import expit
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import curvas_cloud_utils as _ccu

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────
SPREADSHEET_ID   = "1M8nyOgKhawPfHMEylHHxJWlz_YqR0M7eVxAqVaOp98E"
APPSHEET_PROJECT = "P129"
TOKEN_FILE       = _ccu.TOKEN_FILE
OBRA_FOLDER      = "Nuevo Gorbea"
OUTPUT_DIR       = _ccu.get_output_dir_obra(OBRA_FOLDER)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DPI_EXPORT    = 200
DATOS_CONTROL = "Datos Control"
CURVA_S_SHEET = "Curva S"

# Curva S programada semanal (36 semanas = 252 dias)
PCT_SEMANA    = [round(i * 100 / 36, 2) for i in range(37)]
DURACION_DIAS = 252

COLORES = {
    "GRUPO 1": "#1a6eb5",
    "GRUPO 2": "#e07b00",
    "GRUPO 3": "#2ca02c",
    "GRUPO 4": "#9467bd",
}

CHART_NAMES = [
    "CurvaS_GRUPO_1_Gorbea.png",
    "CurvaS_GRUPO_2_Gorbea.png",
    "CurvaS_GRUPO_3_Gorbea.png",
    "CurvaS_GRUPO_4_Gorbea.png",
    "CurvaS_TOTAL_Gorbea.png",
    "CurvaS_Todos_Grupos_Gorbea.png",
]

# Datos hardcodeados desde Gantt; usados como fallback cuando Datos Control no existe
BENEFICIARIOS_SETUP = [
    # GRUPO 1
    ("GRUPO 1", "Adelmo Agustín Obreque Kulman",           "16/11/2026"),
    ("GRUPO 1", "Oscar Antonio Gutiérrez Garrido",         "16/11/2026"),
    ("GRUPO 1", "Sandra Magdalena Hernández Hernández",    "23/11/2026"),
    # GRUPO 2
    ("GRUPO 2", "Annegret Margarita Barra Aravena",        "30/11/2026"),
    ("GRUPO 2", "Nolvia Flora Campos Rivera",              "30/11/2026"),
    # GRUPO 3
    ("GRUPO 3", "Ricardo Patricio Zavala Vásquez",         "07/12/2026"),
    ("GRUPO 3", "Constanza Daniela De La Barra Candia",    "14/12/2026"),
    ("GRUPO 3", "Maria Islanda Osses Gatica",              "21/12/2026"),
    # GRUPO 4
    ("GRUPO 4", "Juana Rosa Fajardo",                      "28/12/2026"),
    ("GRUPO 4", "Patricia Dolores Millar Echeverría",      "28/12/2026"),
    ("GRUPO 4", "Vilma Loreto Gutiérrez Carrasco",         "04/01/2027"),
]

log = _ccu.setup_logging("nuevo_gorbea")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _normalizar_nombre(nombre):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())

def _load_drive_ids():
    return _ccu.load_drive_ids("nuevo_gorbea", {})

def _save_drive_ids(ids):
    _ccu.save_drive_ids("nuevo_gorbea", ids)

def get_credentials():
    return _ccu.get_credentials(SCOPES)


# ─────────────────────────────────────────────────────────────────────────────
# SINCRONIZAR GRUPOS DESDE GANTT
# ─────────────────────────────────────────────────────────────────────────────
def sincronizar_grupos_desde_gantt(sheets_svc):
    log.info("Verificando movimientos de grupo en 'Programa de obra' (Nuevo Gorbea)...")
    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Programa de obra'!A1:L35",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    prog_rows = r.get("values", [])

    gantt_map = {}
    grupo_counter = 0
    grupo_actual  = None
    for row in prog_rows:
        if not row:
            continue
        cell_d = str(row[3]).strip().upper() if len(row) > 3 else ""
        if cell_d.startswith("GRUPO") and len(cell_d) <= 8:
            grupo_counter += 1
            grupo_actual = f"GRUPO {grupo_counter}"
            continue
        nombre_raw = str(row[3]).strip() if len(row) > 3 else ""
        inicio_raw = str(row[10]).strip() if len(row) > 10 else ""
        if not nombre_raw or not grupo_actual:
            continue
        skip = ("BENEFICIARIO", "CARTA GANTT", "CORRE.", "PROGRAMA", "", "CANT", "RUT")
        if nombre_raw.upper() in skip or nombre_raw[0].isdigit():
            continue
        try:
            float(nombre_raw.replace("%", "").replace(",", "."))
            continue
        except ValueError:
            pass
        gantt_map[_normalizar_nombre(nombre_raw)] = {"grupo": grupo_actual, "inicio": inicio_raw}

    if not gantt_map:
        log.warning("  No se pudo leer estructura desde 'Programa de obra'.")
        return

    # Leer Datos Control solo si existe
    try:
        dc = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{DATOS_CONTROL}'!A1:D20",
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        dc_rows = dc.get("values", [])
    except Exception:
        log.info("  Sin movimientos de grupo detectados.")
        return

    cambios = []
    for i, row in enumerate(dc_rows[4:], start=5):
        if len(row) < 2 or not str(row[0]).strip() or not str(row[1]).strip():
            continue
        grupo_dc    = str(row[0]).strip().upper()
        nombre_norm = _normalizar_nombre(str(row[1]).strip())
        if nombre_norm in gantt_map and grupo_dc != gantt_map[nombre_norm]["grupo"]:
            cambios.append({
                "fila_sheet": i,
                "nombre": str(row[1]).strip(),
                "grupo_anterior": grupo_dc,
                "grupo_nuevo": gantt_map[nombre_norm]["grupo"],
                "inicio_nuevo": gantt_map[nombre_norm]["inicio"],
            })

    if not cambios:
        log.info("  Sin movimientos de grupo detectados.")
        return

    meta   = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    dc_gid = next(s["properties"]["sheetId"] for s in meta["sheets"]
                  if s["properties"]["title"] == DATOS_CONTROL)

    requests_list = []
    for c in cambios:
        fi = c["fila_sheet"] - 1
        log.info(f"    >> {c['nombre']}: {c['grupo_anterior']} -> {c['grupo_nuevo']}")
        requests_list.append({"updateCells": {
            "range": {"sheetId": dc_gid, "startRowIndex": fi, "endRowIndex": fi + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{"userEnteredValue": {"stringValue": c["grupo_nuevo"]}}]}],
            "fields": "userEnteredValue"
        }})
        if c["inicio_nuevo"]:
            requests_list.append({"updateCells": {
                "range": {"sheetId": dc_gid, "startRowIndex": fi, "endRowIndex": fi + 1,
                          "startColumnIndex": 2, "endColumnIndex": 3},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": c["inicio_nuevo"]}}]}],
                "fields": "userEnteredValue"
            }})
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests_list}
    ).execute()
    log.info(f"  Datos Control actualizado con {len(cambios)} movimiento(s).")


# ─────────────────────────────────────────────────────────────────────────────
# LEER DATOS
# ─────────────────────────────────────────────────────────────────────────────
def leer_avance_appsheet():
    if not APPSHEET_DISPONIBLE:
        log.warning("Modulo leer_appsheet no disponible.")
        return None
    try:
        log.info(f"Leyendo avance desde AppSheet {APPSHEET_PROJECT} (Nuevo Gorbea)...")
        datos  = leer_avance_proyecto(APPSHEET_PROJECT)
        result = {_normalizar_nombre(k): v for k, v in datos.items()}
        log.info(f"  AppSheet {APPSHEET_PROJECT}: {len(result)} beneficiarios leidos.")
        return result
    except Exception as e:
        log.warning(f"AppSheet no disponible ({e}). Usando '{DATOS_CONTROL}'.")
        return None


def _grupos_desde_setup(avance_appsheet):
    """Construye grupos desde BENEFICIARIOS_SETUP (fallback cuando Datos Control no existe)."""
    grupos    = {}
    sin_match = []
    for grupo_raw, nombre, inicio_str in BENEFICIARIOS_SETUP:
        inicio = datetime.strptime(inicio_str, "%d/%m/%Y").date()
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
                pct = 0.0
        else:
            pct = 0.0
        grupos.setdefault(grupo_raw, []).append((nombre, inicio, float(pct)))
    if sin_match:
        log.warning(f"Sin match AppSheet: {', '.join(sin_match)}")
    return grupos


def leer_datos_control(sheets_svc):
    control_date = date.today()
    log.info(f"Fecha de control (hoy): {control_date.strftime('%d/%m/%Y')}")

    avance_appsheet = leer_avance_appsheet()

    # Intentar leer Datos Control; si no existe usar BENEFICIARIOS_SETUP
    rows = []
    try:
        result = sheets_svc.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{DATOS_CONTROL}'!A1:D20",
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute()
        rows = result.get("values", [])
    except Exception as e:
        log.warning(f"Hoja '{DATOS_CONTROL}' no disponible. Usando BENEFICIARIOS_SETUP.")

    if not rows:
        grupos = _grupos_desde_setup(avance_appsheet)
        fuente = "AppSheet" if avance_appsheet else "BENEFICIARIOS_SETUP (0%)"
        log.info(f"Beneficiarios: {sum(len(v) for v in grupos.values())} "
                 f"en {len(grupos)} grupos | avance desde: {fuente}")
        return control_date, grupos

    # Path normal: leer desde Datos Control
    grupos    = {}
    sin_match = []
    _SHEETS_EPOCH = date(1899, 12, 30)

    for row in rows[4:]:
        if len(row) < 3:
            continue
        grupo_raw  = str(row[0]).strip()
        nombre     = str(row[1]).strip()
        inicio_raw = row[2]
        pct_hoja   = row[3] if len(row) > 3 else 0

        if not grupo_raw or not nombre:
            continue
        if nombre.upper().startswith("GRUPO"):
            continue

        if isinstance(inicio_raw, (int, float)):
            inicio = _SHEETS_EPOCH + timedelta(days=int(inicio_raw))
        else:
            inicio_s = str(inicio_raw).strip()
            inicio   = None
            for _fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    inicio = datetime.strptime(inicio_s, _fmt).date()
                    break
                except ValueError:
                    continue
            if inicio is None:
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

    fuente = "AppSheet" if avance_appsheet else f"'{DATOS_CONTROL}'"
    log.info(f"Beneficiarios: {sum(len(v) for v in grupos.values())} "
             f"en {len(grupos)} grupos | avance desde: {fuente}")
    return control_date, grupos


# ─────────────────────────────────────────────────────────────────────────────
# LOGICA CURVAS S
# ─────────────────────────────────────────────────────────────────────────────
def pct_programada(dia):
    if dia <= 0:
        return 0.0
    semana = dia / 7.0
    idx    = int(semana)
    frac   = semana - idx
    if idx >= len(PCT_SEMANA) - 1:
        return 100.0
    return PCT_SEMANA[idx] + frac * (PCT_SEMANA[idx + 1] - PCT_SEMANA[idx])

def s_curve_real(t_days, pct_real, t_control):
    if t_control <= 0 or pct_real == 0:
        return 0.0
    t_norm  = t_days / t_control
    k       = 8.0
    val     = expit(k * (t_norm - 0.5))
    val_max = expit(k * 0.5)
    val_min = expit(k * (-0.5))
    return float(np.clip((val - val_min) / (val_max - val_min) * pct_real, 0, pct_real))

def proyectar_fin(inicio, pct_real, control):
    if pct_real <= 10:
        return inicio + timedelta(days=DURACION_DIAS)
    dias_trans = max(1, (control - min(inicio, control)).days)
    tasa       = pct_real / dias_trans
    return control + timedelta(days=int((100 - pct_real) / tasa))

def build_group_curves(beneficiarios, control):
    inicio_grupo   = min(b[1] for b in beneficiarios)
    fin_proyecto   = max(b[1] for b in beneficiarios) + timedelta(days=DURACION_DIAS)
    fines_real     = [proyectar_fin(b[1], b[2], control) for b in beneficiarios]
    fin_proyectado = max(fines_real)
    fecha_fin      = max(fin_proyecto, fin_proyectado) + timedelta(days=14)
    fechas         = [inicio_grupo + timedelta(days=d)
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
# GRAFICOS
# ─────────────────────────────────────────────────────────────────────────────
def _fmt_date(d):
    return d.strftime("%d/%m/%Y")

def generar_grafico_grupo(nombre_grupo, beneficiarios, control, outdir, pct_prog_gantt=None):
    color  = COLORES.get(nombre_grupo, "#1a6eb5")
    fechas, prog, real_hist, proj, fin_proy = build_group_curves(beneficiarios, control)
    pct_real_avg  = np.mean([b[2] for b in beneficiarios])
    idx_ctrl      = (control - fechas[0]).days
    pct_prog_ctrl = (pct_prog_gantt if pct_prog_gantt is not None
                     else (prog[idx_ctrl] if 0 <= idx_ctrl < len(prog) else 0.0))

    fig, ax = plt.subplots(figsize=(10, 5.1))
    ax.set_facecolor("#f8f9fa"); fig.patch.set_facecolor("#ffffff")

    ax.plot(fechas, prog, color="#1f77b4", linewidth=2.5, linestyle="--", label="% Programado", zorder=3)
    rf = [f for f, v in zip(fechas, real_hist) if v is not None]
    rv = [v for v in real_hist if v is not None]
    ax.plot(rf, rv, color=color, linewidth=3, label="% Real (suavizado)", zorder=4)
    pf = [f for f, v in zip(fechas, proj) if v is not None]
    pv = [v for v in proj if v is not None]
    ax.plot(pf, pv, color="#d62728", linewidth=2, linestyle=":", label="% Proyectado", zorder=3)

    ax.axvline(control, color="#ff7f0e", linewidth=2, linestyle="-.",
               label=f"Fecha Control ({_fmt_date(control)})", zorder=5)
    if fin_proy <= fechas[-1]:
        ax.axvline(fin_proy, color="#9467bd", linewidth=1.5, linestyle=":",
                   label=f"Termino Proyectado ({_fmt_date(fin_proy)})", zorder=4)

    if 0 <= idx_ctrl < len(prog):
        diff = pct_real_avg - pct_prog_ctrl
        ax.annotate(
            f"Prog: {pct_prog_ctrl:.1f}%\nReal: {pct_real_avg:.1f}%\nDesv: {'+' if diff>=0 else ''}{diff:.1f}%",
            xy=(control, pct_prog_ctrl),
            xytext=(control + timedelta(days=21), max(5, pct_prog_ctrl + 8)),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6", edgecolor="#ff7f0e", alpha=0.95),
        )

    fin_prog_grupo = max(b[1] for b in beneficiarios) + timedelta(days=DURACION_DIAS)
    ax.set_xlim(fechas[0] - timedelta(days=7), fechas[-1] + timedelta(days=7))
    ax.set_ylim(-2, 108)
    ax.set_ylabel("Avance (%)", fontsize=12); ax.set_xlabel("Fecha", fontsize=12)
    ax.set_title(
        f"Curva S - {nombre_grupo} - Nuevo Gorbea P129 ({len(beneficiarios)} viviendas)\n"
        f"Inicio: {_fmt_date(min(b[1] for b in beneficiarios))}  |  "
        f"Fin Prog.: {_fmt_date(fin_prog_grupo)}  |  Fin Proy.: {_fmt_date(fin_proy)}",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.grid(axis="y", alpha=0.4, linestyle="--"); ax.grid(axis="x", alpha=0.2, linestyle=":")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax.axvspan(fechas[0], control, alpha=0.04, color="green")
    ax.axvspan(control, fechas[-1], alpha=0.04, color="red")
    plt.tight_layout()

    slug  = nombre_grupo.replace(" ", "_").upper()
    fname = Path(outdir) / f"CurvaS_{slug}_Gorbea.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Grafico guardado: {fname.name}")
    return pct_real_avg, pct_prog_ctrl, min(b[1] for b in beneficiarios), fin_proy


def generar_grafico_total(grupos, control, fines_proy_global, outdir, pct_prog_gantt_total=None):
    todos          = [b for bens in grupos.values() for b in bens]
    inicio_total   = min(b[1] for b in todos)
    fin_prog_total = max(b[1] for b in todos) + timedelta(days=DURACION_DIAS)
    fin_proy_total = max(fines_proy_global)
    fecha_fin_t    = max(fin_prog_total, fin_proy_total) + timedelta(days=14)
    fechas_t       = [inicio_total + timedelta(days=d)
                      for d in range((fecha_fin_t - inicio_total).days + 1)]

    prog_t, real_t, proj_t = [], [], []
    for fecha in fechas_t:
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
        prog_t.append(np.mean(vp))
        real_t.append(np.mean(vr) if vr else None)
        proj_t.append(np.mean(vproj) if vproj else None)

    pct_real_total = np.mean([b[2] for b in todos])
    idx_ctrl_t     = (control - inicio_total).days

    fig2, ax2 = plt.subplots(figsize=(10, 5.1))
    ax2.set_facecolor("#f8f9fa"); fig2.patch.set_facecolor("#ffffff")
    ax2.plot(fechas_t, prog_t, color="#1f77b4", linewidth=3, linestyle="--", label="% Programado Total", zorder=3)
    rt_f = [f for f, v in zip(fechas_t, real_t) if v is not None]
    rt_v = [v for v in real_t if v is not None]
    ax2.plot(rt_f, rt_v, color="#2ca02c", linewidth=3.5, label="% Real Total (suavizado)", zorder=4)
    pt_f = [f for f, v in zip(fechas_t, proj_t) if v is not None]
    pt_v = [v for v in proj_t if v is not None]
    ax2.plot(pt_f, pt_v, color="#d62728", linewidth=2.5, linestyle=":", label="% Proyectado Total", zorder=3)
    ax2.axvline(control, color="#ff7f0e", linewidth=2.5, linestyle="-.",
                label=f"Fecha Control ({_fmt_date(control)})", zorder=5)
    ax2.axvline(fin_proy_total, color="#9467bd", linewidth=2, linestyle=":",
                label=f"Termino Proyectado ({_fmt_date(fin_proy_total)})", zorder=4)
    ax2.axvline(fin_prog_total, color="#1f77b4", linewidth=1.5, linestyle=":", alpha=0.6,
                label=f"Termino Programado ({_fmt_date(fin_prog_total)})", zorder=3)

    if 0 <= idx_ctrl_t < len(prog_t):
        prog_en_ctrl = pct_prog_gantt_total if pct_prog_gantt_total is not None else prog_t[idx_ctrl_t]
        diff = pct_real_total - prog_en_ctrl
        ax2.annotate(
            f"Prog:  {prog_en_ctrl:.1f}%\nReal:  {pct_real_total:.1f}%\n"
            f"Desv: {'+' if diff>=0 else ''}{diff:.1f}%",
            xy=(control, prog_en_ctrl),
            xytext=(control + timedelta(days=21), prog_en_ctrl + 10),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="gray", lw=1.5),
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#fffbe6", edgecolor="#ff7f0e", alpha=0.95),
        )

    ax2.set_xlim(fechas_t[0] - timedelta(days=7), fechas_t[-1] + timedelta(days=7))
    ax2.set_ylim(-2, 108)
    ax2.set_ylabel("Avance promedio (%)", fontsize=13); ax2.set_xlabel("Fecha", fontsize=13)
    ax2.set_title(
        f"Curva S Total - Nuevo Gorbea P129 ({len(todos)} viviendas)\n"
        f"Inicio: {_fmt_date(inicio_total)}  |  Fin Programado: {_fmt_date(fin_prog_total)}  |  "
        f"Fin Proyectado: {_fmt_date(fin_proy_total)}",
        fontsize=14, fontweight="bold", pad=14,
    )
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax2.grid(axis="y", alpha=0.4, linestyle="--"); ax2.grid(axis="x", alpha=0.2, linestyle=":")
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.95)
    ax2.axvspan(fechas_t[0], control, alpha=0.03, color="green")
    ax2.axvspan(control, fechas_t[-1], alpha=0.03, color="red")
    plt.tight_layout()
    fname_t = Path(outdir) / "CurvaS_TOTAL_Gorbea.png"
    plt.savefig(fname_t, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Grafico guardado: {fname_t.name}")


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
    todos      = [b for bens in grupos.values() for b in bens]
    inicio_ref = min(b[1] for b in todos)
    ax3.set_xlim(inicio_ref - timedelta(days=7), max(fines_proy_global) + timedelta(days=21))
    ax3.set_ylim(-2, 108)
    ax3.set_ylabel("Avance (%)", fontsize=12); ax3.set_xlabel("Fecha", fontsize=12)
    ax3.set_title(
        "Curva S por Grupo - Nuevo Gorbea P129\n"
        "Continua=Real  |  Discontinua=Programado  |  Punteado=Proyectado",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax3.grid(axis="y", alpha=0.4, linestyle="--"); ax3.grid(axis="x", alpha=0.2, linestyle=":")
    ax3.axvspan(inicio_ref, control, alpha=0.03, color="green")
    plt.tight_layout()
    fname = Path(outdir) / "CurvaS_Todos_Grupos_Gorbea.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Grafico guardado: {fname.name}")


# ─────────────────────────────────────────────────────────────────────────────
# DRIVE
# ─────────────────────────────────────────────────────────────────────────────
def actualizar_drive(drive_svc, outdir, drive_ids=None):
    return _ccu.actualizar_drive_organizado(drive_svc, outdir, CHART_NAMES, OBRA_FOLDER, "nuevo_gorbea")


# ─────────────────────────────────────────────────────────────────────────────
# SHEETS: IMAGENES Y FLAGS
# ─────────────────────────────────────────────────────────────────────────────
def insertar_imagenes_en_sheets(sheets_svc, drive_ids):
    log.info(f"Actualizando formulas IMAGE() en hoja '{CURVA_S_SHEET}' Nuevo Gorbea...")
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    curva_gid = next(
        (s["properties"]["sheetId"] for s in meta["sheets"]
         if s["properties"]["title"] == CURVA_S_SHEET),
        None
    )
    if curva_gid is None:
        log.warning(f"Hoja '{CURVA_S_SHEET}' no encontrada. Se omite insercion de imagenes.")
        return

    W_PX, H_PX = 755, 385
    layout = [
        ("CurvaS_GRUPO_1_Gorbea.png",      0, 0),
        ("CurvaS_GRUPO_2_Gorbea.png",      1, 0),
        ("CurvaS_GRUPO_3_Gorbea.png",      0, 1),
        ("CurvaS_GRUPO_4_Gorbea.png",      1, 1),
        ("CurvaS_TOTAL_Gorbea.png",        0, 2),
        ("CurvaS_Todos_Grupos_Gorbea.png", 1, 2),
    ]
    n_cols = max(c for _, c, _ in layout) + 1
    n_rows = max(r for _, _, r in layout) + 1

    requests_list = [
        {"updateDimensionProperties": {
            "range": {"sheetId": curva_gid, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": n_cols},
            "properties": {"pixelSize": W_PX}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": curva_gid, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": n_rows},
            "properties": {"pixelSize": H_PX}, "fields": "pixelSize"
        }},
    ]
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for name, col, row in layout:
        fid = drive_ids.get(name, "")
        if not fid:
            continue
        url = f"https://drive.google.com/thumbnail?id={fid}&sz=w2000&v={ts}"
        requests_list.append({"updateCells": {
            "range": {"sheetId": curva_gid,
                      "startRowIndex": row, "endRowIndex": row + 1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rows": [{"values": [{"userEnteredValue": {"formulaValue": f'=IMAGE("{url}",1)'}}]}],
            "fields": "userEnteredValue"
        }})
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests_list}
    ).execute()
    log.info(f"  {len(layout)} formulas IMAGE() actualizadas (v={ts}).")


def actualizar_pct_en_hoja(sheets_svc, grupos):
    """Escribe % real en col D. OBLIGATORIO: round(pct, 2)."""
    valores = []
    for bens in grupos.values():
        for _, _, pct in bens:
            valores.append([round(pct, 2)])
    if not valores:
        return
    n = len(valores)
    try:
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{DATOS_CONTROL}'!D5:D{4 + n}",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        log.info(f"  % real actualizados en '{DATOS_CONTROL}' ({n} filas)")
    except Exception as e:
        log.warning(f"  No se pudo actualizar '{DATOS_CONTROL}': {e}")


def marcar_pendiente(sheets_svc, timestamp_str):
    control_str = date.today().strftime("%d/%m/%Y")
    try:
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{DATOS_CONTROL}'!A1:B2",
            valueInputOption="USER_ENTERED",
            body={"values": [
                ["ESTADO",        f"PENDIENTE - {timestamp_str}"],
                ["FECHA_CONTROL", control_str],
            ]},
        ).execute()
        log.info(f"Flag PENDIENTE escrito | FECHA_CONTROL={control_str}")
    except Exception as e:
        log.warning(f"  No se pudo marcar PENDIENTE ('{DATOS_CONTROL}' no existe): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 65)
    log.info(f"INICIO CURVAS S NUEVO GORBEA P129  -  {ts}")
    log.info("=" * 65)

    try:
        creds      = get_credentials()
        sheets_svc = build("sheets", "v4", credentials=creds)
        drive_svc  = build("drive",  "v3", credentials=creds)

        sincronizar_grupos_desde_gantt(sheets_svc)
        control_date, grupos = leer_datos_control(sheets_svc)
        actualizar_pct_en_hoja(sheets_svc, grupos)

        pct_gantt_grupos = _ccu.leer_pct_gantt_grupos(
            sheets_svc, SPREADSHEET_ID, control_date,
            gantt_sheet="Programa de obra"
        )

        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

        log.info("Generando graficos Nuevo Gorbea P129...")
        fines_proy_global = []
        for nombre_grupo, beneficiarios in grupos.items():
            pct_gantt = (pct_gantt_grupos or {}).get(nombre_grupo.upper())
            _, _, _, fin_proy = generar_grafico_grupo(
                nombre_grupo, beneficiarios, control_date, OUTPUT_DIR,
                pct_prog_gantt=pct_gantt
            )
            fines_proy_global.append(fin_proy)

        generar_grafico_total(grupos, control_date, fines_proy_global, OUTPUT_DIR,
                              pct_prog_gantt_total=(pct_gantt_grupos or {}).get("TOTAL"))
        generar_grafico_todos(grupos, control_date, fines_proy_global, OUTPUT_DIR)

        drive_ids  = _load_drive_ids()
        nuevos_ids = actualizar_drive(drive_svc, OUTPUT_DIR, drive_ids)
        drive_ids.update(nuevos_ids)
        _save_drive_ids(drive_ids)

        insertar_imagenes_en_sheets(sheets_svc, drive_ids)
        marcar_pendiente(sheets_svc, ts)

        log.info("=" * 65)
        log.info("COMPLETADO. Charts generados y subidos a Drive.")
        log.info("=" * 65)

        return nuevos_ids

    except Exception:
        log.error("ERROR:\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

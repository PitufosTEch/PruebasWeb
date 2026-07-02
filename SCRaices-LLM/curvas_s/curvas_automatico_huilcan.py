"""
curvas_automatico_huilcan.py  —  Curvas S automáticas · Juan Huilcan Tolten (P12)
===================================================================================
- Fecha de control: date.today()
- Datos de avance: AppSheet P12 (fallback: hoja 'Datos Control')
- 1 grupo · 10 beneficiarios
- Genera 3 PNGs: GRUPO 1 + total + todos grupos
- Actualiza Google Drive y hoja 'Curvas S' en el Gantt de control
"""

import os, sys, logging, traceback, json
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
from matplotlib.lines import Line2D
from scipy.special import expit
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import curvas_cloud_utils as _ccu
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────
SPREADSHEET_ID   = "1SLu5lQTAzhHOUuorM3jbxSBes7vMyIB9mMXCihQ6A40"
APPSHEET_PROJECT = "P12"
TOKEN_FILE     = _ccu.TOKEN_FILE
OUTPUT_DIR     = _ccu.get_output_dir()
DRIVE_IDS_FILE = None  # gestionado por _ccu (Firebase en cloud, JSON en local)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DPI_EXPORT = 200  # 10"×5.1" → 2000×1020 px

# Curva S programada (245 días = 35 semanas)
PCT_SEMANA = [0, 4, 7, 11, 14, 18, 21, 25, 29, 32, 36, 39, 43, 46, 50,
              54, 57, 61, 64, 68, 71, 75, 79, 82, 86, 89, 93, 96, 100, 100]
DURACION_DIAS = 245

COLORES = {
    "GRUPO 1": "#1a6eb5",
}

CHART_NAMES = [
    "CurvaS_GRUPO_1_Huilcan.png",
    "CurvaS_TOTAL_Huilcan.png",
    "CurvaS_Todos_Grupos_Huilcan.png",
]

BENEFICIARIOS_SETUP = [
    ("FELIX ANTONIO BLANCO QUILAQUEO",       "GRUPO 1", "01/03/2026"),
    ("SARA HORTENCIA CANIUMIL QUINTANA",     "GRUPO 1", "01/03/2026"),
    ("CESAR MAMERTO LIENCURA NANCO",         "GRUPO 1", "08/03/2026"),
    ("VICTOR GRACIANO ANTINAO LLANCALEO",    "GRUPO 1", "08/03/2026"),
    ("RENE BELARMINO ANTINAO LLANCALEO",     "GRUPO 1", "15/03/2026"),
    ("IVAN HERIBERTO ANTINAO LLANCALEO",     "GRUPO 1", "15/03/2026"),
    ("JOSE ALEJANDRO HUIRCAN CARMONA",       "GRUPO 1", "22/03/2026"),
    ("FIDEL MARCEDONIO HUIRCAN PORMA",       "GRUPO 1", "22/03/2026"),
    ("JUAN EGILDO LLANCACURA LLANCALEO",     "GRUPO 1", "29/03/2026"),
    ("ANDRES ALEJANDRO EPUL LINCURA",        "GRUPO 1", "29/03/2026"),
]

# ─────────────────────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────────────────────
log = _ccu.setup_logging("huilcan")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CREDENCIALES
# ─────────────────────────────────────────────────────────────────────────────
def get_credentials():
    return _ccu.get_credentials(SCOPES)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SETUP HOJAS (primera ejecución)
# ─────────────────────────────────────────────────────────────────────────────
def setup_hojas(sheets_svc):
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existentes = {s["properties"]["title"] for s in meta["sheets"]}
    requests = []

    if "Datos Control" not in existentes:
        requests.append({"addSheet": {"properties": {"title": "Datos Control"}}})
    if "Curvas S" not in existentes:
        requests.append({"addSheet": {"properties": {"title": "Curvas S"}}})

    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
        ).execute()
        log.info("Hojas 'Datos Control' y 'Curvas S' creadas.")

    check = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="'Datos Control'!A1"
    ).execute()
    if not check.get("values"):
        rows = [
            ["ESTADO", "PENDIENTE"],
            ["FECHA_CONTROL", date.today().strftime("%d/%m/%Y")],
            [],
            ["GRUPO", "BENEFICIARIO", "INICIO (DD/MM/YYYY)", "% REAL"],
        ]
        for nombre, grupo, inicio in BENEFICIARIOS_SETUP:
            rows.append([grupo, nombre, inicio, 0])
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="'Datos Control'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        log.info(f"'Datos Control' poblada con {len(BENEFICIARIOS_SETUP)} beneficiarios.")


# ─────────────────────────────────────────────────────────────────────────────
# 2b. SINCRONIZAR GRUPOS DESDE GANTT
# ─────────────────────────────────────────────────────────────────────────────
def _get_dc_gid(sheets_svc):
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Datos Control":
            return s["properties"]["sheetId"]
    return 0


def _reordenar_datos_control(sheets_svc):
    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D50",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    rows = dc.get("values", [])
    header = rows[:4]
    datos = [r for r in rows[4:] if len(r) >= 2 and r[0].strip() and r[1].strip()]

    orden_grupos = ["GRUPO 1"]

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
    log.info("  Datos Control reordenado.")


def sincronizar_grupos_desde_gantt(sheets_svc):
    log.info("Verificando movimientos de grupo en 'Programa de obra'...")

    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Programa de obra'!A1:L60",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    prog_rows = r.get("values", [])

    grupo_actual = None
    gantt_map = {}
    for row in prog_rows:
        if not row:
            continue
        # GRUPO headers en idx 3 (col D)
        for col_idx in [3, 0, 2]:
            if col_idx < len(row):
                cell = str(row[col_idx]).strip().upper()
                if cell.startswith("GRUPO"):
                    grupo_actual = cell
                    break
        nombre_raw = str(row[3]).strip() if len(row) > 3 else ""
        # INICIO en idx 8 (col I)
        inicio_raw = str(row[8]).strip() if len(row) > 8 else ""
        if (not nombre_raw or nombre_raw.upper().startswith("GRUPO")
                or nombre_raw.upper() in ("BENEFICIARIO", "CARTA GANTT", "")
                or not grupo_actual):
            continue
        try:
            float(nombre_raw.replace("%", "").replace(",", "."))
            continue
        except ValueError:
            pass
        nombre_norm = _normalizar_nombre(nombre_raw)
        if nombre_norm:
            gantt_map[nombre_norm] = {"grupo": grupo_actual, "inicio": inicio_raw}

    if not gantt_map:
        log.warning("  No se pudo leer estructura desde 'Programa de obra'.")
        return

    dc = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D50",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    dc_rows = dc.get("values", [])

    cambios = []
    for i, row in enumerate(dc_rows[4:], start=5):
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
                    "fila_sheet": i,
                    "nombre": nombre_dc,
                    "grupo_anterior": grupo_dc,
                    "grupo_nuevo": grupo_gantt,
                    "inicio_nuevo": inicio_gantt,
                    "pct": row[3] if len(row) > 3 else 0,
                })

    if not cambios:
        log.info("  Sin movimientos de grupo detectados.")
        return

    log.info(f"  MOVIMIENTOS DETECTADOS ({len(cambios)}):")
    requests = []
    dc_gid = _get_dc_gid(sheets_svc)
    for c in cambios:
        log.info(f"    >> {c['nombre']}: {c['grupo_anterior']} → {c['grupo_nuevo']} "
                 f"(inicio: {c['inicio_nuevo']})")
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

    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
        ).execute()
        _reordenar_datos_control(sheets_svc)
        log.info(f"  Datos Control actualizado ({len(cambios)} movimiento(s)).")

    return cambios


# ─────────────────────────────────────────────────────────────────────────────
# 3. LEER DATOS
# ─────────────────────────────────────────────────────────────────────────────
def _normalizar_nombre(nombre):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_t = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_t.upper().split())


def leer_avance_appsheet():
    if not APPSHEET_DISPONIBLE:
        return None
    try:
        log.info(f"Leyendo avance desde AppSheet {APPSHEET_PROJECT} (Juan Huilcan Tolten)...")
        datos = leer_avance_proyecto(APPSHEET_PROJECT)
        result = {_normalizar_nombre(k): v for k, v in datos.items()}
        log.info(f"  AppSheet {APPSHEET_PROJECT}: {len(result)} beneficiarios leidos.")
        return result
    except Exception as e:
        log.warning(f"AppSheet no disponible ({e}). Usando 'Datos Control'.")
        return None


def leer_datos_control(sheets_svc):
    control_date = date.today()
    log.info(f"Fecha de control (hoy): {control_date.strftime('%d/%m/%Y')}")

    result = sheets_svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:D100",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()
    rows = result.get("values", [])

    avance_appsheet = leer_avance_appsheet()

    grupos = {}
    sin_match = []

    for row in rows[4:]:
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
        log.warning(f"Sin match AppSheet ({len(sin_match)}): " + ", ".join(sin_match[:5]))

    fuente = "AppSheet" if avance_appsheet else "'Datos Control'"
    log.info(f"Beneficiarios: {sum(len(v) for v in grupos.values())} en {len(grupos)} grupos | avance desde: {fuente}")
    return control_date, grupos


def actualizar_pct_en_hoja(sheets_svc, grupos):
    valores = []
    for bens in grupos.values():
        for _, _, pct in bens:
            valores.append([round(pct)])
    if not valores:
        return
    n = len(valores)
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'Datos Control'!D5:D{4 + n}",
        valueInputOption="USER_ENTERED",
        body={"values": valores},
    ).execute()
    log.info(f"  % real guardados en 'Datos Control' ({n} filas)")


# ─────────────────────────────────────────────────────────────────────────────
# 4. LÓGICA DE CURVAS S
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


def _fmt_date(d):
    return d.strftime("%d/%m/%Y")


def build_group_curves(beneficiarios, control):
    benef_adj = []
    for nombre, inicio, pct in beneficiarios:
        if inicio >= control and pct > 0:
            inicio_eff = _estimar_inicio_efectivo(control, pct)
            log.info(f"    [inicio_eff] {nombre}: planif={_fmt_date(inicio)} → eff={_fmt_date(inicio_eff)} ({pct:.0f}%)")
            benef_adj.append((nombre, inicio_eff, pct))
        else:
            benef_adj.append((nombre, inicio, pct))
    beneficiarios = benef_adj

    inicio_grupo   = min(b[1] for b in beneficiarios)
    fin_proyecto   = max(b[1] + timedelta(days=DURACION_DIAS) for b in beneficiarios)
    fin_proyectado = max(proyectar_fin(b[1], b[2], control) for b in beneficiarios)
    fecha_fin      = max(fin_proyecto, fin_proyectado) + timedelta(days=14)
    fechas         = [inicio_grupo + timedelta(days=d) for d in range((fecha_fin - inicio_grupo).days + 1)]

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
# 5. GENERAR GRÁFICOS
# ─────────────────────────────────────────────────────────────────────────────
def generar_grafico_grupo(nombre_grupo, beneficiarios, control, outdir):
    color = COLORES.get(nombre_grupo, "#333333")
    fechas, prog, real_hist, proj, fin_proy = build_group_curves(beneficiarios, control)

    pct_real_avg  = np.mean([b[2] for b in beneficiarios])
    idx_ctrl      = (control - fechas[0]).days
    pct_prog_ctrl = prog[idx_ctrl] if 0 <= idx_ctrl < len(prog) else 0.0

    fig, ax = plt.subplots(figsize=(10, 5.1))
    ax.set_facecolor("#f8f9fa"); fig.patch.set_facecolor("#ffffff")

    ax.plot(fechas, prog, color="#1f77b4", linewidth=2.5, linestyle="--", label="% Programado", zorder=3)
    rf = [f for f, v in zip(fechas, real_hist) if v is not None]
    rv = [v for v in real_hist if v is not None]
    ax.plot(rf, rv, color="#2ca02c", linewidth=3, label="% Real (suavizado)", zorder=4)
    pf = [f for f, v in zip(fechas, proj) if v is not None]
    pv = [v for v in proj if v is not None]
    ax.plot(pf, pv, color="#d62728", linewidth=2, linestyle=":", label="% Proyectado", zorder=3)
    ax.axvline(control, color="#ff7f0e", linewidth=2, linestyle="-.", label=f"Fecha Control ({_fmt_date(control)})", zorder=5)
    if fin_proy <= fechas[-1]:
        ax.axvline(fin_proy, color="#9467bd", linewidth=1.5, linestyle=":", label=f"Término Proyectado ({_fmt_date(fin_proy)})", zorder=4)

    if 0 <= idx_ctrl < len(prog):
        _diff = pct_real_avg - prog[idx_ctrl]
        _signo = "+" if _diff >= 0 else ""
        ax.annotate(
            f"Prog: {prog[idx_ctrl]:.1f}%\nReal: {pct_real_avg:.1f}%\nDesv: {_signo}{_diff:.1f}%",
            xy=(control, prog[idx_ctrl]),
            xytext=(control + timedelta(days=21), prog[idx_ctrl] + 8),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6", edgecolor="#ff7f0e", linewidth=1.0, alpha=0.95),
        )

    fin_prog_grupo = max(b[1] for b in beneficiarios) + timedelta(days=DURACION_DIAS)
    ax.set_xlim(fechas[0] - timedelta(days=7), fechas[-1] + timedelta(days=7))
    ax.set_ylim(-2, 108)
    ax.set_ylabel("Avance (%)", fontsize=12)
    ax.set_xlabel("Fecha", fontsize=12)
    ax.set_title(
        f"Curva S - {nombre_grupo} · Juan Huilcan Tolten ({len(beneficiarios)} viviendas)\n"
        f"Inicio: {_fmt_date(min(b[1] for b in beneficiarios))}  |  "
        f"Fin Prog.: {_fmt_date(fin_prog_grupo)}  |  Fin Proy.: {_fmt_date(fin_proy)}",
        fontsize=13, fontweight="bold", pad=10,
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
    fname = Path(outdir) / f"CurvaS_{nombre_grupo.replace(' ', '_')}_Huilcan.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Gráfico guardado: {fname.name}")
    return pct_real_avg, pct_prog_ctrl, min(b[1] for b in beneficiarios), fin_proy


def generar_grafico_total(grupos, control, fines_proy_global, outdir):
    todos = [b for bens in grupos.values() for b in bens]
    inicio_total    = min(b[1] for b in todos)
    fin_prog_total  = max(b[1] for b in todos) + timedelta(days=DURACION_DIAS)
    fin_proy_total  = max(fines_proy_global)
    fecha_fin_total = max(fin_prog_total, fin_proy_total) + timedelta(days=14)
    fechas_total    = [inicio_total + timedelta(days=d) for d in range((fecha_fin_total - inicio_total).days + 1)]

    prog_total, real_total, proj_total = [], [], []
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
        real_total.append(np.mean(vr) if vr else None)
        proj_total.append(np.mean(vproj) if vproj else None)

    pct_real_total = np.mean([b[2] for b in todos])
    idx_ctrl_total = (control - inicio_total).days

    fig2, ax2 = plt.subplots(figsize=(10, 5.1))
    ax2.set_facecolor("#f8f9fa"); fig2.patch.set_facecolor("#ffffff")

    ax2.plot(fechas_total, prog_total, color="#1f77b4", linewidth=3, linestyle="--", label="% Programado Total", zorder=3)
    rt_f = [f for f, v in zip(fechas_total, real_total) if v is not None]
    rt_v = [v for v in real_total if v is not None]
    ax2.plot(rt_f, rt_v, color="#2ca02c", linewidth=3.5, label="% Real Total (suavizado)", zorder=4)
    pt_f = [f for f, v in zip(fechas_total, proj_total) if v is not None]
    pt_v = [v for v in proj_total if v is not None]
    ax2.plot(pt_f, pt_v, color="#d62728", linewidth=2.5, linestyle=":", label="% Proyectado Total", zorder=3)
    ax2.axvline(control, color="#ff7f0e", linewidth=2.5, linestyle="-.", label=f"Fecha Control ({_fmt_date(control)})", zorder=5)
    ax2.axvline(fin_proy_total, color="#9467bd", linewidth=2, linestyle=":", label=f"Término Proyectado ({_fmt_date(fin_proy_total)})", zorder=4)
    ax2.axvline(fin_prog_total, color="#1f77b4", linewidth=1.5, linestyle=":", alpha=0.6, label=f"Término Programado ({_fmt_date(fin_prog_total)})", zorder=3)

    if 0 <= idx_ctrl_total < len(prog_total):
        prog_en_ctrl = prog_total[idx_ctrl_total]
        _diff2 = pct_real_total - prog_en_ctrl
        _signo2 = "+" if _diff2 >= 0 else ""
        ax2.annotate(
            f"Prog:  {prog_en_ctrl:.1f}%\nReal:  {pct_real_total:.1f}%\nDesv: {_signo2}{_diff2:.1f}%",
            xy=(control, prog_en_ctrl),
            xytext=(control + timedelta(days=28), prog_en_ctrl + 10),
            fontsize=12, color="#111111", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6", edgecolor="#ff7f0e", linewidth=1.0, alpha=0.95),
        )

    ax2.set_xlim(fechas_total[0] - timedelta(days=7), fechas_total[-1] + timedelta(days=7))
    ax2.set_ylim(-2, 108)
    ax2.set_ylabel("Avance promedio (%)", fontsize=12)
    ax2.set_xlabel("Fecha", fontsize=12)
    ax2.set_title(
        f"Curva S Total - Juan Huilcan Tolten ({len(todos)} viviendas)\n"
        f"Inicio: {_fmt_date(inicio_total)}  |  Fin Programado: {_fmt_date(fin_prog_total)}  |  Fin Proyectado: {_fmt_date(fin_proy_total)}",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax2.grid(axis="y", alpha=0.4, linestyle="--"); ax2.grid(axis="x", alpha=0.2, linestyle=":")
    ax2.legend(loc="upper left", fontsize=9, framealpha=0.95)
    ax2.axvspan(fechas_total[0], control, alpha=0.03, color="green")
    ax2.axvspan(control, fechas_total[-1], alpha=0.03, color="red")

    plt.tight_layout()
    fname_total = Path(outdir) / "CurvaS_TOTAL_Huilcan.png"
    plt.savefig(fname_total, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Gráfico guardado: {fname_total.name}")


def generar_grafico_todos(grupos, control, fines_proy_global, outdir):
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
    ax3.set_xlim(inicio_ref - timedelta(days=7), max(fines_proy_global) + timedelta(days=30))
    ax3.set_ylim(-2, 108)
    ax3.set_ylabel("Avance (%)", fontsize=12)
    ax3.set_xlabel("Fecha", fontsize=12)
    ax3.set_title(
        "Curva S por Grupo - Juan Huilcan Tolten\n"
        "Línea continua = Real  |  Discontinua = Programado  |  Punteado = Proyectado",
        fontsize=13, fontweight="bold", pad=10,
    )
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax3.grid(axis="y", alpha=0.4, linestyle="--"); ax3.grid(axis="x", alpha=0.2, linestyle=":")
    ax3.axvspan(inicio_ref, control, alpha=0.03, color="green")

    plt.tight_layout()
    fname = Path(outdir) / "CurvaS_Todos_Grupos_Huilcan.png"
    plt.savefig(fname, dpi=DPI_EXPORT, bbox_inches="tight"); plt.close()
    log.info(f"  Gráfico guardado: {fname.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. DRIVE
# ─────────────────────────────────────────────────────────────────────────────
def _load_drive_ids():
    return _ccu.load_drive_ids("huilcan")


def _save_drive_ids(ids):
    _ccu.save_drive_ids("huilcan", ids)


def actualizar_drive(drive_svc, outdir):
    log.info("Actualizando archivos en Google Drive...")
    drive_ids = _load_drive_ids()
    nuevos = {}

    for chart_name in CHART_NAMES:
        path = Path(outdir) / chart_name
        if not path.exists():
            log.warning(f"  No encontrado: {path}, saltando.")
            continue
        media = MediaFileUpload(str(path), mimetype="image/png", resumable=False)
        existing_id = drive_ids.get(chart_name, "")
        if existing_id:
            drive_svc.files().update(
                fileId=existing_id, body={"name": chart_name}, media_body=media
            ).execute()
            nuevos[chart_name] = existing_id
            log.info(f"  Actualizado: {chart_name} -> {existing_id}")
        else:
            res = drive_svc.files().create(
                body={"name": chart_name, "mimeType": "image/png"},
                media_body=media,
                fields="id"
            ).execute()
            new_id = res["id"]
            drive_svc.permissions().create(
                fileId=new_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
            nuevos[chart_name] = new_id
            log.info(f"  Creado nuevo: {chart_name} -> {new_id}")

    drive_ids.update(nuevos)
    _save_drive_ids(drive_ids)
    return drive_ids


# ─────────────────────────────────────────────────────────────────────────────
# 7. SHEETS IMAGE()
# ─────────────────────────────────────────────────────────────────────────────
def insertar_imagenes_en_sheets(sheets_svc, drive_ids):
    log.info("Actualizando fórmulas IMAGE() en hoja 'Curvas S' Juan Huilcan Tolten...")
    meta = sheets_svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    curvas_gid = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Curvas S":
            curvas_gid = s["properties"]["sheetId"]
            break
    if curvas_gid is None:
        log.error("Hoja 'Curvas S' no encontrada.")
        return

    W_PX, H_PX = 755, 385
    layout = [
        ("CurvaS_GRUPO_1_Huilcan.png",      0, 0),
        ("CurvaS_TOTAL_Huilcan.png",         1, 0),
        ("CurvaS_Todos_Grupos_Huilcan.png",  0, 1),
    ]

    n_cols = max(c for _, c, _ in layout) + 1
    n_rows = max(r for _, _, r in layout) + 1

    requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": curvas_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": n_cols},
            "properties": {"pixelSize": W_PX}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": curvas_gid, "dimension": "ROWS", "startIndex": 0, "endIndex": n_rows},
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
            "range": {"sheetId": curvas_gid,
                      "startRowIndex": row, "endRowIndex": row + 1,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "rows": [{"values": [{"userEnteredValue": {"formulaValue": f'=IMAGE("{url}",1)'}}]}],
            "fields": "userEnteredValue"
        }})

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
    ).execute()
    log.info(f"  {len(layout)} fórmulas IMAGE() actualizadas (v={ts}).")


# ─────────────────────────────────────────────────────────────────────────────
# 8. FLAGS
# ─────────────────────────────────────────────────────────────────────────────
def marcar_pendiente(sheets_svc, timestamp_str):
    control_str = date.today().strftime("%d/%m/%Y")
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Datos Control'!A1:B2",
        valueInputOption="USER_ENTERED",
        body={"values": [["ESTADO", f"PENDIENTE - {timestamp_str}"], ["FECHA_CONTROL", control_str]]},
    ).execute()
    log.info(f"Flag PENDIENTE escrito | FECHA_CONTROL={control_str}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 65)
    log.info(f"INICIO CURVAS S JUAN HUILCAN TOLTEN  -  {ts}")
    log.info("=" * 65)
    try:
        creds      = get_credentials()
        sheets_svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        drive_svc  = build("drive",  "v3", credentials=creds, cache_discovery=False)

        setup_hojas(sheets_svc)
        sincronizar_grupos_desde_gantt(sheets_svc)

        log.info(f"Fecha de control (hoy): {date.today().strftime('%d/%m/%Y')}")
        control_date, grupos = leer_datos_control(sheets_svc)
        actualizar_pct_en_hoja(sheets_svc, grupos)

        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

        log.info("Generando gráficos por grupo...")
        fines_proy_global = []
        for nombre_grupo, beneficiarios in grupos.items():
            _, _, _, fin_proy = generar_grafico_grupo(nombre_grupo, beneficiarios, control_date, OUTPUT_DIR)
            fines_proy_global.append(fin_proy)

        log.info("Generando gráficos consolidados...")
        generar_grafico_total(grupos, control_date, fines_proy_global, OUTPUT_DIR)
        generar_grafico_todos(grupos, control_date, fines_proy_global, OUTPUT_DIR)

        drive_ids = actualizar_drive(drive_svc, OUTPUT_DIR)
        insertar_imagenes_en_sheets(sheets_svc, drive_ids)
        marcar_pendiente(sheets_svc, ts)

        log.info("=" * 65)
        log.info("COMPLETADO. Curvas S Juan Huilcan Tolten actualizadas.")
        log.info("=" * 65)

    except Exception:
        log.error("ERROR:\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
curvas_master.py
================
Script universal para actualizar Curvas S de cualquier proyecto.
Reemplaza todos los curvas_automatico_*.py individuales.

Uso:
  python curvas_master.py P119              # Procesa Ñuke Mapu
  python curvas_master.py P126              # Procesa El Maitén
  python curvas_master.py --todos           # Procesa todos los proyectos
  python curvas_master.py P119 --debug      # Browser AppSheet visible
  python curvas_master.py --sync-dashboard  # Solo actualiza dashboard (post-proceso)

Flujo por proyecto:
  1. Lee beneficiarios y grupos desde Gantt "Datos Control"
  2. Lee % programado del lunes actual desde Gantt "Programa de obra"
  3. Lee % avance real desde AppSheet web (leer_appsheet_web.py)
  4. Genera imágenes PNG por grupo + TOTAL + TODOS_GRUPOS
  5. Sube/actualiza imágenes en Google Drive (drive_ids.json / Firebase)
  6. Inserta fórmulas IMAGE() en pestaña "Curva S" del Gantt
  7. Actualiza "Datos Control" con nuevos % reales (2 decimales)
  8. Actualiza Firebase (avance_gantt)
  Nota: SIN enviar correos — solo el cron del lunes lo hace
"""

import json
import logging
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

import curvas_cloud_utils as _ccu
from googleapiclient.discovery import build

# ─── RUTAS ────────────────────────────────────────────────────────────────────
_BASE          = Path(__file__).parent
CONFIG_FILE    = _BASE / "config_proyectos.json"
DRIVE_IDS_FILE = _BASE / "drive_ids.json"

FIREBASE_NODE_V2 = "drive_ids_v2"   # /drive_ids_v2 en Firebase RTDB
GITHUB_REPO      = "PitufosTEch/PruebasWeb"
GITHUB_FILE      = "SCRaices-LLM/dashboard/app_compiled.js"
GITHUB_BRANCH    = "master"

# ─── COLORES POR GRUPO ────────────────────────────────────────────────────────
_COLORES_DEFAULT = [
    "#1a6eb5", "#e07b00", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#17becf",
]
COLORES_GRUPO = {
    "GRUPO 1":         "#1a6eb5",
    "GRUPO 2":         "#e07b00",
    "GRUPO 3":         "#2ca02c",
    "GRUPO 4":         "#d62728",
    "GRUPO 5":         "#9467bd",
    "GRUPO REZAGADOS": "#8c564b",
}

# ─── LOGGING ──────────────────────────────────────────────────────────────────
log = _ccu.setup_logging("curvas_master")


# ─── UTILIDADES ───────────────────────────────────────────────────────────────
def _normalizar(nombre: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(nombre))
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


def _lunes_actual() -> date:
    hoy = date.today()
    return hoy - timedelta(days=hoy.weekday())


def _color_grupo(grupo: str, idx: int) -> str:
    return COLORES_GRUPO.get(grupo.strip().upper(), _COLORES_DEFAULT[idx % len(_COLORES_DEFAULT)])


# ─── CARGAR CONFIG ────────────────────────────────────────────────────────────
def _cargar_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _proyecto_por_id(cfg: dict, pid: str) -> dict:
    for p in cfg["proyectos"]:
        if p["id"] == pid:
            return p
    raise ValueError(f"Proyecto {pid} no encontrado en config_proyectos.json")


# ─── DRIVE IDs (cloud-aware) ──────────────────────────────────────────────────
def _cargar_drive_ids() -> dict:
    """Cloud → Firebase /drive_ids_v2. Local → drive_ids.json."""
    import requests
    if _ccu.is_cloud():
        url = f"{_ccu.FIREBASE_URL}/{FIREBASE_NODE_V2}.json"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and r.json():
                data = r.json()
                log.info(f"Drive IDs desde Firebase: {len(data)} proyectos")
                return data
        except Exception as e:
            log.warning(f"Firebase drive_ids no disponible: {e}")
        return {}

    if DRIVE_IDS_FILE.exists():
        with open(DRIVE_IDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _guardar_drive_ids(ids: dict):
    """Cloud → Firebase /drive_ids_v2. Local → drive_ids.json."""
    import requests
    if _ccu.is_cloud():
        url = f"{_ccu.FIREBASE_URL}/{FIREBASE_NODE_V2}.json"
        try:
            r = requests.put(url, json=ids, timeout=30)
            r.raise_for_status()
            log.info(f"Drive IDs en Firebase: {len(ids)} proyectos")
        except Exception as e:
            log.error(f"Error guardando drive_ids Firebase: {e}")
        return

    with open(DRIVE_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2, ensure_ascii=False)
    log.info(f"Drive IDs en {DRIVE_IDS_FILE.name}")


# ─── PASO 1: LEER BENEFICIARIOS DESDE GANTT ──────────────────────────────────
def leer_beneficiarios_gantt(sheets_svc, spreadsheet_id: str) -> list:
    """
    Lee 'Datos Control' y retorna lista de beneficiarios con grupo, nombre, inicio, pct_real.
    Detecta grupos automáticamente (incluyendo REZAGADOS como grupo normal).
    """
    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Datos Control'!A1:D200",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    filas = r.get("values", [])

    beneficiarios = []
    for fila in filas:
        if len(fila) < 2:
            continue
        col_a = str(fila[0]).strip().upper()
        col_b = str(fila[1]).strip() if len(fila) > 1 else ""
        col_c = str(fila[2]).strip() if len(fila) > 2 else ""
        col_d = str(fila[3]).strip() if len(fila) > 3 else "0"

        if col_b.upper() in ("BENEFICIARIO", "NOMBRE", ""):
            continue
        if not col_a.startswith("GRUPO"):
            continue

        try:
            pct = round(float(col_d.replace("%", "").replace(",", ".") or "0"), 2)
        except ValueError:
            pct = 0.0

        beneficiarios.append({
            "grupo":    col_a,
            "nombre":   _normalizar(col_b),
            "inicio":   col_c,
            "pct_real": pct,
        })

    n_grupos = len(set(b["grupo"] for b in beneficiarios))
    log.info(f"  Datos Control: {len(beneficiarios)} beneficiarios, {n_grupos} grupos")
    return beneficiarios


# ─── PASO 2: % PROGRAMADO DESDE GANTT ────────────────────────────────────────
def leer_pct_programado(sheets_svc, spreadsheet_id: str, control_date: date) -> dict:
    """Retorna { 'GRUPO 1': 55.3, ..., 'GRUPO REZAGADOS': 80.1, 'TOTAL': 26.85 }"""
    hoja = "Programa de obra"
    raw = _ccu.leer_pct_prog_por_grupo(sheets_svc, spreadsheet_id, hoja, control_date)
    result = {}
    for k, v in raw.items():
        if "REZAG" in k.upper():
            result["GRUPO REZAGADOS"] = v
        else:
            result[k] = v
    # % total del programa
    total_pct = _ccu.leer_pct_programa_gantt(sheets_svc, spreadsheet_id, hoja)
    if total_pct is not None:
        result["TOTAL"] = total_pct
    log.info(f"  % programado {control_date}: {result}")
    return result


# ─── PASO 3: % REAL DESDE APPSHEET WEB ───────────────────────────────────────
def leer_avance_appsheet(project_id: str, debug: bool = False) -> dict:
    """Retorna { 'APELLIDO NOMBRE (normalizado)': pct_float }."""
    from leer_appsheet_web import leer_proyecto
    return leer_proyecto(project_id, headless=not debug)


# ─── PASO 4: FUSIONAR DATOS ───────────────────────────────────────────────────
def fusionar_datos(beneficiarios: list, avance_web: dict) -> list:
    # Índice frozenset para resolver diferencia de orden NOMBRE/APELLIDO entre
    # Sheets ("INES DEL CARMEN HERNANDEZ CASTRO") y AppSheet ("HERNANDEZ CASTRO INES DEL CARMEN")
    palabras_a_pct: dict[frozenset, tuple] = {
        frozenset(k.split()): (k, v) for k, v in avance_web.items()
    }

    sin_match = []
    resultado = []
    for b in beneficiarios:
        nombre_norm = b["nombre"]
        pct = avance_web.get(nombre_norm)

        if pct is None:
            # Comparar conjuntos completos (orden NOMBRE/APELLIDO diferente)
            palabras = frozenset(nombre_norm.split())
            match = palabras_a_pct.get(palabras)
            if match:
                nombre_web, pct = match
                log.info(f"  Match por palabras: '{nombre_norm}' → '{nombre_web}'")

        if pct is None:
            # Subconjunto bidireccional:
            #   - AppSheet omite palabra de Sheets → palabras_web ⊆ palabras
            #   - AppSheet tiene extra palabra    → palabras ⊆ palabras_web
            palabras = frozenset(nombre_norm.split())
            for palabras_web, (nombre_web, pct_web) in palabras_a_pct.items():
                if (palabras_web.issubset(palabras) or palabras.issubset(palabras_web)) \
                        and len(palabras_web) >= 2 and len(palabras) >= 2:
                    pct = pct_web
                    log.info(f"  Match subconjunto: '{nombre_norm}' → '{nombre_web}'")
                    break

        if pct is None:
            sin_match.append(nombre_norm)
            pct = b["pct_real"]

        resultado.append({**b, "pct_real": round(pct, 2)})

    if sin_match:
        log.warning(f"  Sin match ({len(sin_match)}): {sin_match}")
    return resultado


# ─── PASO 5: GENERAR IMÁGENES PNG ────────────────────────────────────────────
def _fecha_inicio(b: dict):
    try:
        raw = b["inicio"].replace("-", "/")
        partes = raw.split("/")
        if len(partes) == 3:
            return date(int(partes[2]), int(partes[1]), int(partes[0]))
    except Exception:
        pass
    return None


def _interpolar(fechas: list, pcts: list, target: date):
    if not fechas or not pcts:
        return None
    for i, f in enumerate(fechas):
        if f >= target:
            if i == 0:
                return pcts[0]
            f0, f1 = fechas[i-1], fechas[i]
            p0, p1 = pcts[i-1], pcts[i]
            t = (target - f0).days / max((f1 - f0).days, 1)
            return round(p0 + t * (p1 - p0), 2)
    return pcts[-1] if pcts else None


def _s_curve_real(t_days: int, pct_real: float, t_control: int) -> float:
    """Modelo logístico: crece de 0 a pct_real en t_control días."""
    if t_control <= 0 or pct_real == 0:
        return 0.0
    t_norm = t_days / t_control
    k = 5.0
    v     = 1.0 / (1.0 + np.exp(-k * (t_norm - 0.5)))
    v_max = 1.0 / (1.0 + np.exp(-k *  0.5))
    v_min = 1.0 / (1.0 + np.exp(-k * -0.5))
    return float(np.clip((v - v_min) / (v_max - v_min) * pct_real, 0.0, pct_real))


def _fin_proyectado_benef(b: dict, control_date: date) -> date:
    """Fecha estimada de término de un beneficiario al ritmo actual."""
    fi = _fecha_inicio(b)
    if fi is None:
        return control_date + timedelta(days=245)
    pct = b["pct_real"]
    # Para avance muy bajo (<= 10%) la extrapolación lineal es poco confiable;
    # usar la duración nominal de obra (igual que hacía el script original).
    if pct <= 10:
        return fi + timedelta(days=245)
    dias_trans = max(1, (control_date - fi).days)
    tasa = pct / dias_trans
    dias_rest = (100.0 - pct) / tasa
    # Cap: nunca proyectar más de 3 años desde la fecha de control
    dias_rest = min(dias_rest, 3 * 365)
    return control_date + timedelta(days=int(dias_rest))


def _curva_real_grupo(beneficiarios: list, control_date: date):
    """
    Retorna (fechas_hist, pcts_hist, fechas_proj, pcts_proj).
    - hist: desde fecha_ini hasta control_date, curva sigmoide por beneficiario.
    - proj: desde control_date hasta fin proyectado, extrapolación lineal.
    """
    fechas_ini_validas = [_fecha_inicio(b) for b in beneficiarios if _fecha_inicio(b)]
    if not fechas_ini_validas:
        return [], [], [], []

    fecha_ini = min(fechas_ini_validas)
    n_total   = len(beneficiarios)

    # Fin proyectado: el más tardío entre todos los beneficiarios
    fin_proy = max(_fin_proyectado_benef(b, control_date) for b in beneficiarios)
    fin_proy = max(fin_proy, control_date + timedelta(days=30))

    # ── Curva histórica (hasta control_date, sigmoide) ──
    fechas_hist, pcts_hist = [], []
    f = fecha_ini
    while f <= control_date:
        valores = []
        for b in beneficiarios:
            fi = _fecha_inicio(b)
            if fi is None or fi > f:
                continue
            t_dias    = max(0, (f - fi).days)
            t_control = max(1, (control_date - fi).days)
            valores.append(_s_curve_real(t_dias, b["pct_real"], t_control))
        pct_avg = round(sum(valores) / n_total, 2) if valores else 0.0
        fechas_hist.append(f)
        pcts_hist.append(pct_avg)
        f += timedelta(weeks=1)

    # Asegurar que el último punto histórico es exactamente control_date
    if fechas_hist and fechas_hist[-1] != control_date:
        valores_ctrl = []
        for b in beneficiarios:
            fi = _fecha_inicio(b)
            if fi is None or fi > control_date:
                continue
            t_control = max(1, (control_date - fi).days)
            valores_ctrl.append(_s_curve_real(t_control, b["pct_real"], t_control))
        pct_ctrl = round(sum(valores_ctrl) / n_total, 2) if valores_ctrl else pcts_hist[-1]
        fechas_hist.append(control_date)
        pcts_hist.append(pct_ctrl)

    # ── Curva proyectada (desde control_date hasta fin_proy) ──
    fechas_proj, pcts_proj = [], []
    pct_en_ctrl = pcts_hist[-1] if pcts_hist else 0.0
    f = control_date
    while f <= fin_proy:
        valores = []
        for b in beneficiarios:
            fi = _fecha_inicio(b)
            if fi is None or fi > control_date:
                continue
            if b["pct_real"] <= 0:
                continue
            t_control = max(1, (control_date - fi).days)
            tasa = b["pct_real"] / t_control
            v = min(100.0, b["pct_real"] + tasa * (f - control_date).days)
            valores.append(v)
        pct_avg = round(sum(valores) / n_total, 2) if valores else pct_en_ctrl
        fechas_proj.append(f)
        pcts_proj.append(pct_avg)
        f += timedelta(weeks=1)

    return fechas_hist, pcts_hist, fechas_proj, pcts_proj


def _curva_prog_lineal(beneficiarios: list, pct_prog: float, control_date: date):
    fechas_ini = [_fecha_inicio(b) for b in beneficiarios]
    fechas_ini = [f for f in fechas_ini if f is not None]
    if not fechas_ini:
        return [], []
    fecha_ini = min(fechas_ini)
    fecha_fin = fecha_ini + timedelta(days=224)
    total_dias = max((fecha_fin - fecha_ini).days, 1)
    limite = max(fecha_fin, control_date + timedelta(days=14))
    fechas, pcts = [], []
    f = fecha_ini
    while f <= limite:
        dias = (f - fecha_ini).days
        pcts.append(round(min(pct_prog, pct_prog * dias / total_dias), 2))
        fechas.append(f)
        f += timedelta(weeks=1)
    return fechas, pcts


def _setup_ax(ax, titulo: str, control_date: date):
    ax.set_facecolor("#f8f9fa")
    ax.set_title(titulo, fontsize=12, fontweight="bold", pad=8)
    ax.set_ylabel("% Avance", fontsize=9)
    ax.set_ylim(-2, 108)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.4, linestyle="--")
    ax.grid(axis="x", alpha=0.2, linestyle=":")
    ax.axvline(control_date, color="#ff7f0e", lw=2, linestyle="-.", zorder=4,
               label=f"Fecha Control ({control_date.strftime('%d/%m/%Y')})")


def generar_imagen_grupo(beneficiarios: list, grupo: str, proyecto_nombre: str,
                         pct_prog, output_path: Path, control_date: date):
    color = _color_grupo(grupo, 0)
    fechas_hist, pcts_hist, fechas_proj, pcts_proj = _curva_real_grupo(beneficiarios, control_date)

    fig, ax = plt.subplots(figsize=(10, 5.1), dpi=200)
    fig.patch.set_facecolor("white")
    _setup_ax(ax, f"Curva S — {grupo}  ·  {proyecto_nombre}", control_date)

    # Curva programada (lineal de referencia)
    ppc = None
    if pct_prog is not None:
        fp, pp = _curva_prog_lineal(beneficiarios, pct_prog, control_date)
        if fp:
            ax.plot(fp, pp, color="#888888", lw=1.5, linestyle="--", label="Programado", zorder=2)
            ppc = _interpolar(fp, pp, control_date)

    # Curva real histórica (sigmoide)
    prc = None
    if fechas_hist:
        ax.plot(fechas_hist, pcts_hist, color=color, lw=2.5, marker="o", markersize=3,
                label="Real", zorder=3)
        ax.axvspan(fechas_hist[0], control_date, alpha=0.04, color="green", zorder=0)
        prc = pcts_hist[-1]

    # Curva proyectada (punteada)
    if fechas_proj and len(fechas_proj) > 1:
        ax.plot(fechas_proj, pcts_proj, color=color, lw=1.8, linestyle=":",
                label="Proyectado", zorder=2, alpha=0.8)
        ax.axvspan(control_date, fechas_proj[-1], alpha=0.03, color="red", zorder=0)

    # Marcador y anotación en fecha de control
    if prc is not None:
        ax.plot(control_date, prc, "o", color=color, markersize=8, zorder=6)

    # Cuadro resumen Prog / Real / Desv
    if prc is not None:
        pct_p_display = ppc if ppc is not None else 0.0
        diff = prc - pct_p_display
        signo = "+" if diff >= 0 else ""
        txt = f"Prog: {pct_p_display:.1f}%\nReal: {prc:.1f}%\nDesv: {signo}{diff:.1f}%"
        ax.annotate(txt,
                    xy=(control_date, prc),
                    xycoords="data",
                    xytext=(0.97, 0.06),
                    textcoords="axes fraction",
                    fontsize=10, color="#111111", fontweight="bold",
                    ha="right", va="bottom",
                    arrowprops=dict(arrowstyle="->", color="#ff7f0e", lw=1.0),
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="#fffbe6",
                              edgecolor="#ff7f0e", lw=1.0, alpha=0.95))

    # Acotar el eje X: desde la primera fecha hasta fin proyectado (o max 3 años)
    todas_fechas = (fechas_hist or []) + (fechas_proj or [])
    if todas_fechas:
        x_ini = todas_fechas[0] - timedelta(days=7)
        x_fin = todas_fechas[-1] + timedelta(days=14)
        ax.set_xlim(x_ini, x_fin)

    ax.legend(loc="upper left", fontsize=8, framealpha=0.8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    log.info(f"  PNG: {output_path.name}")


def generar_imagen_todos_grupos(grupos_data: dict, proyecto_nombre: str,
                                output_path: Path, control_date: date,
                                grupos_ordenados: list):
    fig, ax = plt.subplots(figsize=(10, 5.1), dpi=200)
    fig.patch.set_facecolor("white")
    _setup_ax(ax, f"Curva S — Todos los Grupos  ·  {proyecto_nombre}", control_date)

    handles = []
    for i, grupo in enumerate(grupos_ordenados):
        benef = grupos_data.get(grupo, [])
        if not benef:
            continue
        color = _color_grupo(grupo, i)
        fechas_hist, pcts_hist, fechas_proj, pcts_proj = _curva_real_grupo(benef, control_date)
        if fechas_hist:
            ax.plot(fechas_hist, pcts_hist, color=color, lw=2.0, marker="o", markersize=3)
            handles.append(Line2D([0], [0], color=color, lw=2, label=grupo))
        if fechas_proj and len(fechas_proj) > 1:
            ax.plot(fechas_proj, pcts_proj, color=color, lw=1.5, linestyle=":", alpha=0.7)

    legend_extra = [
        Line2D([0], [0], color="gray", lw=1.8, linestyle=":",  label="Proyectado"),
    ]
    if handles:
        ax.legend(handles=handles + legend_extra, loc="upper left", fontsize=7, framealpha=0.8)

    # Acotar eje X al rango útil de los grupos mostrados
    todas_fechas_g = []
    for grupo in grupos_ordenados:
        benef = grupos_data.get(grupo, [])
        if not benef:
            continue
        fh, _, fp, _ = _curva_real_grupo(benef, control_date)
        todas_fechas_g.extend(fh or [])
        todas_fechas_g.extend(fp or [])
    if todas_fechas_g:
        ax.set_xlim(min(todas_fechas_g) - timedelta(days=7),
                    max(todas_fechas_g) + timedelta(days=14))

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    log.info(f"  PNG: {output_path.name}")




# ─── PASO 7: ACTUALIZAR HOJA CURVAS S ────────────────────────────────────────
def actualizar_curvas_s_sheet(sheets_svc, spreadsheet_id: str,
                               imagenes_drive: dict, control_date: date):
    """Inserta =IMAGE() en hoja 'Curvas S', layout 2 columnas."""
    grupos_norm = sorted(k for k in imagenes_drive if k not in ("TOTAL", "TODOS_GRUPOS"))
    orden = grupos_norm
    if "TOTAL" in imagenes_drive:
        orden.append("TOTAL")
    if "TODOS_GRUPOS" in imagenes_drive:
        orden.append("TODOS_GRUPOS")

    filas = []
    fila = []
    for key in orden:
        fid = imagenes_drive[key]
        url = f"https://drive.google.com/thumbnail?id={fid}&sz=w800"
        fila.append(f'=IMAGE("{url}", 1)')
        if len(fila) == 2:
            filas.append(fila)
            fila = []
    if fila:
        fila.append("")
        filas.append(fila)

    sheets_svc.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range="'Curvas S'!A1:Z200",
    ).execute()
    if filas:
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="'Curvas S'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": filas},
        ).execute()
        log.info(f"  Hoja 'Curvas S': {len(filas)} filas")


# ─── PASO 8: ACTUALIZAR DATOS CONTROL ────────────────────────────────────────
def actualizar_datos_control(sheets_svc, spreadsheet_id: str,
                              beneficiarios: list, control_date: date):
    """Actualiza % real (2 decimales) en col D de 'Datos Control'."""
    from datetime import datetime
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Datos Control'!A1:B2",
        valueInputOption="USER_ENTERED",
        body={"values": [
            ["ESTADO",        f"PENDIENTE - {ahora}"],
            ["FECHA_CONTROL", control_date.strftime("%d/%m/%Y")],
        ]},
    ).execute()

    r = sheets_svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Datos Control'!A1:D200",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    filas = r.get("values", [])
    pct_map = {b["nombre"]: b["pct_real"] for b in beneficiarios}

    updates = []
    for i, fila in enumerate(filas):
        if len(fila) < 2:
            continue
        col_b = _normalizar(str(fila[1]).strip())
        if col_b in pct_map:
            updates.append({
                "range":  f"'Datos Control'!D{i + 1}",
                "values": [[round(pct_map[col_b], 2)]],
            })

    if updates:
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()
        log.info(f"  Datos Control: {len(updates)} filas actualizadas")


# ─── PASO 9: ACTUALIZAR FIREBASE ──────────────────────────────────────────────
def actualizar_firebase(project_id: str, beneficiarios: list,
                        pcts_prog: dict, control_date: date):
    import requests
    n = len(beneficiarios)
    if not n:
        return
    pct_total = round(sum(b["pct_real"] for b in beneficiarios) / n, 2)
    payload = {
        "pct":      pct_total,   # campo que lee el dashboard
        "pct_real": pct_total,
        "pct_prog": round(pcts_prog.get("TOTAL", 0.0), 2),
        "fecha":    control_date.isoformat(),
        "n_benef":  n,
    }
    try:
        r = requests.patch(f"{_ccu.FIREBASE_URL}/avance_gantt/{project_id}.json",
                           json=payload, timeout=20)
        r.raise_for_status()
        log.info(f"  Firebase avance_gantt/{project_id}: {pct_total}%")
    except Exception as e:
        log.error(f"  Firebase error: {e}")


# ─── PASO 10: ACTUALIZAR DASHBOARD (GitHub API) ───────────────────────────────
def actualizar_dashboard(all_drive_ids: dict):
    """Actualiza CURVAS_S_CONFIG en app_compiled.js via GitHub API."""
    import base64
    import requests

    token = _ccu.get_github_token()
    if not token:
        log.error("Sin token GitHub — dashboard no actualizado")
        return

    cfg = _cargar_config()

    # Construir nuevo bloque CURVAS_S_CONFIG
    import time as _time
    ts = int(_time.time())  # timestamp para cache-busting de thumbnails Drive
    lines = ["const CURVAS_S_CONFIG = {"]
    for proy in cfg["proyectos"]:
        pid    = proy["id"]
        nombre = proy["nombre"]
        ids    = all_drive_ids.get(pid, {})
        if not ids:
            continue
        grupos  = sorted(k for k in ids if k.startswith("GRUPO") and k != "GRUPO REZAGADOS")
        rezag   = ["GRUPO REZAGADOS"] if "GRUPO REZAGADOS" in ids else []
        finales = [k for k in ("TOTAL", "TODOS_GRUPOS") if k in ids]
        lines.append(f"    '{pid}': [")
        for key in grupos + rezag + finales:
            fid = ids[key]
            if key == "TOTAL":
                label = f"Total Proyecto · {nombre}"
            elif key == "TODOS_GRUPOS":
                label = f"Todos los Grupos · {nombre}"
            elif key == "GRUPO REZAGADOS":
                label = f"Grupo Rezagados · {nombre}"
            else:
                num = key.replace("GRUPO ", "")
                label = f"Grupo {num} · {nombre}"
            lines.append(f"        {{ id: '{fid}', label: '{label}', v: '{ts}' }},")
        lines.append("    ],")
    lines.append("};")
    nuevo_config = "\n".join(lines)

    # Descargar app_compiled.js desde GitHub
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}?ref={GITHUB_BRANCH}",
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    sha  = data["sha"]

    if data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8")
    else:
        r2 = requests.get(data["download_url"], headers={"Authorization": f"token {token}"}, timeout=60)
        r2.raise_for_status()
        content = r2.text

    nuevo_content = re.sub(
        r"const CURVAS_S_CONFIG\s*=\s*\{[\s\S]*?\};",
        nuevo_config, content,
    )
    if nuevo_content == content:
        log.info("  Dashboard sin cambios")
        return

    encoded = base64.b64encode(nuevo_content.encode("utf-8")).decode("utf-8")
    r3 = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}",
        headers=headers,
        json={
            "message": "auto: actualizar CURVAS_S_CONFIG con Drive IDs nuevos\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
            "content": encoded,
            "sha":     sha,
            "branch":  GITHUB_BRANCH,
        },
        timeout=30,
    )
    r3.raise_for_status()
    log.info("  Dashboard actualizado en GitHub")

    # Actualizar copia local si existe
    local_js = Path(r"C:\Users\rodri\PruebasWeb\SCRaices-LLM\dashboard\app_compiled.js")
    if local_js.exists():
        local_js.write_text(nuevo_content, encoding="utf-8")
        log.info("  Copia local app_compiled.js actualizada")


# ─── ORQUESTADOR PRINCIPAL ────────────────────────────────────────────────────
def procesar_proyecto(project_id: str, debug: bool = False):
    cfg    = _cargar_config()
    proy   = _proyecto_por_id(cfg, project_id)
    nombre = proy["nombre"]
    sid    = proy["spreadsheet_id"]

    log.info(f"\n{'='*60}")
    log.info(f"PROYECTO: {nombre} ({project_id})")
    log.info(f"{'='*60}")

    control_date = _lunes_actual()
    log.info(f"Fecha de control: {control_date.strftime('%d/%m/%Y')} (lunes)")

    creds      = _ccu.get_credentials()
    sheets_svc = build("sheets", "v4", credentials=creds)
    drive_svc  = build("drive",  "v3", credentials=creds)

    # 1. Beneficiarios
    beneficiarios = leer_beneficiarios_gantt(sheets_svc, sid)
    if not beneficiarios:
        log.error(f"[{project_id}] Sin beneficiarios — abortando")
        return

    # 2. % programado
    pcts_prog = leer_pct_programado(sheets_svc, sid, control_date)

    # 3. % real AppSheet
    try:
        avance_web = leer_avance_appsheet(project_id, debug=debug)
    except Exception as e:
        log.error(f"[{project_id}] Error AppSheet: {e}")
        avance_web = {b["nombre"]: b["pct_real"] for b in beneficiarios}

    # 4. Fusionar
    beneficiarios = fusionar_datos(beneficiarios, avance_web)

    # 5. Imágenes
    obra_folder   = proy["drive_folder"]
    nombre_ccu    = proy["nombre_ccu"]
    output_dir    = Path(_ccu.get_output_dir_obra(obra_folder))
    all_drive_ids = _cargar_drive_ids()

    grupos_unicos = sorted(set(b["grupo"] for b in beneficiarios))
    if "GRUPO REZAGADOS" in grupos_unicos:
        grupos_unicos.remove("GRUPO REZAGADOS")
        grupos_unicos.append("GRUPO REZAGADOS")

    grupos_data = defaultdict(list)
    for b in beneficiarios:
        grupos_data[b["grupo"]].append(b)

    safe_nombre  = re.sub(r"[^A-Za-z0-9]", "_", nombre)
    png_to_group: dict = {}   # {filename: group_key}

    for grupo in grupos_unicos:
        benef  = grupos_data[grupo]
        safe_g = re.sub(r"[^A-Za-z0-9]", "_", grupo.replace(" ", "_"))
        png    = output_dir / f"CurvaS_{safe_g}_{safe_nombre}.png"
        generar_imagen_grupo(benef, grupo, nombre, pcts_prog.get(grupo), png, control_date)
        png_to_group[png.name] = grupo

    # TOTAL (todos los beneficiarios juntos)
    png_total = output_dir / f"CurvaS_TOTAL_{safe_nombre}.png"
    generar_imagen_grupo(list(beneficiarios), f"Total · {nombre}", nombre,
                         pcts_prog.get("TOTAL"), png_total, control_date)
    png_to_group[png_total.name] = "TOTAL"

    # TODOS_GRUPOS (overlay)
    png_todos = output_dir / f"CurvaS_Todos_Grupos_{safe_nombre}.png"
    generar_imagen_todos_grupos(grupos_data, nombre, png_todos, control_date, grupos_unicos)
    png_to_group[png_todos.name] = "TODOS_GRUPOS"

    # Subir a Drive en carpeta correcta: Archivos Dashboard/Curvas PNG/{obra_folder}/
    drive_result = _ccu.actualizar_drive_organizado(
        drive_svc, str(output_dir), list(png_to_group.keys()), obra_folder, nombre_ccu
    )
    nuevos_ids = {group_key: drive_result[fname]
                  for fname, group_key in png_to_group.items()
                  if fname in drive_result}

    # 6. Guardar IDs
    all_drive_ids[project_id] = nuevos_ids
    _guardar_drive_ids(all_drive_ids)

    # 7. Hoja Curvas S
    actualizar_curvas_s_sheet(sheets_svc, sid, nuevos_ids, control_date)

    # 8. Datos Control
    actualizar_datos_control(sheets_svc, sid, beneficiarios, control_date)

    # 9. Firebase
    actualizar_firebase(project_id, beneficiarios, pcts_prog, control_date)

    log.info(f"[{project_id}] ✓ {nombre} completado")


def procesar_todos(debug: bool = False):
    cfg     = _cargar_config()
    errores = []
    for proy in cfg["proyectos"]:
        try:
            procesar_proyecto(proy["id"], debug=debug)
        except Exception as e:
            log.error(f"[{proy['id']}] ERROR: {e}")
            errores.append(proy["id"])

    log.info("\nActualizando dashboard...")
    actualizar_dashboard(_cargar_drive_ids())

    if errores:
        log.warning(f"Proyectos con error: {errores}")
    else:
        log.info("Todos los proyectos completados")


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args_raw = sys.argv[1:]

    if not args_raw:
        print("Uso:")
        print("  python curvas_master.py P119              # Un proyecto")
        print("  python curvas_master.py --todos           # Todos")
        print("  python curvas_master.py P119 --debug      # Browser visible")
        print("  python curvas_master.py --sync-dashboard  # Solo dashboard")
        sys.exit(1)

    debug = "--debug" in args_raw
    args  = [a for a in args_raw if not a.startswith("--")]

    if "--sync-dashboard" in args_raw:
        log.info("Modo: sincronización de dashboard")
        actualizar_dashboard(_cargar_drive_ids())

    elif "--todos" in args_raw:
        procesar_todos(debug=debug)

    elif args:
        procesar_proyecto(args[0], debug=debug)
        log.info("Actualizando dashboard...")
        actualizar_dashboard(_cargar_drive_ids())

    else:
        log.error("Argumento no reconocido")
        sys.exit(1)

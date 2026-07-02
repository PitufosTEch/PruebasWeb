"""
sincronizar_dashboard.py
========================
Sincroniza CURVAS_S_CONFIG en el dashboard GitHub con los Drive IDs
locales de todos los proyectos. Se ejecuta automaticamente al final
de ejecutar_curvas_semanal.bat, o manualmente:

    python sincronizar_dashboard.py

Flujo:
  1. Lee todos los drive_ids_*.json locales
  2. Descarga el HTML del dashboard desde GitHub
  3. Compara CURVAS_S_CONFIG actual con el esperado
  4. Si hay diferencias: actualiza el HTML y hace push via GitHub API
  5. Registra resultado en log
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import requests
import curvas_cloud_utils as _ccu

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────────────────────────────────────
DRIVE_IDS_DIR   = r"C:\Users\rodri\OneDrive\Documentos Claude Code"
GITHUB_REPO     = "PitufosTEch/PruebasWeb"
GITHUB_FILE     = "SCRaices-LLM/dashboard/index_live_v3.html"
GITHUB_BRANCH   = "master"
GITHUB_TOKEN_FILE = r"C:\Users\rodri\.claude\github_token.txt"  # fallback local

log = _ccu.setup_logging("sincronizar_dashboard")

# Mapeo proyecto_id → metadatos para construir labels legibles
PROYECTOS_META = {
    "P119": {
        "nombre": "Ñuke Mapu",
        "json": None,
        "hardcoded": {
            "CurvaS_TOTAL_Nuke_Mapu.png":    ("Total Proyecto · Ñuke Mapu",        1),
            "CurvaS_Todos_Grupos.png":        ("Todos los Grupos · Ñuke Mapu",      2),
            "CurvaS_GRUPO_1.png":             ("Grupo 1 · Ñuke Mapu",              3),
            "CurvaS_GRUPO_2.png":             ("Grupo 2 · Ñuke Mapu",              4),
            "CurvaS_GRUPO_3.png":             ("Grupo 3 · Ñuke Mapu",              5),
            "CurvaS_GRUPO_4.png":             ("Grupo 4 · Ñuke Mapu",              6),
            "CurvaS_GRUPO_5.png":             ("Grupo 5 · Ñuke Mapu",              7),
        },
        "id": "P119",
    },
    "P38":  {"nombre": "Aliwen",              "json": "drive_ids_aliwen.json",    "id": "P38"},
    "P126": {"nombre": "El Maitén",           "json": "drive_ids_maiten.json",    "id": "P126"},
    "P39":  {"nombre": "El Coihue",           "json": "drive_ids_coihue.json",    "id": "P39"},
    "P127": {"nombre": "Nuevo Cunco",         "json": "drive_ids_cunco.json",     "id": "P127"},
    "P12":  {"nombre": "Juan Huilcan Tolten", "json": "drive_ids_huilcan.json",   "id": "P12"},
    "P14":  {"nombre": "Com. Madihue",        "json": "drive_ids_madihue.json",   "id": "P14"},
    "P116": {"nombre": "Sonia Quilaleo",      "json": "drive_ids_quilaleo.json",  "id": "P116"},
    "P31":  {"nombre": "Trovolhue",           "json": "drive_ids_trovolhue.json", "id": "P31"},
    "P131": {"nombre": "Raíces de Melipeuco", "json": "drive_ids_melipeuco.json", "id": "P131"},
    "P28":  {"nombre": "Elsa Pinchulaf",      "json": "drive_ids_pinchulaf.json", "id": "P28"},
}

# Orden de aparición preferido: TOTAL primero, luego Todos_Grupos, luego grupos individuales
def _sort_key(filename):
    f = filename.upper()
    if "TOTAL_" in f and "TODOS" not in f:
        return 0
    if "TODOS" in f:
        return 1
    m = re.search(r"GRUPO_(\d+)", f)
    if m:
        return 2 + int(m.group(1))
    if "REZAGADOS" in f:
        return 90
    return 99

def _label(filename, nombre_proy):
    f = filename
    if re.search(r"TOTAL_", f, re.I) and "TODOS" not in f.upper():
        return f"Total Proyecto · {nombre_proy}"
    if "TODOS" in f.upper():
        return f"Todos los Grupos · {nombre_proy}"
    m = re.search(r"GRUPO_(\d+)", f, re.I)
    if m:
        return f"Grupo {m.group(1)} · {nombre_proy}"
    if "REZAGADOS" in f.upper():
        return f"Grupo Rezagados · {nombre_proy}"
    return f"{f} · {nombre_proy}"

# ─────────────────────────────────────────────────────────────────────────────
# TOKEN: env var (cloud) → gh CLI → archivo manual
# ─────────────────────────────────────────────────────────────────────────────
def _get_github_token():
    return _ccu.get_github_token()


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONSTRUIR CONFIG ESPERADA
#    Cloud: desde Firebase RTDB (/curvas_drive_ids/{nombre})
#    Local: desde drive_ids_*.json en OneDrive
# ─────────────────────────────────────────────────────────────────────────────
# Mapeo proyecto_id → nombre_firebase (clave en /curvas_drive_ids/)
_FIREBASE_NOMBRE = {
    "P38":  "aliwen",
    "P126": "maiten",
    "P39":  "coihue",
    "P127": "cunco",
    "P12":  "huilcan",
    "P14":  "madihue",
    "P116": "quilaleo",
    "P31":  "trovolhue",
    "P131": "melipeuco",
    "P28":  "pinchulaf",
}


def _load_ids_para_proyecto(proy_id: str, meta: dict) -> dict:
    """Carga drive_ids para un proyecto desde Firebase (cloud) o JSON local."""
    if _ccu.is_cloud():
        nombre_fb = _FIREBASE_NOMBRE.get(proy_id)
        if not nombre_fb:
            return {}
        return _ccu.load_drive_ids(nombre_fb)

    # Modo local
    json_path = Path(DRIVE_IDS_DIR) / meta["json"]
    if not json_path.exists():
        log.warning(f"  [{proy_id}] JSON no encontrado: {json_path}")
        return {}
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def build_expected_config():
    config = {}
    for proy_id, meta in PROYECTOS_META.items():
        nombre = meta["nombre"]

        if meta.get("hardcoded"):
            entries = []
            for fname, (label, order) in sorted(meta["hardcoded"].items(), key=lambda x: x[1][1]):
                entries.append({"id": "PLACEHOLDER", "label": label, "fname": fname})
            config[proy_id] = entries
            continue

        ids = _load_ids_para_proyecto(proy_id, meta)
        if not ids:
            continue

        entries = []
        for fname in sorted(ids.keys(), key=_sort_key):
            entries.append({"id": ids[fname], "label": _label(fname, nombre)})
        config[proy_id] = entries

    return config

# ─────────────────────────────────────────────────────────────────────────────
# 2. DESCARGAR HTML desde GitHub
# ─────────────────────────────────────────────────────────────────────────────
def download_html(token):
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}?ref={GITHUB_BRANCH}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    sha = data["sha"]
    # Archivos >1MB: GitHub no incluye 'content', usa download_url en su lugar
    if data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8")
    elif data.get("download_url"):
        log.info("Archivo >1MB, descargando via download_url...")
        r2 = requests.get(data["download_url"], headers={"Authorization": f"token {token}"}, timeout=60)
        r2.raise_for_status()
        content = r2.text
    else:
        raise RuntimeError("No se pudo descargar el HTML: respuesta sin 'content' ni 'download_url'.")
    return content, sha

# ─────────────────────────────────────────────────────────────────────────────
# 3. EXTRAER CURVAS_S_CONFIG ACTUAL del HTML
# ─────────────────────────────────────────────────────────────────────────────
def extract_current_config(html):
    m = re.search(r"const CURVAS_S_CONFIG = \{(.+?)\};", html, re.DOTALL)
    if not m:
        raise RuntimeError("No se encontró CURVAS_S_CONFIG en el HTML.")
    block = m.group(1)
    current = {}
    for proy_m in re.finditer(r"'(P\d+)'\s*:\s*\[(.+?)\]", block, re.DOTALL):
        proy_id = proy_m.group(1)
        items_block = proy_m.group(2)
        entries = []
        for item_m in re.finditer(r"\{\s*id:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'\s*\}", items_block):
            entries.append({"id": item_m.group(1), "label": item_m.group(2)})
        current[proy_id] = entries
    return current

# ─────────────────────────────────────────────────────────────────────────────
# 4. GENERAR NUEVO BLOQUE JS
# ─────────────────────────────────────────────────────────────────────────────
def build_new_js_block(expected_config, current_config):
    """
    Para P119 (hardcoded) usa los IDs del config actual.
    Para el resto usa los IDs de los JSON locales.
    """
    lines = ["const CURVAS_S_CONFIG = {"]
    for proy_id, entries in expected_config.items():
        lines.append(f"    '{proy_id}': [")
        # Para P119, rellenar IDs desde el config actual
        if proy_id == "P119":
            current_entries = {e["label"]: e["id"] for e in (current_config.get("P119") or [])}
            # Usar los IDs del hardcoded de Ñuke Mapu que ya están en los scripts Python
            hardcoded_ids = {
                "CurvaS_TOTAL_Nuke_Mapu.png": "11L-TIagyTGZOh3yhbGvjdIruG0dJQGPQ",
                "CurvaS_Todos_Grupos.png":    "1_xxaqAay-UeB4POTcXMaBRD_Xo5ceb-1",
                "CurvaS_GRUPO_1.png":         "1k2gpSr9Sk5zUZ3MAOxw3zGcHRa9ljFSA",
                "CurvaS_GRUPO_2.png":         "1Ciu52kLYT9NjgaqUBPif4mtWk6l0RtPm",
                "CurvaS_GRUPO_3.png":         "1mDdpyG5zGmSgOXZVMN4qzGbp_0BMrzT2",
                "CurvaS_GRUPO_4.png":         "1GHthHYK1bpoA7_2Q5qSm3VFJq4KPYQa_",
                "CurvaS_GRUPO_5.png":         "12yQw_tt3W4H91Q4KpiMafm_eLUNkwqpP",
            }
            for e in entries:
                drive_id = hardcoded_ids.get(e["fname"], current_entries.get(e["label"], "MISSING"))
                lines.append(f"        {{ id: '{drive_id}', label: '{e['label']}' }},")
        else:
            for e in entries:
                lines.append(f"        {{ id: '{e['id']}', label: '{e['label']}' }},")
        lines.append("    ],")
    lines.append("};")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# 5. REEMPLAZAR en el HTML y subir a GitHub
# ─────────────────────────────────────────────────────────────────────────────
def update_github(html, sha, new_js_block, token):
    new_html = re.sub(
        r"const CURVAS_S_CONFIG = \{.+?\};",
        new_js_block,
        html,
        flags=re.DOTALL,
    )
    import base64
    encoded = base64.b64encode(new_html.encode("utf-8")).decode("utf-8")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    payload = {
        "message": "auto: sincronizar CURVAS_S_CONFIG con Drive IDs actualizados",
        "content": encoded,
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }
    r = requests.put(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    log.info("  Dashboard actualizado en GitHub.")
    return new_html

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("SINCRONIZAR DASHBOARD — CURVAS_S_CONFIG")
    log.info("=" * 60)

    # Obtener token: primero gh CLI, luego archivo manual
    token = _get_github_token()
    if not token:
        log.error("No se encontró token de GitHub.")
        log.error("Ejecuta UNA VEZ en la terminal:  gh auth login")
        log.error("Selecciona GitHub.com → HTTPS → autenticar con navegador.")
        sys.exit(1)
    log.info("Token GitHub obtenido.")

    # Construir config esperada desde JSONs locales
    expected = build_expected_config()
    log.info(f"Config local: {len(expected)} proyectos")

    # Descargar HTML actual
    log.info("Descargando dashboard desde GitHub...")
    html, sha = download_html(token)

    # Extraer config actual
    current = extract_current_config(html)
    log.info(f"Config actual en dashboard: {len(current)} proyectos")

    # Comparar
    diferencias = []
    for proy_id, entries in expected.items():
        if proy_id == "P119":
            continue  # IDs hardcodeados, no cambian
        curr_ids = {e["id"] for e in (current.get(proy_id) or [])}
        exp_ids  = {e["id"] for e in entries}
        if curr_ids != exp_ids or proy_id not in current:
            diferencias.append(proy_id)
            log.info(f"  [{proy_id}] DIFERENCIA DETECTADA")
            log.info(f"    Actual:   {curr_ids}")
            log.info(f"    Esperado: {exp_ids}")

    # Proyectos nuevos en local que no están en dashboard
    for proy_id in expected:
        if proy_id not in current:
            diferencias.append(proy_id)
            log.info(f"  [{proy_id}] NUEVO — no estaba en el dashboard")

    if not diferencias:
        log.info("Dashboard ya está sincronizado. Sin cambios necesarios.")
        log.info("=" * 60)
        return

    log.info(f"\n{len(diferencias)} proyecto(s) con diferencias. Actualizando dashboard...")
    new_block = build_new_js_block(expected, current)
    update_github(html, sha, new_block, token)
    log.info(f"\nSincronizacion completada. {len(diferencias)} proyecto(s) actualizados.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()

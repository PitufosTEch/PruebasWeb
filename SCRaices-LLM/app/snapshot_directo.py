"""
snapshot_directo.py
===================
Abre el dashboard en Chrome headless, espera que carguen los datos en vivo
(ya no requiere sesión de Google — el deployment es anónimo), captura
window.__SNAPSHOT__ y lo sube a GitHub como data_snapshot.json.

Ejecutar manualmente o via tarea programada cada 30 min.
"""

import base64, json, os, sys, time, threading
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

DASHBOARD_URL = (
    "https://pitufostech.github.io/PruebasWeb/"
    "SCRaices-LLM/dashboard/index_live_v3.html"
)
APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxcJowX3a3XBmSNiKOCesj1jRkQWS1VIsMbvdt-x7ckK8ZXMauI6gRgCGsoT77xYxpP/exec"
)
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = "PitufosTEch/PruebasWeb"
GITHUB_BRANCH = "data-snapshot"
GITHUB_FILE   = "data_snapshot.json"
SNAPSHOT_URL  = "https://raw.githubusercontent.com/PitufosTEch/PruebasWeb/data-snapshot/data_snapshot.json"
WAIT_TIMEOUT  = 420  # segundos máximos esperando datos en vivo (fallback browser)

REPO_DIR   = Path(__file__).resolve().parents[2]  # C:\Users\rodri\PruebasWeb
SNAP_FILE  = REPO_DIR / GITHUB_FILE


def push_via_git(content: str) -> bool:
    """Usa el repo git local — método preferido, no necesita token."""
    import subprocess

    def run(cmd, timeout=60):
        return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout)

    try:
        ts = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())
        # Guardar cambios en curso del branch actual
        run(["git", "stash"])
        # Sincronizar data-snapshot con upstream y escribir el archivo
        run(["git", "fetch", "upstream", GITHUB_BRANCH])
        run(["git", "checkout", "-B", GITHUB_BRANCH, f"upstream/{GITHUB_BRANCH}"])
        SNAP_FILE.write_text(content, encoding="utf-8")
        run(["git", "add", GITHUB_FILE])
        r = run(["git", "commit", "-m", f"data: snapshot {ts}"])
        if r.returncode != 0 and "nothing to commit" in r.stdout + r.stderr:
            print("Sin cambios desde el último snapshot")
            run(["git", "checkout", "master"])
            run(["git", "stash", "pop"])
            return True
        r = run(["git", "push", "upstream", GITHUB_BRANCH])
        run(["git", "checkout", "master"])
        run(["git", "stash", "pop"])
        if r.returncode == 0:
            print(f"✓ Snapshot subido via git ({len(content)//1024} KB)")
            return True
        print(f"ERROR git push: {r.stderr[:300]}")
        return False
    except Exception as e:
        # Intentar volver a master en caso de error
        try:
            run(["git", "checkout", "master"])
            run(["git", "stash", "pop"])
        except Exception:
            pass
        print(f"ERROR push_via_git: {e}")
        return False


def push_to_github(content: str) -> bool:
    """Fallback: GitHub API con token."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN no definido, saltando API push")
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    sha = None
    r = requests.get(url, params={"ref": GITHUB_BRANCH}, headers=headers, timeout=15)
    if r.status_code == 200:
        sha = r.json()["sha"]
    payload: dict = {
        "message": f"data: snapshot {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, json=payload, headers=headers, timeout=30)
    if r.status_code in (200, 201):
        print(f"✓ Snapshot subido via API ({len(content)//1024} KB)")
        return True
    print(f"ERROR GitHub HTTP {r.status_code}: {r.text[:300]}")
    return False


def capture_snapshot(ej_rows: list | None = None) -> str | None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context()
        page = context.new_page()

        live_ok = False

        def on_console(msg):
            nonlocal live_ok
            text = msg.text
            if "[LIVE] Datos en vivo cargados" in text or "[LIVE] Datos actualizados" in text:
                live_ok = True
                print(f"  → {text}")
            elif "[v3 LIVE]" in text or "[SNAPSHOT]" in text or "[LIVE]" in text:
                print(f"  → {text}")

        page.on("console", on_console)

        # Interceptar Solpago para evitar el timeout que bloquea Promise.all.
        # Si Solpago falla, processRawData nunca corre y los rows de Ejecucion
        # inyectados se ignoran. Devolvemos vacío en <1s para que el pipeline
        # complete y procese todas las partidas + cierre desde Ejecucion.
        def _mock_solpago(route):
            if "tables=Solpago" in route.request.url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"Solpago": {"rows": []}}),
                )
                print("  → [ROUTE] Solpago interceptado → vacío (evita timeout)")
            else:
                route.continue_()

        page.route("**/macros/**exec**", _mock_solpago)

        print(f"Abriendo dashboard: {DASHBOARD_URL}")
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60_000)

        # Inyectar Ejecucion ANTES de que processRawData corra (live fetch tarda ~30s)
        if ej_rows:
            print(f"  Inyectando {len(ej_rows)} filas de Ejecucion en window.__EJECUCION_ROWS__...")
            # Serializar en chunks para evitar límites del evaluate
            chunk_size = 500
            page.evaluate("() => { window.__EJECUCION_ROWS__ = []; }")
            for i in range(0, len(ej_rows), chunk_size):
                chunk = ej_rows[i:i + chunk_size]
                page.evaluate(f"(rows) => {{ window.__EJECUCION_ROWS__.push(...rows); }}", chunk)
            print(f"  ✓ Inyectadas {len(ej_rows)} filas")

        deadline = time.time() + WAIT_TIMEOUT
        while time.time() < deadline:
            if live_ok:
                break
            time.sleep(2)

        if not live_ok:
            print("Advertencia: datos en vivo no confirmados, capturando igualmente")

        # Dar tiempo extra para que renderApp() termine con INSPECCIONES_DATA
        time.sleep(5)

        snapshot = page.evaluate("() => typeof window.__SNAPSHOT__ !== 'undefined' ? JSON.stringify(window.__SNAPSHOT__) : null")
        browser.close()

        if not snapshot:
            print("ERROR: window.__SNAPSHOT__ no disponible")
            return None

        data = json.loads(snapshot)
        size_kb = len(snapshot) // 1024
        insp = len(data.get("INSPECCIONES_DATA", []))
        proy = len(data.get("PROYECTOS_DATA", []))
        benef = len(data.get("BENEFICIARIOS_DATA", []))
        print(f"✓ Snapshot capturado: {size_kb} KB | {proy} proyectos | {benef} benef | {insp} inspecciones")
        return snapshot


def fetch_ejecucion_full() -> list | None:
    """Descarga la tabla Ejecucion completa con timeout extendido (6 min)."""
    print("Descargando tabla Ejecucion completa (puede tardar ~5 min)...")
    t0 = time.time()
    try:
        r = requests.get(f"{APPS_SCRIPT_URL}?tables=Ejecucion", timeout=370)
        if r.status_code != 200:
            print(f"  ERROR HTTP {r.status_code}")
            return None
        data = r.json()
        ej = data.get("Ejecucion", {})
        if "error" in ej:
            print(f"  ERROR: {ej['error']}")
            return None
        rows = ej.get("rows", [])
        elapsed = time.time() - t0
        print(f"✓ Ejecucion completa: {len(rows)} filas en {elapsed:.0f}s")
        return rows
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def build_inspecciones_data(ej_rows: list) -> list:
    """Construye INSPECCIONES_DATA desde las filas crudas de Ejecucion.
    Replica la lógica de app_source.jsx lines 556-615.
    """
    INSP_FIELDS = [
        "A_Fund", "A_Alc", "A_Alc_Ext", "A_Rad", "A_Tab", "A_Tec",
        "A_Rev_Ext", "A_Cub", "A_Vent", "A_Cer_Piso", "A_Cie", "A_Alero",
        "A_Red_El", "A_Ag_Pot", "A_Ais_Cie", "A_Rev_Sec", "A_Rev_Hum",
        "A_Ais_Mur", "A_Cer_Mur", "A_Pin_Ext", "A_Pin_Int", "A_Pue",
        "A_Mol", "A_Art_Coc", "A_Art_Ban", "A_Ag_Pot_Ext", "A_Art_El",
        "A_Ins_Elec_Ext", "A_Ins_Elec_Int",
    ]
    # Agrupa por ID_benef (o IDU si no hay ID_benef) → toma último valor por campo
    from collections import defaultdict
    groups: dict = defaultdict(dict)
    for row in ej_rows:
        bid = str(row.get("ID_benef") or row.get("IDU") or "").strip()
        if not bid:
            continue
        for f in INSP_FIELDS:
            v = row.get(f)
            if v is not None and v != "":
                groups[bid][f] = v
        # Metadata
        for meta in ["ID_proy", "nombre", "Empalme", "Habilitado"]:
            v = row.get(meta)
            if v is not None and v != "":
                groups[bid][meta] = v
    result = []
    for bid, fields in groups.items():
        entry = {"ID_benef": bid}
        entry.update(fields)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Lógica Python-nativa: replicar VIV_COLUMNS + CIERRE_COLS del dashboard JS
# para reconstruir INSPECCIONES_DATA sin necesidad de browser.
# ---------------------------------------------------------------------------

_VIV_COLUMNS = {
    "A_Fund":          {"short": "Fundaciones",       "weight": 0.02},
    "A_Radier":        {"short": "Radier",             "weight": 0.04},
    "A_Planta_Alc":    {"short": "Alcantarillado",     "weight": 0.01},
    "A_E_Tabiques":    {"short": "Tabiques",           "weight": 0.06},
    "A_E_Techumbre":   {"short": "Techumbre",          "weight": 0.04},
    "A_rev Ext":       {"short": "Rev. Exterior",      "weight": 0.06},
    "A_vent":          {"short": "Ventanas",           "weight": 0.03},
    "A_Cubierta":      {"short": "Cubierta",           "weight": 0.03},
    "A_Ent_Cielo":     {"short": "Cielo",              "weight": 0.02},
    "A_ent_alero":     {"short": "Alero",              "weight": 0.02},
    "A_Red_AP":        {"short": "Red Agua Pot.",      "weight": 0.03},
    "A_Red_Elect":     {"short": "Red Eléctrica",      "weight": 0.04},
    "A_rev_ZS":        {"short": "Rev. Zona Seca",     "weight": 0.04},
    "A_rev_ZH":        {"short": "Rev. Zona Húmeda",   "weight": 0.02},
    "A_Aisl_Muro":     {"short": "Aisl. Muro",         "weight": 0.04},
    "A_Aisl_Cielo":    {"short": "Aisl. Cielo",        "weight": 0.03},
    "A_Cer_Piso":      {"short": "Cerámico Piso",      "weight": 0.05},
    "A_Cer_muro":      {"short": "Cerámico Muro",      "weight": 0.03},
    "A_pint_Ext":      {"short": "Pintura Ext.",        "weight": 0.04},
    "A_pint_int":      {"short": "Pintura Int.",        "weight": 0.02},
    "A_puertas":       {"short": "Puertas",            "weight": 0.05},
    "A_molduras":      {"short": "Molduras",           "weight": 0.02},
    "A_Art_Baño":      {"short": "Art. Baño",          "weight": 0.05},
    "A_Art_cocina":    {"short": "Art. Cocina",        "weight": 0.02},
    "A_Art_Elec":      {"short": "Art. Eléctricos",    "weight": 0.04},
    "A_AP_Ext":        {"short": "Agua Pot. Ext.",     "weight": 0.05},
    "A_ALC_Ext":       {"short": "Alcant. Ext.",       "weight": 0.05},
    "A_Ins_Elec_Ext":  {"short": "Inst. Eléc. Ext.",   "weight": 0.05},
}

_CIERRE_COLS = {"empalme": "E", "preF1": "P", "desarme": "D", "ret_escombro": "R", "aseo": "A"}


def _parse_insp_val(val) -> float:
    if val is None or val == "" or val == "nan":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val) if val <= 1.5 else float(val) / 100
    s = str(val).strip().replace("%", "").replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return 0.0
    return n / 100 if n > 1.5 else n


def _parse_date_ej(val) -> str:
    import re
    if not val or val in ("nan", "NaT", ""):
        return ""
    s = str(val).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        p1, p2, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if p1 > 12:
            return f"{year}-{p2:02d}-{p1:02d}"
        if p2 > 12:
            return f"{year}-{p1:02d}-{p2:02d}"
        return f"{year}-{p1:02d}-{p2:02d}"
    if "T" in s:
        return s[:10]
    return ""


def build_inspecciones_data_py(ej_rows: list, ids_benef: set) -> list:
    """Replica exacta de la lógica JS processRawData para INSPECCIONES_DATA.
    Trabaja sin browser: solo filas de Ejecucion + set de IDs válidos.
    """
    if not ej_rows:
        return []

    sample = ej_rows[0]
    has_barno = "A_Art_Bano" in sample and "A_Art_Baño" not in sample
    rc_cols = [k for k in sample.keys() if k.startswith("AB_")]
    has_hab = "A_Habilitacion" in sample

    insp_map: dict = {}

    for e in ej_rows:
        id_b = str(e.get("ID_Benef") or e.get("ID_benef") or "").strip()
        if not id_b or id_b not in ids_benef:
            continue
        if id_b not in insp_map:
            insp_map[id_b] = {
                "ID_Benef": id_b,
                "partidas": {},
                "rc_vals": {},
                "hab_sum": 0.0,
                "n_insp": 0,
                "ultima_insp": "",
                "cierre": {},
            }
        rec = insp_map[id_b]
        rec["n_insp"] += 1

        for col, info in _VIV_COLUMNS.items():
            actual = "A_Art_Bano" if (col == "A_Art_Baño" and has_barno) else col
            val = _parse_insp_val(e.get(actual))
            if val > 0:
                short = info["short"]
                rec["partidas"][short] = min(1.0, (rec["partidas"].get(short) or 0.0) + val)

        for col in rc_cols:
            val = _parse_insp_val(e.get(col))
            if val > 0:
                rec["rc_vals"][col] = min(1.0, (rec["rc_vals"].get(col) or 0.0) + val)

        if has_hab:
            val = _parse_insp_val(e.get("A_Habilitacion"))
            if val > 0:
                rec["hab_sum"] = min(1.0, rec["hab_sum"] + val)

        f_insp = _parse_date_ej(e.get("Fecha_creacion") or e.get("fecha_creacion") or "")
        if f_insp and f_insp > rec["ultima_insp"]:
            rec["ultima_insp"] = f_insp

        for col, label in _CIERRE_COLS.items():
            val = str(e.get(col) or "").strip().lower()
            if val and val != "nan":
                cur = rec["cierre"].get(label)
                if val == "terminado":
                    rec["cierre"][label] = 1
                elif val in ("n/a", "na", "n.a.", "no aplica", "no_aplica"):
                    if cur != 1:
                        rec["cierre"][label] = -1
                elif cur not in (1, -1):
                    rec["cierre"][label] = 0

    result = []
    for insp in insp_map.values():
        pct_viv = sum(
            min(1.0, max(0.0, insp["partidas"].get(info["short"]) or 0.0)) * info["weight"]
            for info in _VIV_COLUMNS.values()
        )
        rc_vals = list(insp["rc_vals"].values())
        pct_rc = (
            sum(min(1.0, max(0.0, v)) for v in rc_vals) / len(rc_vals)
            if rc_vals else 0.0
        )
        pct_hab = min(1.0, max(0.0, insp["hab_sum"]))
        pct_total = pct_viv * 0.7 + pct_rc * 0.25 + pct_hab * 0.05

        partidas_100 = {
            k: round(min(1.0, max(0.0, v)) * 100)
            for k, v in insp["partidas"].items()
        }

        result.append({
            "ID_Benef":    insp["ID_Benef"],
            "pct_viv":     round(pct_viv * 1000) / 10,
            "pct_rc":      round(pct_rc * 1000) / 10,
            "pct_hab":     round(pct_hab * 1000) / 10,
            "pct_total":   round(pct_total * 1000) / 10,
            "ultima_insp": insp["ultima_insp"],
            "n_insp":      insp["n_insp"],
            "partidas":    partidas_100,
            "cierre":      insp["cierre"],
        })

    return result


def fetch_beneficiarios_ids() -> set | None:
    """Descarga Beneficiario y retorna set de ID_Benef válidos."""
    print("Descargando Beneficiarios para IDs válidos...")
    t0 = time.time()
    try:
        r = requests.get(f"{APPS_SCRIPT_URL}?tables=Beneficiario", timeout=120)
        if r.status_code != 200:
            print(f"  ERROR HTTP {r.status_code}")
            return None
        rows = r.json().get("Beneficiario", {}).get("rows", [])
        ids = {str(b.get("ID_Benef") or b.get("IDU_Benef") or "").strip() for b in rows}
        ids.discard("")
        print(f"  ✓ {len(ids)} IDs en {time.time() - t0:.0f}s")
        return ids
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def fetch_current_snapshot() -> dict | None:
    """Descarga el snapshot actual desde GitHub CDN."""
    print("Descargando snapshot actual desde GitHub CDN...")
    try:
        r = requests.get(f"{SNAPSHOT_URL}?t={int(time.time())}", timeout=30)
        if r.status_code != 200:
            print(f"  ERROR HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def _parse_monto_uf(raw) -> float:
    s = str(raw or "0").strip()
    if not s or s in ("nan", "None"):
        return 0.0
    if "," in s and "." in s:
        try:
            return round(float(s.replace(".", "").replace(",", ".")) * 100) / 100
        except ValueError:
            return 0.0
    elif "," in s:
        try:
            return round(float(s.replace(",", ".")) * 100) / 100
        except ValueError:
            return 0.0
    else:
        try:
            return round((float(s) if s else 0.0) * 100) / 100
        except ValueError:
            return 0.0


def _norm_proy_id(raw) -> str:
    """Normaliza IDs numéricos: '122' → 'P122' (igual que el JS)."""
    s = str(raw or "").strip()
    return "P" + s if s.isdigit() else s


def build_eepp_data_py(eepp_rows: list, ids_proy_activos: set) -> list:
    """Replica la lógica JS de procesamiento de controlEEPP para EEPP_DATA."""
    result = []
    for ep in eepp_rows:
        id_proy = _norm_proy_id(ep.get("ID_Proy", ""))
        if id_proy not in ids_proy_activos:
            continue
        result.append({
            "ID_Proy":  id_proy,
            "ID_Benef": str(ep.get("ID_Benef", "")),
            "Num_EP":   str(ep.get("Num_EP", "")),
            "Monto":    _parse_monto_uf(ep.get("Monto")),
            "Estado":   str(ep.get("Estado", "")),
            "Fecha":    _parse_date_ej(ep.get("Fecha") or ""),
        })
    return result


def fetch_control_eepp() -> list | None:
    """Descarga la tabla controlEEPP desde Apps Script."""
    print("Descargando controlEEPP desde Apps Script...")
    t0 = time.time()
    try:
        r = requests.get(f"{APPS_SCRIPT_URL}?tables=controlEEPP", timeout=120)
        if r.status_code != 200:
            print(f"  ERROR HTTP {r.status_code}")
            return None
        rows = r.json().get("controlEEPP", {}).get("rows", [])
        print(f"  ✓ {len(rows)} EPs en {time.time() - t0:.0f}s")
        return rows
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def main() -> int:
    print("=" * 60)
    print("snapshot_directo.py — captura + push a GitHub")
    print(f"Hora: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    ej_rows = fetch_ejecucion_full()

    snapshot_str = None

    # Flujo primario: Python-nativo — no depende del browser ni de Solpago.
    # Parchea solo INSPECCIONES_DATA en el snapshot existente.
    if ej_rows:
        ids_benef = fetch_beneficiarios_ids()
        if ids_benef:
            current_snap = fetch_current_snapshot()
            if current_snap:
                # Patch INSPECCIONES_DATA
                new_insp = build_inspecciones_data_py(ej_rows, ids_benef)
                con_cierre = sum(1 for r in new_insp if r.get("cierre"))
                current_snap["INSPECCIONES_DATA"] = new_insp
                print(f"✓ INSPECCIONES_DATA: {len(new_insp)} registros, {con_cierre} con cierre")

                # Patch EEPP_DATA
                eepp_rows = fetch_control_eepp()
                if eepp_rows is not None:
                    ids_proy_activos = {
                        str(p.get("ID_proy") or p.get("ID_Proy") or "")
                        for p in current_snap.get("PROYECTOS_DATA", [])
                        if p.get("ID_proy") or p.get("ID_Proy")
                    }
                    new_eepp = build_eepp_data_py(eepp_rows, ids_proy_activos)
                    current_snap["EEPP_DATA"] = new_eepp
                    estados = {}
                    for ep in new_eepp:
                        estados[ep["Estado"]] = estados.get(ep["Estado"], 0) + 1
                    print(f"✓ EEPP_DATA: {len(new_eepp)} EPs — {estados}")
                else:
                    print("  AVISO: controlEEPP no disponible, EEPP_DATA sin cambios")

                current_snap["ts"] = int(time.time() * 1000)
                snapshot_str = json.dumps(current_snap, ensure_ascii=False)
                print(f"  Tamaño snapshot: {len(snapshot_str)//1024} KB")

    # Fallback: browser-based (por si el flujo Python falla)
    if not snapshot_str:
        print("Flujo Python falló — fallback: captura vía browser...")
        snap = capture_snapshot(ej_rows=ej_rows)
        if snap:
            snapshot_str = snap

    if not snapshot_str:
        print("FALLO: no se pudo generar snapshot")
        return 1

    if not push_via_git(snapshot_str):
        print("Git push falló, intentando via GitHub API...")
        if not push_to_github(snapshot_str):
            out = Path(__file__).parent / "snapshot_local.json"
            out.write_text(snapshot_str, encoding="utf-8")
            print(f"Guardado localmente: {out}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

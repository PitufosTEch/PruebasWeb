"""
leer_appsheet.py
================
Lee datos de avance (avance_obras) de cualquier proyecto AppSheet.

Modos de autenticación (en orden de prioridad):
  1. CLOUD: env var APPSHEET_COOKIES_B64 (base64 de cookies JSON)
  2. LOCAL: appsheet_auth.json (sesión Playwright guardada)
  3. LOCAL: Copia del perfil Chrome (Chrome debe estar cerrado)

Uso:
  python leer_appsheet.py          -> datos P119
  python leer_appsheet.py P38      -> datos P38
  python leer_appsheet.py --setup  -> configura auth local
"""

import base64
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import psutil
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────────────────────
APPSHEET_URL        = "https://www.appsheet.com/start/e07d4aa1-e59e-4b9b-bf4c-32582e74e8fc?platform=desktop"
TABLA_IDX           = 4
AUTH_FILE           = r"C:\Users\rodri\.claude\appsheet_auth.json"
CHROME_PROFILE      = r"C:\Users\rodri\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE_WORK = r"C:\Users\rodri\.claude\chrome_work_profile"

log = logging.getLogger(__name__)

JS_WAIT = """
() => {
    try {
        if (typeof AppModel === 'undefined') return false;
        var t = AppModel.Tables[""" + str(TABLA_IDX) + """];
        if (!t || !t.Rows) return false;
        return Object.keys(t.Rows).length > 50;
    } catch(e) { return false; }
}
"""

JS_EXTRACT = """
(projectId) => {
    var tbl = AppModel.Tables[""" + str(TABLA_IDX) + """];
    var rowKeys = Object.keys(tbl.Rows);
    var result = [];
    for (var i = 0; i < rowKeys.length; i++) {
        var row = tbl.Rows[rowKeys[i]];
        if (row.ID_Proy === projectId) {
            var pct = Math.round(parseFloat(row.avance_obras || 0) * 10000) / 100;
            result.push({
                nombre: ((row.APELLIDOS || '') + ' ' + (row.NOMBRES || '')).toUpperCase().trim(),
                avance: pct
            });
        }
    }
    return result;
}
"""


def _chrome_running():
    for p in psutil.process_iter(["name"]):
        try:
            if "chrome.exe" in p.info["name"].lower():
                return True
        except Exception:
            pass
    return False


def _extraer_datos_proyecto(page, project_id):
    log.info("  Navegando a AppSheet...")
    page.goto(APPSHEET_URL, wait_until="domcontentloaded", timeout=60_000)

    url_actual = page.url
    log.info(f"  URL actual: {url_actual[:80]}")

    if "accounts.google.com" in url_actual or "signin" in url_actual.lower():
        raise RuntimeError(
            "AppSheet redireccionó a login de Google — sesión expirada. "
            "Regenera APPSHEET_COOKIES_B64 ejecutando localmente: "
            "python leer_appsheet.py --setup"
        )

    log.info("  Esperando que AppModel cargue datos (hasta 150s)...")
    try:
        page.wait_for_function(JS_WAIT, timeout=150_000)
    except PWTimeout:
        title   = page.title()
        url     = page.url
        app_def = page.evaluate("typeof AppModel !== 'undefined'")
        log.error(f"  Timeout. Título: '{title}' | URL: {url[:60]} | AppModel: {app_def}")
        raise RuntimeError(
            f"AppSheet no cargó datos en 150s.\n"
            f"  Título: {title}\n  URL: {url}\n  AppModel: {app_def}"
        )

    datos = page.evaluate(JS_EXTRACT, project_id)
    log.info(f"  Extraídos {len(datos)} beneficiarios para proyecto {project_id}")
    return datos


# ─────────────────────────────────────────────────────────────────────────────
# Modo CLOUD: cookies desde env var APPSHEET_COOKIES_B64
# ─────────────────────────────────────────────────────────────────────────────
def _leer_desde_env(project_id: str) -> dict:
    """Lee AppSheet usando cookies almacenadas en env var (GitHub Actions)."""
    cookies_b64 = os.environ.get("APPSHEET_COOKIES_B64", "").strip()
    if not cookies_b64:
        raise RuntimeError("APPSHEET_COOKIES_B64 no configurada.")

    cookies_json = base64.b64decode(cookies_b64).decode("utf-8")
    storage_state = json.loads(cookies_json)

    # Normalizar: Playwright espera {"cookies": [...], "origins": [...]}
    if "cookies" not in storage_state:
        raise RuntimeError("APPSHEET_COOKIES_B64 no tiene formato válido (falta 'cookies').")
    if "origins" not in storage_state:
        storage_state["origins"] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx  = browser.new_context(storage_state=storage_state)
        page = ctx.new_page()
        datos = _extraer_datos_proyecto(page, project_id)
        ctx.close()
        browser.close()

    return {d["nombre"]: d["avance"] for d in datos}


# ─────────────────────────────────────────────────────────────────────────────
# Modo LOCAL: auth guardado o perfil Chrome
# ─────────────────────────────────────────────────────────────────────────────
def _preparar_perfil_trabajo():
    src = Path(CHROME_PROFILE) / "Default"
    dst = Path(CHROME_PROFILE_WORK) / "Default"

    if not src.exists():
        raise RuntimeError(f"Perfil Chrome no encontrado: {src}")

    log.info(f"Preparando perfil de trabajo en: {CHROME_PROFILE_WORK}")
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)

    esenciales = ["Network", "Local Storage", "Session Storage", "IndexedDB",
                  "Preferences", "Secure Preferences", "Cookies"]
    copiados = 0
    for item in esenciales:
        s = src / item
        d = dst / item
        try:
            if s.is_dir():
                shutil.copytree(s, d, ignore_dangling_symlinks=True)
                copiados += 1
            elif s.is_file():
                shutil.copy2(s, d)
                copiados += 1
        except Exception as e:
            log.debug(f"  No se pudo copiar {item}: {e}")

    log.info(f"  Perfil de trabajo listo ({copiados} elementos copiados).")
    return CHROME_PROFILE_WORK


def leer_avance_proyecto(project_id: str) -> dict:
    """
    Retorna dict {nombre_upper: pct_real_int} para el proyecto indicado.

    Intenta en orden:
      1. Env var APPSHEET_COOKIES_B64 (cloud / GitHub Actions)
      2. AUTH_FILE local (appsheet_auth.json)
      3. Perfil Chrome local (Chrome debe estar cerrado)
    """
    # ── 1. Cloud: env var ─────────────────────────────────────────────────────
    if os.environ.get("APPSHEET_COOKIES_B64"):
        log.info("Usando APPSHEET_COOKIES_B64 (modo cloud)...")
        try:
            return _leer_desde_env(project_id)
        except Exception as e:
            log.warning(f"  Cloud auth falló: {e}. Intentando auth local...")

    # ── 2. Local: auth guardado ────────────────────────────────────────────────
    if os.path.exists(AUTH_FILE):
        log.info(f"Usando auth guardado: {AUTH_FILE}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx     = browser.new_context(storage_state=AUTH_FILE)
                page    = ctx.new_page()
                datos   = _extraer_datos_proyecto(page, project_id)
                ctx.storage_state(path=AUTH_FILE)
                ctx.close()
                browser.close()
            return {d["nombre"]: d["avance"] for d in datos}
        except Exception as e:
            log.warning(f"Auth guardado falló: {e}. Intentando perfil Chrome...")

    # ── 3. Local: perfil Chrome ────────────────────────────────────────────────
    if not _chrome_running():
        log.info("Usando copia del perfil Chrome (headless)...")
        try:
            work_dir = _preparar_perfil_trabajo()
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=work_dir,
                    channel="chrome",
                    headless=True,
                    args=["--no-first-run", "--no-default-browser-check"],
                )
                page  = ctx.new_page() if len(ctx.pages) == 0 else ctx.pages[0]
                datos = _extraer_datos_proyecto(page, project_id)
                ctx.storage_state(path=AUTH_FILE)
                log.info(f"  Auth guardado en {AUTH_FILE}")
                ctx.close()
            return {d["nombre"]: d["avance"] for d in datos}
        except Exception as e:
            log.warning(f"Perfil Chrome falló: {e}")
    else:
        log.warning("Chrome está en ejecución. Ciérralo para usar el perfil.")

    raise RuntimeError(
        f"No se pudo leer AppSheet proyecto {project_id}.\n"
        "Soluciones:\n"
        "  1. Configura APPSHEET_COOKIES_B64 como GitHub Secret\n"
        "  2. Ejecuta: python leer_appsheet.py --setup\n"
        "  3. Cierra Chrome antes de ejecutar este script\n"
    )


def leer_avance_p119():
    return leer_avance_proyecto("P119")

def leer_avance_p38():
    return leer_avance_proyecto("P38")

def leer_avance_maiten():
    return leer_avance_proyecto("P126")


def generar_cookies_secret() -> str:
    """
    Genera el valor base64 listo para pegar en GitHub Secret APPSHEET_COOKIES_B64.
    Solo incluye cookies (sin localStorage) para mantenerse dentro del límite 64KB.
    """
    if not os.path.exists(AUTH_FILE):
        raise RuntimeError(
            f"No existe {AUTH_FILE}. Ejecuta primero: python leer_appsheet.py --setup"
        )

    with open(AUTH_FILE, encoding="utf-8") as f:
        data = json.load(f)

    auth_only = {
        "cookies": [
            c for c in data.get("cookies", [])
            if "google" in c.get("domain", "") or "appsheet" in c.get("domain", "")
        ],
        "origins": [],
    }

    json_str = json.dumps(auth_only, separators=(",", ":"))
    b64      = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    size_kb = len(b64) / 1024
    log.info(f"Cookies exportadas: {len(auth_only['cookies'])} | Tamaño: {size_kb:.1f} KB")
    return b64


def setup_auth():
    print("\n" + "=" * 60)
    print("CONFIGURACIÓN DE AUTENTICACIÓN APPSHEET")
    print("=" * 60)

    if _chrome_running():
        print("\nATENCIÓN: Chrome está abierto. Ciérralo e intenta de nuevo.")
        return False

    print("Preparando perfil de Chrome...")

    with sync_playwright() as p:
        try:
            work_dir = _preparar_perfil_trabajo()
            print(f"Perfil de trabajo: {work_dir}")
            print("Abriendo AppSheet. Espera a que carguen los datos...\n")

            ctx = p.chromium.launch_persistent_context(
                user_data_dir=work_dir,
                channel="chrome",
                headless=False,
                args=["--no-first-run", "--no-default-browser-check"],
            )
            page  = ctx.new_page() if len(ctx.pages) == 0 else ctx.pages[0]
            datos = _extraer_datos_proyecto(page, "P119")
            ctx.storage_state(path=AUTH_FILE)
            ctx.close()

            print(f"\nOK: {len(datos)} beneficiarios P119 cargados.")
            print(f"Auth guardado en: {AUTH_FILE}")

            # Generar el Secret automáticamente
            print("\nGenerando valor para GitHub Secret APPSHEET_COOKIES_B64...")
            b64 = generar_cookies_secret()
            secret_file = Path(AUTH_FILE).parent / "appsheet_cookies_b64.txt"
            secret_file.write_text(b64)
            print(f"Secret guardado en: {secret_file}")
            print(f"Tamaño: {len(b64)/1024:.1f} KB")
            print("\nCopia ese valor y agrégalo en GitHub → Settings → Secrets → APPSHEET_COOKIES_B64")
            return True

        except Exception as e:
            print(f"\nERROR: {e}")
            return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s")

    if "--setup" in sys.argv:
        ok = setup_auth()
        sys.exit(0 if ok else 1)

    if "--export-secret" in sys.argv:
        try:
            b64 = generar_cookies_secret()
            print(b64)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    pid = "P119"
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            pid = arg.upper()
            break

    try:
        datos = leer_avance_proyecto(pid)
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

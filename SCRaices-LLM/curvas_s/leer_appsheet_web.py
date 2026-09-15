"""
leer_appsheet_web.py
====================
Lee el % de avance REAL de cada beneficiario directamente desde la página web de AppSheet.
Navega a Obras → Total Avances, filtra por proyecto, entra a cada beneficiario y lee "Avance XX%".

Uso:
  python leer_appsheet_web.py P119          # Lee Ñuke Mapu
  python leer_appsheet_web.py P126          # Lee El Maitén
  python leer_appsheet_web.py P119 --debug  # Muestra prints y no cierra el browser

Retorna dict: { "APELLIDOS NOMBRE": 34.50, ... }
"""

import base64
import json
import logging
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── CONFIG ───────────────────────────────────────────────────────────────────
AUTH_FILE   = r"C:\Users\rodri\.claude\appsheet_auth.json"
CONFIG_FILE = Path(__file__).parent / "config_proyectos.json"

log = logging.getLogger("leer_appsheet_web")

# ─── UTILIDADES ───────────────────────────────────────────────────────────────
def _normalizar(nombre: str) -> str:
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_tildes.upper().split())


def _cargar_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _proyecto_por_id(project_id: str) -> dict:
    cfg = _cargar_config()
    for p in cfg["proyectos"]:
        if p["id"] == project_id:
            return p, cfg
    raise ValueError(f"Proyecto {project_id} no encontrado en config_proyectos.json")


# ─── AUTENTICACIÓN ────────────────────────────────────────────────────────────
def _get_context(playwright, headless: bool = True):
    """Crea contexto Playwright con sesión guardada (cookies de AppSheet)."""
    # Modo cloud: cookies desde env var
    cookies_b64 = os.environ.get("APPSHEET_COOKIES_B64", "").strip()
    if cookies_b64:
        cookies = json.loads(base64.b64decode(cookies_b64).decode())
        ctx = playwright.chromium.launch(headless=headless).new_context()
        ctx.add_cookies(cookies)
        return ctx

    # Modo local: sesión guardada en JSON
    if Path(AUTH_FILE).exists():
        browser = playwright.chromium.launch(headless=headless)
        return browser.new_context(storage_state=AUTH_FILE)

    raise RuntimeError(
        "Sin autenticación AppSheet.\n"
        "  Local: ejecuta  python leer_appsheet.py --setup\n"
        "  Cloud: configura APPSHEET_COOKIES_B64 en los secrets de GitHub."
    )


# ─── LÓGICA PRINCIPAL ─────────────────────────────────────────────────────────
def leer_proyecto(project_id: str, headless: bool = True) -> dict:
    """
    Lee % avance real de todos los beneficiarios de un proyecto desde AppSheet web.
    Retorna: { "APELLIDOS NOMBRE": pct_float, ... }
    """
    proyecto, cfg = _proyecto_por_id(project_id)
    appsheet_url   = cfg["appsheet_url"]
    nombre_panel   = proyecto["appsheet_nombre"]  # nombre exacto en el panel izquierdo

    log.info(f"[{project_id}] Abriendo AppSheet — proyecto '{nombre_panel}'")

    resultados = {}

    with sync_playwright() as p:
        ctx  = _get_context(p, headless=headless)
        page = ctx.new_page()
        page.set_default_timeout(60_000)

        # 1. Navegar a AppSheet
        page.goto(appsheet_url, wait_until="domcontentloaded", timeout=90_000)
        _verificar_login(page)

        # 2. Esperar que la app cargue (buscar texto "Total Avances" o similar)
        log.info(f"[{project_id}] Esperando carga de la app...")
        try:
            page.wait_for_selector("text=Total Avances", timeout=60_000)
        except PWTimeout:
            _screenshot_debug(page, project_id, "carga")
            raise RuntimeError(f"[{project_id}] AppSheet no cargó 'Total Avances' en 60s")

        # 3. Navegar a la vista "Total Avances" si no estamos en ella
        _navegar_a_total_avances(page, project_id)

        # 4. Filtrar por proyecto en el panel izquierdo
        _filtrar_por_proyecto(page, nombre_panel, project_id)

        # 5. Leer % de cada beneficiario
        resultados = _leer_beneficiarios(page, project_id, nombre_panel)

        ctx.close()

    log.info(f"[{project_id}] Total leídos: {len(resultados)} beneficiarios")
    return resultados


def _verificar_login(page):
    """Lanza error si AppSheet redirigió a Google login."""
    url = page.url
    if "accounts.google.com" in url or "signin" in url.lower():
        raise RuntimeError(
            "AppSheet redirigió al login de Google — sesión expirada.\n"
            "Regenera la sesión: python leer_appsheet.py --setup"
        )


def _navegar_a_total_avances(page, project_id: str):
    """Hace click en 'Total Avances' en la navegación si no estamos ahí."""
    try:
        # Esperar que el menú lateral cargue
        page.wait_for_selector("text=Obras", timeout=15_000)
        # Click en "Total Avances" en el menú
        nav = page.locator("text=Total Avances").first
        if nav.is_visible():
            nav.click()
            page.wait_for_timeout(2_000)
            log.info(f"[{project_id}] Navegado a 'Total Avances'")
    except Exception as e:
        log.warning(f"[{project_id}] No se pudo navegar a 'Total Avances': {e}")


def _filtrar_por_proyecto(page, nombre_panel: str, project_id: str):
    """Hace click en el nombre del proyecto en el panel izquierdo para filtrar."""
    log.info(f"[{project_id}] Filtrando por '{nombre_panel}' en panel izquierdo...")

    # Intentar encontrar el proyecto en el panel izquierdo (coincidencia parcial)
    # El panel muestra "Ñuke Mapu 85.91%" — buscamos el texto del nombre
    try:
        # Primero intentar click exacto en panel izquierdo
        panel_items = page.locator(f"text={nombre_panel}").all()
        if not panel_items:
            # Buscar por primera parte del nombre (puede estar truncado)
            primera_parte = nombre_panel.split()[0]
            panel_items = page.locator(f"text={primera_parte}").all()

        if not panel_items:
            log.warning(f"[{project_id}] No encontrado '{nombre_panel}' en panel, continuando sin filtro")
            return

        # Hacer click en el primer elemento que coincida
        panel_items[0].click()
        page.wait_for_timeout(2_500)  # Esperar actualización de la lista
        log.info(f"[{project_id}] Filtro aplicado")
    except Exception as e:
        log.warning(f"[{project_id}] Error al filtrar: {e} — continuando sin filtro")


def _leer_beneficiarios(page, project_id: str, nombre_panel: str) -> dict:
    """
    Lee nombre y % avance de cada tarjeta de beneficiario visible.
    Estrategia principal: leer directamente de las tarjetas (sin click individual).
    Fallback: click en cada tarjeta y leer del panel de detalle.
    """
    resultados = {}

    # Esperar que aparezcan tarjetas de beneficiarios
    try:
        page.wait_for_selector("[class*='approw'], [class*='list-item'], [class*='card']", timeout=15_000)
    except PWTimeout:
        log.warning(f"[{project_id}] No se detectaron tarjetas — intentando lectura de texto bruto")

    # Scroll para cargar todos los beneficiarios (AppSheet puede tener scroll infinito)
    _scroll_completo(page, project_id)

    # Estrategia 1: Extraer datos de las tarjetas directamente (rápido)
    resultados = _extraer_de_tarjetas(page, project_id)
    if resultados:
        log.info(f"[{project_id}] Estrategia 1 (tarjetas): {len(resultados)} leídos")
        return resultados

    # Estrategia 2: Click en cada tarjeta y leer panel de detalle (robusto)
    log.info(f"[{project_id}] Estrategia 1 sin resultados — usando click por tarjeta")
    resultados = _extraer_por_click(page, project_id)
    return resultados


def _scroll_completo(page, project_id: str, max_scrolls: int = 20):
    """Hace scroll hacia abajo hasta que no aparezcan más tarjetas nuevas."""
    prev_count = 0
    for i in range(max_scrolls):
        # Scroll hacia abajo en el área de contenido
        page.keyboard.press("End")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)

        # Contar tarjetas visibles
        count = page.evaluate("""
        () => {
            const sels = ['[class*="approw"]', '[class*="list-item"]', '[class*="card-row"]'];
            for (const s of sels) {
                const els = document.querySelectorAll(s);
                if (els.length > 2) return els.length;
            }
            return 0;
        }
        """)
        if count == prev_count and count > 0:
            break
        prev_count = count

    log.info(f"[{project_id}] Scroll completado — {prev_count} tarjetas visibles")


def _extraer_de_tarjetas(page, project_id: str) -> dict:
    """
    Intenta extraer nombre+% directamente del DOM de las tarjetas.
    Retorna dict o {} si no puede determinar la estructura.
    """
    datos = page.evaluate(r"""
    () => {
        const resultado = [];

        // Intentar múltiples selectores de tarjeta
        const selectorsTarjeta = [
            '[class*="approw-box"]',
            '[class*="list-item-container"]',
            '[class*="card-container"]',
            '[class*="approw"]',
        ];

        let tarjetas = [];
        for (const sel of selectorsTarjeta) {
            const found = Array.from(document.querySelectorAll(sel));
            // Filtrar elementos con al menos algún texto sustancial
            const validos = found.filter(el => el.textContent.trim().length > 10);
            if (validos.length > 2) {
                tarjetas = validos;
                break;
            }
        }

        if (tarjetas.length === 0) return [];

        for (const tarjeta of tarjetas) {
            const texto = tarjeta.innerText || tarjeta.textContent || "";
            const lineas = texto.split('\n').map(l => l.trim()).filter(l => l.length > 0);

            let nombre = null;
            let pct    = null;

            for (const linea of lineas) {
                // Detectar porcentaje: "100%", "85,91%", "34.5%"
                const mPct = linea.match(/^(\d{1,3}[.,]\d{1,2})%$|^(\d{1,3})%$/);
                if (mPct) {
                    const raw = mPct[1] || mPct[2];
                    pct = parseFloat(raw.replace(',', '.'));
                }
                // Detectar nombre: línea con 2+ palabras en mayúsculas
                if (!nombre && /^[A-ZÁÉÍÓÚÑÜA-Z][A-ZÁÉÍÓÚÑÜA-Za-záéíóúñü ]{4,}$/.test(linea)
                    && linea.split(' ').length >= 2) {
                    nombre = linea.toUpperCase().trim();
                }
            }

            if (nombre && pct !== null) {
                resultado.push({ nombre, pct });
            }
        }

        return resultado;
    }
    """)

    if not datos:
        return {}

    resultados = {}
    for item in datos:
        nombre_norm = _normalizar(item["nombre"])
        if nombre_norm and len(nombre_norm) > 4:
            resultados[nombre_norm] = round(item["pct"], 2)

    return resultados


def _extraer_por_click(page, project_id: str) -> dict:
    """
    Hace click en cada tarjeta de beneficiario y lee el % del panel de detalle.
    Más lento pero más robusto — fallback cuando la extracción directa falla.
    """
    resultados = {}

    # Obtener todos los enlaces/botones de tarjeta que se puedan clicar
    tarjetas = page.locator("[class*='approw'], [class*='list-item']").all()
    if not tarjetas:
        log.warning(f"[{project_id}] No se encontraron tarjetas clicables")
        return {}

    log.info(f"[{project_id}] Procesando {len(tarjetas)} tarjetas por click...")

    for i, tarjeta in enumerate(tarjetas):
        try:
            # Leer texto de la tarjeta (nombre)
            texto_tarjeta = (tarjeta.inner_text() or "").strip()
            nombre_raw = _extraer_nombre_de_texto(texto_tarjeta)
            if not nombre_raw:
                continue

            # Click en la tarjeta para abrir detalle
            tarjeta.click()
            page.wait_for_timeout(1_500)

            # Leer "Avance" del panel de detalle
            pct = _leer_avance_detalle(page, project_id, nombre_raw)
            if pct is not None:
                nombre_norm = _normalizar(nombre_raw)
                resultados[nombre_norm] = round(pct, 2)
                log.info(f"[{project_id}] {nombre_norm}: {pct}%")

            # Volver a la lista (Escape o botón atrás)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        except Exception as e:
            log.warning(f"[{project_id}] Error en tarjeta {i}: {e}")
            continue

    return resultados


def _leer_avance_detalle(page, project_id: str, nombre_hint: str) -> float | None:
    """
    En el panel de detalle de un beneficiario, busca el valor 'Avance XX%'.
    Retorna el porcentaje como float, o None si no lo encuentra.
    """
    # Esperar que el detalle cargue
    try:
        page.wait_for_selector("text=Avance", timeout=8_000)
    except PWTimeout:
        log.warning(f"[{project_id}] No encontró 'Avance' en detalle de '{nombre_hint}'")
        return None

    # Extraer todos los pares etiqueta-valor del panel de detalle
    valor = page.evaluate(r"""
    () => {
        // Buscar el elemento que contiene "Avance" y leer su valor asociado
        const allText = document.body.innerText;
        const match = allText.match(/Avance[\s\S]{0,30}?(\d{1,3}[.,]?\d{0,2})%/);
        if (match) return match[1].replace(',', '.');
        return null;
    }
    """)

    if valor is None:
        # Segunda estrategia: buscar el porcentaje grande visible en el detalle
        valor = page.evaluate(r"""
        () => {
            // El % de avance suele estar en un elemento destacado grande
            const candidates = Array.from(document.querySelectorAll('*'));
            for (const el of candidates) {
                if (el.children.length > 0) continue;
                const t = el.textContent.trim();
                // Buscar "100%" o "85,91%" o similar en elemento leaf
                if (/^\d{1,3}[.,]?\d{0,2}%$/.test(t)) {
                    // Verificar que el padre contiene "Avance" o es el primer % grande
                    let parent = el.parentElement;
                    for (let i = 0; i < 4; i++) {
                        if (!parent) break;
                        if (parent.innerText && parent.innerText.includes('Avance')) {
                            return t.replace('%', '').replace(',', '.');
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return null;
        }
        """)

    if valor is None:
        log.warning(f"[{project_id}] No se pudo leer % de '{nombre_hint}'")
        return None

    try:
        return round(float(str(valor).replace(',', '.')), 2)
    except ValueError:
        log.warning(f"[{project_id}] Valor no numérico '{valor}' en '{nombre_hint}'")
        return None


def _extraer_nombre_de_texto(texto: str) -> str | None:
    """Extrae el nombre del beneficiario desde el texto de una tarjeta."""
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    for linea in lineas:
        # El nombre tiene 2+ palabras, todas en mayúsculas, sin %
        if len(linea) > 5 and '%' not in linea and len(linea.split()) >= 2:
            if re.match(r'^[A-ZÁÉÍÓÚÑÜA-Z][A-ZÁÉÍÓÚÑÜA-Za-záéíóúñü ]+$', linea):
                return linea
    return None


def _screenshot_debug(page, project_id: str, etapa: str):
    """Guarda screenshot para debug."""
    try:
        path = Path(r"C:\Users\rodri\.claude\logs") / f"debug_{project_id}_{etapa}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path))
        log.info(f"[{project_id}] Screenshot guardado: {path}")
    except Exception:
        pass


# ─── CLI ──────────────────────────────────────────────────────────────────────
def setup_logging_cli():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )


if __name__ == "__main__":
    setup_logging_cli()

    if len(sys.argv) < 2:
        print("Uso: python leer_appsheet_web.py <PROJECT_ID> [--debug]")
        print("     python leer_appsheet_web.py P119")
        sys.exit(1)

    pid     = sys.argv[1]
    debug   = "--debug" in sys.argv
    headless = not debug

    print(f"\nLeyendo AppSheet web — proyecto {pid}...")
    datos = leer_proyecto(pid, headless=headless)
    print(f"\nResultados ({len(datos)} beneficiarios):")
    for nombre, pct in sorted(datos.items()):
        print(f"  {nombre:<45} {pct:>6.2f}%")

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
def _launch_browser(playwright, headless: bool):
    """Lanza browser: Chromium descargado por Playwright o Chrome del sistema como fallback."""
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception:
        # Fallback: Chrome real instalado en el sistema (Windows)
        return playwright.chromium.launch(channel="chrome", headless=headless)


def _get_context(playwright, headless: bool = True):
    """Crea contexto Playwright con sesión guardada (cookies de AppSheet)."""
    # Modo cloud: cookies desde env var
    cookies_b64 = os.environ.get("APPSHEET_COOKIES_B64", "").strip()
    if cookies_b64:
        cookies = json.loads(base64.b64decode(cookies_b64).decode())
        ctx = _launch_browser(playwright, headless).new_context()
        ctx.add_cookies(cookies)
        return ctx

    # Modo local: sesión guardada en JSON
    if Path(AUTH_FILE).exists():
        browser = _launch_browser(playwright, headless)
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

        # 2. Esperar que la app cargue — probar selectores en secuencia
        log.info(f"[{project_id}] Esperando carga de la app...")
        cargado = False
        for sel in ["text=Inicio", "text=SG Raíces", "[class*='appbody']", "[class*='app-body']"]:
            try:
                page.wait_for_selector(sel, timeout=60_000)
                cargado = True
                log.info(f"[{project_id}] App lista (selector: {sel})")
                break
            except PWTimeout:
                continue
        if not cargado:
            _screenshot_debug(page, project_id, "carga")
            raise RuntimeError(f"[{project_id}] AppSheet no cargó en 60s")

        page.wait_for_timeout(2_000)  # Dejar que el nav se estabilice

        # 3. Navegar a la vista "Total Avances"
        _navegar_a_total_avances(page, project_id)

        # Screenshot post-navegación (siempre, para diagnóstico)
        _screenshot_debug(page, project_id, "post_nav")

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
    """
    Navega a la vista 'Total Avances' desde cualquier pantalla de AppSheet.
    La nav izquierda muestra solo íconos. El texto "Total Avances [En Ejecución]"
    existe en el DOM como span oculto dentro del ícono padre.
    Estrategia: click en el ancestor visible del span que contiene "Total Avances".
    """
    # Estrategia 1: JavaScript — click en el ancestor visible del span "Total Avances"
    clicado = page.evaluate("""
    () => {
        // Buscar span con texto "Total Avances" (puede ser "Total Avances [En Ejecución]")
        const spans = Array.from(document.querySelectorAll('span, div, a, li'));
        const found = spans.find(el =>
            el.textContent.trim().startsWith('Total Avances') &&
            el.children.length === 0
        );
        if (!found) return 'no_span';

        // Subir por el árbol hasta encontrar el primer elemento visible clicable
        let el = found.parentElement;
        for (let i = 0; i < 8; i++) {
            if (!el) break;
            const style = window.getComputedStyle(el);
            const rect  = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 &&
                style.display !== 'none' && style.visibility !== 'hidden' &&
                style.pointerEvents !== 'none') {
                el.click();
                return 'clicked:' + el.tagName + '.' + (el.className || '').slice(0, 40);
            }
            el = el.parentElement;
        }
        return 'no_clickable_ancestor';
    }
    """)
    log.info(f"[{project_id}] nav JS: {clicado}")

    # Esperar que la vista "Total Avances" cargue (hasta 15s)
    for wait_sel in ["text=Total Avances", "text=Todo"]:
        try:
            page.wait_for_selector(wait_sel, timeout=15_000)
            log.info(f"[{project_id}] Vista 'Total Avances' lista ('{wait_sel}')")
            page.wait_for_timeout(1_500)
            return
        except PWTimeout:
            continue

    # Fallback: probar íconos si el JS click no funcionó
    if "no_" in str(clicado):
        _click_nav_icon_hasta_total_avances(page, project_id)


def _click_nav_icon_hasta_total_avances(page, project_id: str):
    """
    Fallback: hace click en cada ícono de la barra lateral hasta que la vista
    actual muestre "Total Avances" en el título/breadcrumb.
    """
    # Los íconos de nav en AppSheet son elementos con clase b-jss* en el sidebar
    nav_icons = page.evaluate("""
    () => {
        // Buscar todos los elementos clicables en la barra lateral izquierda
        const sidebar = document.querySelector('[class*="app-nav"], [class*="appnav"], [class*="sidebar"]');
        if (!sidebar) return [];
        const items = Array.from(sidebar.querySelectorAll('[role="button"], [role="menuitem"], li, a'));
        return items.map((el, i) => ({
            idx: i,
            tag: el.tagName,
            cls: (el.className || '').slice(0, 60),
            text: el.textContent.trim().slice(0, 50),
            visible: el.getBoundingClientRect().width > 0,
        }));
    }
    """)
    log.info(f"[{project_id}] Fallback: {len(nav_icons)} ítems en sidebar")

    for item in nav_icons:
        if not item.get("visible"):
            continue
        try:
            # Click por índice usando el selector CSS
            page.evaluate(f"""
            () => {{
                const sidebar = document.querySelector('[class*="app-nav"], [class*="appnav"], [class*="sidebar"]');
                if (!sidebar) return;
                const items = Array.from(sidebar.querySelectorAll('[role="button"], [role="menuitem"], li, a'));
                const el = items[{item['idx']}];
                if (el) el.click();
            }}
            """)
            page.wait_for_timeout(1_200)

            # ¿Estamos en Total Avances?
            try:
                page.wait_for_selector("text=Total Avances", timeout=2_000)
                log.info(f"[{project_id}] Ícono {item['idx']} ('{item['text']}') → Total Avances")
                return
            except PWTimeout:
                continue
        except Exception:
            continue

    _screenshot_debug(page, project_id, "nav_fallo")
    log.warning(f"[{project_id}] No se encontró 'Total Avances' tras probar todos los íconos")


def _filtrar_por_proyecto(page, nombre_panel: str, project_id: str):
    """
    Hace click en el nombre del proyecto en el panel izquierdo.
    El panel muestra "El Maitén 49,50%" — buscamos las primeras palabras del nombre.
    """
    log.info(f"[{project_id}] Filtrando por '{nombre_panel}' en panel izquierdo...")

    # Buscar por JavaScript usando la mayor parte del nombre para evitar falsas coincidencias
    nombre_js = nombre_panel.replace('"', '').replace("'", "\\'")
    clicado = page.evaluate(f"""
    () => {{
        const nombre = "{nombre_js}";
        // Usar prefijo de 2 palabras para evitar coincidencias falsas (ej. "El" vs "Electrico")
        const palabras = nombre.split(' ');
        const prefijo = palabras.length >= 2
            ? palabras[0] + ' ' + palabras[1].slice(0, 4)  // "El Mait"
            : palabras[0] + ' ';                            // "Aliwen " (con espacio)

        const items = Array.from(document.querySelectorAll('*'));
        for (const el of items) {{
            // Aceptar nodos con pocos hijos también (el texto puede estar en un span hijo)
            if (el.children.length > 2) continue;
            const t = (el.textContent || '').trim();
            // Debe contener el prefijo y tener texto razonable (no un botón gigante)
            if (!t.toLowerCase().startsWith(prefijo.toLowerCase())) continue;
            if (t.length > 80) continue;
            const r = el.getBoundingClientRect();
            // Debe ser visible y estar en el panel izquierdo (x < 320px)
            if (r.width < 20 || r.height < 8 || r.x > 320) continue;
            el.click();
            return 'clicked:' + t.slice(0, 50);
        }}
        return 'not_found';
    }}
    """)
    log.info(f"[{project_id}] Filtro JS: {clicado}")
    page.wait_for_timeout(3_000)  # Esperar que el filtro actualice las tarjetas

    _screenshot_debug(page, project_id, "post_filtro")


def _leer_beneficiarios(page, project_id: str, nombre_panel: str) -> dict:
    """
    Lee nombre y % avance de cada tarjeta de beneficiario visible.
    Estrategia principal: leer directamente de las tarjetas (sin click individual).
    Fallback: click en cada tarjeta y leer del panel de detalle.
    """
    resultados = {}

    # Esperar badges SVG (AppSheet incrusta el % en data-testonly-src como SVG)
    try:
        page.wait_for_function(
            r"() => Array.from(document.querySelectorAll('[data-testonly-src]')).some(el => />(\d{1,3})%</.test(el.getAttribute('data-testonly-src')||''))",
            timeout=15_000
        )
    except PWTimeout:
        log.warning(f"[{project_id}] No se detectaron badges SVG — intentando igualmente")

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
        page.keyboard.press("End")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(900)

        # Contar badges SVG con % (AppSheet usa data-testonly-src con SVG incrustado)
        count = page.evaluate(r"""
        () => {
            return Array.from(document.querySelectorAll('[data-testonly-src]')).filter(el =>
                />(\d{1,3})%</.test(el.getAttribute('data-testonly-src') || '')
            ).length;
        }
        """)
        if count == prev_count and count > 0:
            break
        prev_count = count

    log.info(f"[{project_id}] Scroll completado — ~{prev_count} badges % visibles")


def _extraer_de_tarjetas(page, project_id: str) -> dict:
    """
    Extrae nombre+% de las tarjetas de beneficiarios.

    AppSheet renderiza el badge de avance como una imagen SVG data URI en el
    atributo `data-testonly-src` del elemento `.ImageWithSpinner`.
    El % aparece dentro del SVG como <text>100%</text> — no como texto DOM.

    Estrategia:
    1. Busca todos los [data-testonly-src] que contengan SVG con texto de %
    2. Parsea el porcentaje del SVG con regex
    3. Sube al contenedor de la tarjeta para obtener el nombre
    """
    datos = page.evaluate(r"""
    () => {
        const resultado = [];
        const vistos = new Set();

        // Buscar elementos con data-testonly-src que contengan SVG
        const badgeEls = Array.from(document.querySelectorAll('[data-testonly-src]'));

        for (const badgeEl of badgeEls) {
            const src = badgeEl.getAttribute('data-testonly-src') || '';
            // El porcentaje está como >XX%< en el SVG embebido
            const m = src.match(/>(\d{1,3})%</);
            if (!m) continue;
            const pct = parseFloat(m[1]);
            if (isNaN(pct)) continue;

            // Subir hasta el contenedor de la tarjeta para extraer el nombre
            let container = badgeEl.parentElement;
            let nombre = null;

            for (let i = 0; i < 10; i++) {
                if (!container) break;
                const rect = container.getBoundingClientRect();

                if (rect.width > 100 && rect.height > 40) {
                    const inner = (container.innerText || container.textContent || '');
                    const lineas = inner.split(/\n|\r/).map(l => l.trim()).filter(l => l.length > 0);

                    for (const linea of lineas) {
                        if (linea.replace(/\s+/g, '').includes('%')) continue;
                        if (linea.length < 6) continue;
                        const palabras = linea.trim().split(/\s+/);
                        if (palabras.length < 2) continue;
                        if (!palabras.some(p => p.length >= 2)) continue;
                        if (palabras.every(p => p.length <= 1)) continue;
                        if (!/[A-Za-záéíóúñüÁÉÍÓÚÑÜ]/.test(linea)) continue;
                        if (/^\d/.test(linea)) continue;

                        nombre = linea.toUpperCase().trim();
                        break;
                    }

                    if (nombre) break;
                }
                container = container.parentElement;
            }

            if (nombre && !vistos.has(nombre)) {
                vistos.add(nombre);
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

    # Obtener posiciones de los badges SVG (data-testonly-src con % en SVG)
    posiciones = page.evaluate(r"""
    () => {
        const badges = Array.from(document.querySelectorAll('[data-testonly-src]')).filter(el =>
            />(\d{1,3})%</.test(el.getAttribute('data-testonly-src') || '')
        );
        return badges.map(el => {
            const r = el.getBoundingClientRect();
            return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
        }).filter(p => p.x > 0 && p.y > 0);
    }
    """)
    if not posiciones:
        log.warning(f"[{project_id}] No se encontraron tarjetas clicables por badges")
        return {}

    tarjetas = posiciones  # Usaremos coordenadas para click

    log.info(f"[{project_id}] Procesando {len(tarjetas)} tarjetas por click en badge...")

    for i, pos in enumerate(tarjetas):
        try:
            # Click en el badge de % para abrir detalle
            page.mouse.click(pos["x"], pos["y"])
            page.wait_for_timeout(1_800)

            # Leer "Avance" del panel de detalle
            pct = _leer_avance_detalle(page, project_id, f"tarjeta_{i}")
            if pct is not None:
                # Intentar extraer el nombre del panel de detalle
                nombre_raw = page.evaluate(r"""
                () => {
                    const lines = (document.body.innerText || '').split('\n').map(l => l.trim()).filter(l => l);
                    return lines.find(l => !l.includes('%') && l.split(' ').length >= 2 && l.length > 8 && /[A-Za-záéíóúñüÁÉÍÓÚÑÜ]/.test(l)) || null;
                }
                """)
                if nombre_raw:
                    nombre_norm = _normalizar(nombre_raw)
                    resultados[nombre_norm] = round(pct, 2)
                    log.info(f"[{project_id}] {nombre_norm}: {pct}%")

            # Volver a la lista
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)

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

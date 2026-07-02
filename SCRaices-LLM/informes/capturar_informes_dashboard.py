"""
capturar_informes_dashboard.py
==============================
Abre el dashboard SG Raíces con Playwright y captura TODOS los informes
por proyecto:

  PDF  — Informe_Ejecutivo_{pid}_{nombre}_{fecha}.pdf          → curvas_s
  PDF  — Informe_Residente_{pid}_{nombre}_{fecha}.pdf          → residente
  PDF  — Informe_Capataz_{pid}_{nombre}_{slug}_{fecha}.pdf     → por_capataz (uno por capataz)
  HTML — Informe_EjecutivoHTML_{fecha}.html                    → html_navegable (global)
  HTML — Informe_Adquisiciones_{fecha}.html                    → adquisiciones_html (global)

Modo local : guarda en OUTPUT_DIR_LOCAL
Modo cloud : usa tempfile.mkdtemp() y la ruta la retorna main()

Uso standalone:
    python capturar_informes_dashboard.py
    python capturar_informes_dashboard.py --output-dir /ruta/a/dir
"""

import os
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from playwright.sync_api import sync_playwright
import requests

_BASE_URL        = "https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html"
DASHBOARD_URL    = f"{_BASE_URL}?v={int(time.time())}"
OUTPUT_DIR_LOCAL = Path(r"C:\Users\rodri\.claude\informes_pdf")
FIREBASE         = "https://scraices-dashboard-default-rtdb.firebaseio.com"

PROYECTOS = [
    ("P126", "El_Maiten"),
    ("P119", "Nuke_Mapu"),
    ("P127", "Nuevo_Cunco"),
    ("P39",  "El_Coihue"),
    ("P14",  "Com_Madihue"),
    ("P116", "Sonia_Quilaleo"),
    ("P12",  "Juan_Huilcan_Tolten"),
    ("P38",  "Aliwen"),
    ("P31",  "Trovolhue"),
    ("P131", "Raices_Melipeuco"),
]

# Informes PDF estándar por proyecto (sin capataz — se maneja aparte)
INFORMES_PDF = [
    ("Ejecutivo", "Reporte ejecutivo (Curvas S)"),
    ("Residente", "Reporte residente"),
]

# Informes HTML globales (contienen todos los proyectos — se capturan una sola vez)
INFORMES_HTML = [
    ("EjecutivoHTML", "Reporte Ejecutivo HTML"),
    ("Adquisiciones", "Reporte adquisiciones HTML"),
]


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _slug(nombre: str) -> str:
    """Convierte nombre a slug ASCII-safe para usar en nombres de archivo."""
    nfd = unicodedata.normalize("NFD", nombre)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w]", "_", ascii_str).strip("_")


def _grupos_capataces(pid: str) -> list:
    """Retorna lista ordenada de nombres de capataz para el proyecto dado (desde Firebase)."""
    try:
        r = requests.get(f"{FIREBASE}/grupos/{pid}.json", timeout=20)
        grupos = r.json()
        if not grupos:
            return []
        if isinstance(grupos, list):
            items = [g for g in grupos if g]
        elif isinstance(grupos, dict):
            items = list(grupos.values())
        else:
            return []
        caps = sorted(set(g.get("capataz", "") for g in items if g.get("capataz")))
        return caps
    except Exception as e:
        print(f"    [grupos] Error leyendo capataces de {pid}: {e}")
        return []


# ─── Helpers de Playwright ────────────────────────────────────────────────────

def wait_dashboard_ready(page, timeout=300):
    print("  Esperando carga del dashboard (hasta 5 min)...")
    page.wait_for_selector("select", timeout=timeout * 1000)
    try:
        page.wait_for_function(
            "() => { const t=document.body.innerText; "
            "return !t.includes('Cargando') && !t.includes('Descargando') && t.length>300; }",
            timeout=timeout * 1000,
        )
    except Exception:
        pass
    time.sleep(4)
    print("  Dashboard listo.")


def activar_tab_estado_general(page):
    page.evaluate("""
        const tab=[...document.querySelectorAll('button')]
            .find(b=>b.textContent.trim()==='Estado General');
        if(tab){
            const fk=Object.keys(tab).find(k=>k.startsWith('__reactFiber'));
            tab[fk]?.memoizedProps?.onClick?.(
                {type:'click',preventDefault:()=>{},stopPropagation:()=>{}});
        }
    """)
    time.sleep(1.5)


def instalar_interceptor(page):
    """Intercepta window.open() capturando tanto document.write como blob: URLs."""
    page.evaluate("""
        window._capturedHTML = null;
        window.open = function(url, name, features) {
            if (url && typeof url === 'string' && url.startsWith('blob:')) {
                fetch(url).then(r => r.text()).then(t => { window._capturedHTML = t; });
                return { focus(){}, close(){} };
            }
            const fw = {
                document: {
                    _h: '',
                    open()  {},
                    write(h)   { this._h += h; },
                    writeln(h) { this._h += h + '\\n'; },
                    close()    { window._capturedHTML = this._h; }
                },
                focus(){}, close(){}
            };
            return fw;
        };
    """)


def instalar_interceptor_multi(page):
    """Intercepta window.open() acumulando múltiples HTMLs en un array."""
    page.evaluate("""
        window._capturedHTMLs = [];
        window.open = function(url, name, features) {
            if (url && typeof url === 'string' && url.startsWith('blob:')) {
                return { focus(){}, close(){} };
            }
            const idx = window._capturedHTMLs.length;
            window._capturedHTMLs.push({done: false, html: ''});
            return {
                document: {
                    write(h)   { window._capturedHTMLs[idx].html += h; },
                    writeln(h) { window._capturedHTMLs[idx].html += h + '\\n'; },
                    close()    { window._capturedHTMLs[idx].done = true; }
                },
                focus(){}, close(){}
            };
        };
    """)


def disparar_boton(page, texto_boton):
    """Resetea el capturador, dispara el botón y espera el HTML."""
    page.evaluate("window._capturedHTML = null;")
    page.evaluate(f"""
        const btn=[...document.querySelectorAll('button')]
            .find(b=>b.textContent.trim().includes({repr(texto_boton)}));
        if(btn){{
            const rk=Object.keys(btn).find(k=>k.startsWith('__reactFiber'));
            btn[rk]?.memoizedProps?.onClick?.(
                {{type:'click',preventDefault:()=>{{}},stopPropagation:()=>{{}}}});
        }}
    """)
    try:
        page.wait_for_function("() => !!window._capturedHTML", timeout=30000)
        return page.evaluate("window._capturedHTML")
    except Exception as e:
        print(f"    Timeout esperando HTML ({e})")
        return None


def disparar_boton_multi(page, texto_boton, expected: int):
    """Dispara botón que genera múltiples ventanas; retorna lista de HTMLs capturados."""
    page.evaluate(f"""
        const btn=[...document.querySelectorAll('button')]
            .find(b=>b.textContent.trim().includes({repr(texto_boton)}));
        if(btn){{
            const rk=Object.keys(btn).find(k=>k.startsWith('__reactFiber'));
            btn[rk]?.memoizedProps?.onClick?.(
                {{type:'click',preventDefault:()=>{{}},stopPropagation:()=>{{}}}});
        }}
    """)
    try:
        page.wait_for_function(
            f"() => window._capturedHTMLs.filter(x => x.done).length >= {expected}",
            timeout=90000,
        )
    except Exception as e:
        print(f"    Timeout esperando {expected} capturas: {e}")
    captured = page.evaluate("window._capturedHTMLs.filter(x => x.done).map(x => x.html)")
    return captured


def html_a_pdf(context, html, pdf_path):
    """Renderiza el HTML en una pestaña nueva y exporta a PDF."""
    p = context.new_page()
    p.set_content(html, wait_until="domcontentloaded")
    try:
        p.wait_for_function(
            "() => { const imgs=[...document.querySelectorAll('img')]; "
            "return imgs.length===0 || imgs.every(i=>i.complete && i.naturalWidth>0); }",
            timeout=25000,
        )
    except Exception:
        print("    (Timeout imágenes, continuando)")
    p.pdf(
        path=str(pdf_path),
        format="A4",
        print_background=True,
        margin={"top":"10mm","bottom":"10mm","left":"10mm","right":"10mm"},
    )
    p.close()


def _extraer_nombre_capataz(html: str) -> str:
    """Extrae el nombre del capataz desde el <title> del HTML generado."""
    m = re.search(r"<title>Reporte Capataz (.+?) —", html)
    if not m:
        m = re.search(r"<title>Reporte Capataz (.+?) -", html)
    if not m:
        m = re.search(r"<title>Reporte Capataz (.+?)</title>", html)
    return m.group(1).strip() if m else ""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(output_dir: Path = None) -> Path:
    """
    Captura todos los informes del dashboard.
    Retorna el directorio donde se guardaron los archivos.
    """
    if output_dir is None:
        if os.environ.get("GOOGLE_REFRESH_TOKEN"):
            output_dir = Path(tempfile.mkdtemp(prefix="informes_"))
        else:
            output_dir = OUTPUT_DIR_LOCAL
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fecha     = time.strftime("%Y%m%d")
    total_ok  = 0
    total_err = 0

    # Pre-cargar capataces por proyecto desde Firebase
    capataces_por_proy = {pid: _grupos_capataces(pid) for pid, _ in PROYECTOS}

    with sync_playwright() as pw:
        # --disable-dev-shm-usage: evita "Failed to fetch" al descargar tablas
        # grandes (~55MB) en CI, donde /dev/shm es de solo 64MB.
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page    = context.new_page()

        print("Abriendo dashboard...")
        page.goto(DASHBOARD_URL, timeout=60000)
        wait_dashboard_ready(page)

        # ── HTMLs globales (una sola captura, contienen todos los proyectos) ────
        primer_pid, _ = PROYECTOS[0]
        print(f"\n[GLOBAL] Capturando HTMLs globales desde {primer_pid}...")
        try:
            page.wait_for_selector("select", timeout=15000)
            page.evaluate(f"""
                const sel=document.querySelector('select');
                if(sel){{sel.value='{primer_pid}';
                sel.dispatchEvent(new Event('change',{{bubbles:true}}));}}
            """)
            time.sleep(3)
            activar_tab_estado_general(page)

            for sufijo, texto in INFORMES_HTML:
                html_path = output_dir / f"Informe_{sufijo}_{fecha}.html"
                print(f"  [{sufijo}] Generando '{texto}'...")
                instalar_interceptor(page)
                html = disparar_boton(page, texto)
                if not html:
                    print(f"  [{sufijo}] ERROR: no se capturó HTML")
                    total_err += 1
                    continue
                print(f"    HTML: {len(html):,} chars")
                html_path.write_text(html, encoding="utf-8")
                print(f"    HTML: {html_path.name} ({html_path.stat().st_size:,} bytes)")
                total_ok += 1
        except Exception as e:
            print(f"  ERROR capturando HTMLs globales: {e}")
            total_err += 1

        # ── PDFs por proyecto ──────────────────────────────────────────────────
        for pid, nombre in PROYECTOS:
            print(f"\n[{pid}] {nombre}")
            try:
                page.wait_for_selector("select", timeout=15000)
                page.evaluate(f"""
                    const sel=document.querySelector('select');
                    if(sel){{sel.value='{pid}';
                    sel.dispatchEvent(new Event('change',{{bubbles:true}}));}}
                """)
                time.sleep(3)
                activar_tab_estado_general(page)

                # PDFs estándar (Ejecutivo y Residente)
                for sufijo, texto in INFORMES_PDF:
                    pdf_path = output_dir / f"Informe_{sufijo}_{pid}_{nombre}_{fecha}.pdf"
                    print(f"  [{sufijo}] Generando '{texto}'...")
                    instalar_interceptor(page)
                    html = disparar_boton(page, texto)
                    if not html:
                        print(f"  [{sufijo}] ERROR: no se capturó HTML")
                        total_err += 1
                        continue
                    print(f"    HTML: {len(html):,} chars")
                    html_a_pdf(context, html, pdf_path)
                    print(f"    PDF: {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
                    total_ok += 1

                # PDFs de capataz — uno por capataz individual
                caps = capataces_por_proy.get(pid, [])
                if caps:
                    print(f"  [Capataz] Generando {len(caps)} reporte(s): {caps}")
                    instalar_interceptor_multi(page)
                    htmls = disparar_boton_multi(page, "Reporte Capataz", expected=len(caps))
                    if not htmls:
                        print(f"  [Capataz] ERROR: no se capturó ningún HTML")
                        total_err += 1
                    else:
                        for html_cap in htmls:
                            nombre_cap = _extraer_nombre_capataz(html_cap)
                            if not nombre_cap:
                                print("  [Capataz] ADVERTENCIA: no se pudo extraer nombre del capataz")
                                total_err += 1
                                continue
                            slug = _slug(nombre_cap)
                            pdf_path = output_dir / f"Informe_Capataz_{pid}_{nombre}_{slug}_{fecha}.pdf"
                            html_a_pdf(context, html_cap, pdf_path)
                            print(f"    PDF: {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
                            total_ok += 1
                else:
                    print(f"  [Capataz] Sin capataces registrados en Firebase/grupos — omitiendo")

            except Exception as e:
                print(f"  ERROR general [{pid}]: {e}")
                total_err += 1

        browser.close()

    print(f"\n{'='*50}")
    print(f"Completado: {total_ok} archivos generados, {total_err} errores")
    print(f"Directorio: {output_dir}")
    return output_dir


if __name__ == "__main__":
    out_arg = None
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            out_arg = Path(sys.argv[idx + 1])
    main(out_arg)

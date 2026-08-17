"""
enviar_informes_lunes.py  (v2 — Playwright)
===========================================
Genera los informes HTML usando Playwright (mismo motor que el botón
"Informes" del dashboard) y los envía por Gmail SMTP.

Estrategia de captura:
  Se parchea window.Blob en el navegador para interceptar el HTML justo
  antes de que el dashboard lo convierta en archivo de descarga.  Así
  los informes enviados son exactamente los que generaría el usuario.

Funciones JS invocadas:
  html_navegable     → generarInformeMultiObras()
  adquisiciones_html → generarInformeAdquisicionesHTML()
  recepciones_html   → generarInformeRecepciones()
  estados_pago_html  → generarEstadosPagoHTML()
  residente          → generarInformeResidenteHTML()  (requiere proyectoSel)
  por_capataz        → generarReporteCapataz(nombre)  (requiere proyectoSel)

Variables de entorno:
  FIREBASE_URL         URL base Firebase (sin .json al final)
  GMAIL_APP_PASSWORD   App password de Gmail (16 chars sin espacios)
  DRY_RUN              'false' para enviar correos reales (default en cron)
  TEST_EMAIL           Si definido, envía SOLO a este correo (modo prueba)
"""

import asyncio
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timezone, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from playwright.async_api import async_playwright

# ── Configuración ──────────────────────────────────────────────────────────
FIREBASE_URL  = (os.environ.get('FIREBASE_URL') or
                 'https://scraices-dashboard-default-rtdb.firebaseio.com').rstrip('/')
GMAIL_USER    = 'rodrigolagoslira@gmail.com'
GMAIL_PASS    = os.environ.get('GMAIL_APP_PASSWORD', '')
DRY_RUN       = os.environ.get('DRY_RUN', 'false').lower() != 'false'
TEST_EMAIL    = os.environ.get('TEST_EMAIL', '').strip()

DASHBOARD_URL = (
    'https://pitufostech.github.io/PruebasWeb/'
    'SCRaices-LLM/dashboard/index_live_v3.html'
)
LIVE_TIMEOUT = 600  # segundos esperando log [LIVE] Datos

ACTIVE_PROJ_IDS = {
    'P119', 'P38', 'P126', 'P39', 'P127',
    'P12',  'P14', 'P116', 'P31', 'P131', 'P28',
}

# Propiedad en window._raicesInformeFns para cada tipo de informe multi-obra
MULTI_OBRA_FN = {
    'html_navegable':     'ejecutivo',
    'adquisiciones_html': 'adquisiciones',
    'recepciones_html':   'recepciones',
    'estados_pago_html':  'estadosPago',
}

INFORME_LABELS = {
    'html_navegable':    'Ejecutivo',
    'adquisiciones_html': 'Adquisiciones',
    'recepciones_html':   'Recepciones',
    'estados_pago_html':  'EstadosPago',
    'residente':          'Residente',
    'por_capataz':        'Capataz',
}

# ── Inyección JS: parchea Blob para capturar HTML ──────────────────────────
_BLOB_PATCH = """
    window.__captured = null;
    const _OB = window.Blob;
    window.Blob = function(parts, opts) {
        if (opts && typeof opts.type === 'string' &&
            opts.type.includes('text/html') && parts && parts[0]) {
            window.__captured = parts[0];
        }
        return new _OB(parts, opts);
    };
    window.open  = () => null;
    window.alert = (m) => console.warn('[ALERT]', m);
"""

# ── Firebase ───────────────────────────────────────────────────────────────
def fb_get(path: str):
    r = requests.get(f'{FIREBASE_URL}/{path}.json', timeout=20)
    r.raise_for_status()
    return r.json() or {}

# ── Playwright ─────────────────────────────────────────────────────────────
async def _capturar(page, js_call: str) -> str | None:
    """Arm interceptor, run async JS call, return captured HTML or None."""
    await page.evaluate(f'() => {{ {_BLOB_PATCH} }}')
    try:
        await page.evaluate(f'async () => {{ {js_call}; }}')
    except Exception as e:
        print(f'    JS error: {e}')
    return await page.evaluate('() => window.__captured')


async def _set_proyecto(page, proj_id: str):
    """Change the dashboard's selected project via React state setter."""
    await page.evaluate(f"""() => {{
        if (typeof window._raicesSetProy === 'function') {{
            window._raicesSetProy({json.dumps(proj_id)});
        }} else {{
            window.proyectoSel = {json.dumps(proj_id)};
        }}
    }}""")
    await asyncio.sleep(3)  # Wait for React re-render and useEffect


async def generar_informes_playwright(
    tipos_multi:          set,
    residentes_proyectos: dict,   # {nombre_residente: primer_proj_id}
    capataces_proyectos:  dict,   # {nombre_capataz: [proj_id, ...]}
) -> dict:
    """
    Abre el dashboard, espera carga en vivo, genera todos los informes.
    Retorna:
      tipo_str → html                    (multi-obra)
      ('residente', nombre) → html
      ('capataz', nombre, proj_id) → html
    """
    resultados: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        page = await (await browser.new_context()).new_page()

        live_done = [False]
        page.on('console',   lambda m: live_done.__setitem__(0, True)
                             if '[LIVE] Datos' in m.text else None)
        page.on('pageerror', lambda e: print(f'  [PAGEERROR] {e}'))

        print('  Abriendo dashboard...')
        await page.goto(DASHBOARD_URL, wait_until='domcontentloaded',
                        timeout=60_000)

        # Esperar carga en vivo
        t0 = time.time()
        deadline = t0 + LIVE_TIMEOUT
        while time.time() < deadline and not live_done[0]:
            await asyncio.sleep(3)
            elapsed = int(time.time() - t0)
            if elapsed % 30 < 4:
                print(f'  ...esperando [LIVE]: {elapsed}s...')

        if not live_done[0]:
            print('  ERROR: timeout esperando [LIVE] Datos')
            await browser.close()
            return {}

        print(f'  Dashboard cargado OK en {int(time.time()-t0)}s')
        await asyncio.sleep(8)  # Wait for React render + useEffect to populate _raicesInformeFns

        # 1. Multi-obra
        for tipo in tipos_multi:
            fn = MULTI_OBRA_FN.get(tipo)
            if not fn:
                continue
            label = INFORME_LABELS.get(tipo, tipo)
            print(f'  [{label}] ', end='', flush=True)
            html = await _capturar(page, f'await window._raicesInformeFns.{fn}()')
            if html:
                resultados[tipo] = html
                print(f'OK ({len(html)//1024} KB)')
            else:
                print('vacío')

        # 2. Residente (por proyecto de referencia)
        for nombre, proj_id in residentes_proyectos.items():
            print(f'  [Residente: {nombre} / {proj_id}] ', end='', flush=True)
            await _set_proyecto(page, proj_id)
            html = await _capturar(page, 'await window._raicesInformeFns.residente()')
            if html:
                resultados[('residente', nombre)] = html
                print(f'OK ({len(html)//1024} KB)')
            else:
                print('vacío (nombre no coincide con grupos?)')

        # 3. Capataz (por nombre y proyecto)
        for nombre, proj_ids in capataces_proyectos.items():
            for proj_id in proj_ids:
                print(f'  [Capataz: {nombre} / {proj_id}] ',
                      end='', flush=True)
                await _set_proyecto(page, proj_id)
                html = await _capturar(
                    page,
                    f'await window._raicesInformeFns.generarReporteCapatazPorNombre({json.dumps(nombre)})'
                )
                if html:
                    resultados[('capataz', nombre, proj_id)] = html
                    print(f'OK ({len(html)//1024} KB)')
                else:
                    print('vacío')

        await browser.close()

    return resultados


# ── Mappings Firebase → destinatarios ─────────────────────────────────────
def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode()


def build_mappings(personal: dict, grupos: dict) -> tuple:
    """
    Construye:
      residentes_proyectos: {nombre_residente: primer_proj_id}
      capataces_proyectos:  {nombre_capataz: [proj_ids]}
      recipients:           [{correo, nombre, tipos, residente_nombre?, capataz_nombre?}]
    """
    # Índice grupos Firebase
    res_a_proy:  dict[str, list[str]] = {}
    cap_a_proy:  dict[str, list[str]] = {}

    for pid, grp_list in grupos.items():
        if pid not in ACTIVE_PROJ_IDS or not isinstance(grp_list, list):
            continue
        for g in grp_list:
            for campo, idx in [('residente', res_a_proy),
                                ('capataz',   cap_a_proy)]:
                nombre = (g.get(campo) or '').strip()
                if nombre:
                    idx.setdefault(nombre, [])
                    if pid not in idx[nombre]:
                        idx[nombre].append(pid)

    recipients = []
    for _, persona in personal.items():
        correo = (persona.get('correo') or '').strip()
        tipos  = persona.get('informes') or []
        nombre = (persona.get('nombre') or '').strip()
        if not correo or not tipos:
            continue
        entry: dict = {'correo': correo, 'nombre': nombre, 'tipos': tipos}

        if 'residente' in tipos:
            match = next(
                (r for r in res_a_proy
                 if _norm(nombre) in _norm(r) or _norm(r) in _norm(nombre)),
                None
            )
            entry['residente_nombre'] = match

        if 'por_capataz' in tipos:
            match = next(
                (c for c in cap_a_proy
                 if _norm(nombre) in _norm(c) or _norm(c) in _norm(nombre)),
                None
            )
            entry['capataz_nombre'] = match

        recipients.append(entry)

    # Filtrar solo los residentes/capataces realmente necesarios
    needed_res: dict[str, str]        = {}
    needed_cap: dict[str, list[str]]  = {}

    for r in recipients:
        rn = r.get('residente_nombre')
        if rn and rn in res_a_proy:
            needed_res[rn] = res_a_proy[rn][0]
        cn = r.get('capataz_nombre')
        if cn and cn in cap_a_proy:
            needed_cap[cn] = cap_a_proy[cn]

    return needed_res, needed_cap, recipients


def build_mappings_test(grupos: dict) -> tuple:
    """Modo TEST: elige un residente y un capataz de muestra."""
    res_a_proy: dict[str, str]        = {}
    cap_a_proy: dict[str, list[str]]  = {}

    for pid, grp_list in grupos.items():
        if pid not in ACTIVE_PROJ_IDS or not isinstance(grp_list, list):
            continue
        for g in grp_list:
            res = (g.get('residente') or '').strip()
            cap = (g.get('capataz') or '').strip()
            if res and res not in res_a_proy:
                res_a_proy[res] = pid
            if cap and cap not in cap_a_proy:
                cap_a_proy.setdefault(cap, [])
                if pid not in cap_a_proy[cap]:
                    cap_a_proy[cap].append(pid)

    # Muestra: primer residente y primer capataz encontrados
    sample_res  = dict(list(res_a_proy.items())[:1])
    sample_cap  = dict(list(cap_a_proy.items())[:1])
    res_nombre  = list(sample_res.keys())[0]  if sample_res  else None
    cap_nombre  = list(sample_cap.keys())[0]  if sample_cap  else None

    todos_tipos = list(MULTI_OBRA_FN.keys()) + ['residente', 'por_capataz']
    recipient = {
        'correo':           TEST_EMAIL,
        'nombre':           'Prueba',
        'tipos':            todos_tipos,
        'residente_nombre': res_nombre,
        'capataz_nombre':   cap_nombre,
    }
    return sample_res, sample_cap, [recipient]


# ── Gmail SMTP ─────────────────────────────────────────────────────────────
def enviar_correo(destinatario: str, nombre: str,
                  adjuntos: dict[str, str], fecha: str) -> bool:
    msg = MIMEMultipart('mixed')
    msg['From']    = GMAIL_USER
    msg['To']      = destinatario
    msg['Subject'] = f'Informes Semanales · Constructora Raíces · {fecha}'

    cuerpo = MIMEText(
        f'Estimado/a {nombre},\n\n'
        f'Adjunto los informes semanales del {fecha}.\n'
        f'Abra cada archivo en su navegador web para visualizarlo.\n\n'
        'Constructora Raíces · Informe automático · No responder.',
        'plain', 'utf-8'
    )
    msg.attach(cuerpo)

    for label, contenido in adjuntos.items():
        filename = f'informe_{label}_{fecha.replace("/","_")}.html'
        part = MIMEBase('text', 'html')
        part.set_payload(contenido.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=filename)
        part.add_header('Content-Type', 'text/html; charset=utf-8')
        msg.attach(part)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
            s.ehlo(); s.starttls()
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, destinatario, msg.as_string())
        return True
    except Exception as e:
        print(f'  ERROR SMTP: {e}')
        return False


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    now_cl = datetime.now(timezone(timedelta(hours=-3)))
    fecha  = now_cl.strftime('%d/%m/%Y')
    test_mode = bool(TEST_EMAIL)

    print(f'\n{"="*60}')
    print(f'  Informes Semanales Raíces · {fecha}')
    print(f'  DRY_RUN={DRY_RUN}  TEST_EMAIL={TEST_EMAIL or "(ninguno)"}')
    print(f'{"="*60}\n')

    # 1. Cargar Firebase
    print('[1/4] Cargando Firebase...')
    personal = fb_get('personal_global')
    grupos   = fb_get('grupos')
    print(f'  personal_global: {len(personal)} entradas')
    print(f'  grupos: {len(grupos)} proyectos')

    # 2. Mappings
    print('\n[2/4] Construyendo destinatarios...')
    if test_mode:
        needed_res, needed_cap, recipients = build_mappings_test(grupos)
        print(f'  ⚠ MODO PRUEBA → {TEST_EMAIL}')
    else:
        needed_res, needed_cap, recipients = build_mappings(personal, grupos)

    if not recipients:
        print('  ! Sin destinatarios.')
        sys.exit(0)

    for r in recipients:
        rn = r.get('residente_nombre', '—')
        cn = r.get('capataz_nombre',   '—')
        print(f'  → {r["nombre"]} <{r["correo"]}>'
              f'  tipos={r["tipos"]}'
              f'  res={rn}  cap={cn}')

    # Tipos multi-obra requeridos
    tipos_multi = {t for r in recipients for t in r['tipos']
                   if t in MULTI_OBRA_FN}

    print(f'\n  Multi-obra: {sorted(tipos_multi)}')
    print(f'  Residentes: {list(needed_res.keys())}')
    print(f'  Capataces:  {list(needed_cap.keys())}')

    # 3. Generar con Playwright
    print('\n[3/4] Generando informes (Playwright)...')
    resultados = asyncio.run(generar_informes_playwright(
        tipos_multi, needed_res, needed_cap
    ))
    if not resultados:
        print('  ERROR: no se generó ningún informe')
        sys.exit(1)
    print(f'  Total generados: {len(resultados)}')

    # 4. Construir adjuntos y enviar
    print(f'\n[4/4] {"[DRY RUN]" if DRY_RUN else "Enviando correos"}...')
    ok = err = 0

    for r in recipients:
        adjuntos: dict[str, str] = {}

        for tipo in r['tipos']:
            # Multi-obra
            if tipo in MULTI_OBRA_FN:
                if tipo in resultados:
                    adjuntos[INFORME_LABELS[tipo]] = resultados[tipo]

            # Residente
            elif tipo == 'residente':
                rn  = r.get('residente_nombre')
                key = ('residente', rn) if rn else None
                if key and key in resultados:
                    adjuntos['Residente'] = resultados[key]
                elif not rn:
                    print(f'  ! {r["nombre"]}: sin residente_nombre, '
                          'agrega el campo a personal_global en Firebase')

            # Capataz (uno por proyecto)
            elif tipo == 'por_capataz':
                cn = r.get('capataz_nombre')
                if cn:
                    for pid in needed_cap.get(cn, []):
                        key = ('capataz', cn, pid)
                        if key in resultados:
                            adjuntos[f'Capataz_{pid}'] = resultados[key]
                else:
                    print(f'  ! {r["nombre"]}: sin capataz_nombre, '
                          'agrega el campo a personal_global en Firebase')

        if not adjuntos:
            print(f'  ! {r["nombre"]} <{r["correo"]}>: sin adjuntos, omitiendo')
            continue

        if DRY_RUN:
            print(f'  [DRY] {r["nombre"]} <{r["correo"]}>'
                  f' → {", ".join(adjuntos)}')
            ok += 1
        else:
            print(f'  Enviando a {r["nombre"]} <{r["correo"]}>'
                  f' ({len(adjuntos)} adjuntos)...', end=' ', flush=True)
            if enviar_correo(r['correo'], r['nombre'], adjuntos, fecha):
                print('✓')
                ok += 1
            else:
                err += 1

    print(f'\n{"="*60}')
    print(f'  Resultado: {ok} OK · {err} errores')
    print(f'{"="*60}\n')

    if err:
        sys.exit(1)


if __name__ == '__main__':
    main()

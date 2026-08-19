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
RESUMEN_EMAIL = 'rlagos@scraices.cl'  # resumen de estado siempre a este correo

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


async def _seleccionar_proyecto_ui(page, proj_id: str, current: list) -> None:
    """
    Cambia el proyecto activo llamando window._raicesSetProy(proj_id).
    Expuesto desde el App component via useEffect — dispara re-render React
    y recarga datos/grupos para ese proyecto en la closure de los informes.
    current = [proj_id_actual]  (lista mutable para evitar cambios innecesarios)
    """
    if current[0] == proj_id:
        return
    print(f'    → seleccionando {proj_id}...', end=' ', flush=True)
    await page.evaluate(f'() => window._raicesSetProy && window._raicesSetProy({json.dumps(proj_id)})')
    # Esperar re-render React + fetch datos/grupos + useEffect line-1855 re-run
    await asyncio.sleep(8)
    current[0] = proj_id
    print('OK')


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
        current_proj = [None]  # rastrear proyecto seleccionado actualmente en UI

        def _on_console(m):
            if '[LIVE] Datos' in m.text:
                live_done[0] = True
            elif m.type in ('warning', 'error') or '[ALERT]' in m.text:
                print(f'  [CON:{m.type}] {m.text[:120]}')

        page.on('console',   _on_console)
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
            await _seleccionar_proyecto_ui(page, proj_id, current_proj)
            print(f'  [Residente: {nombre} / {proj_id}] ', end='', flush=True)
            html = await _capturar(page, 'await window._raicesInformeFns.residente()')
            if html:
                resultados[('residente', nombre)] = html
                print(f'OK ({len(html)//1024} KB)')
            else:
                print('vacío')

        # 3. Capataz (por nombre y proyecto)
        for nombre, proj_ids in capataces_proyectos.items():
            for proj_id in proj_ids:
                await _seleccionar_proyecto_ui(page, proj_id, current_proj)
                print(f'  [Capataz: {nombre} / {proj_id}] ',
                      end='', flush=True)
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


def build_mappings_test(personal: dict, grupos: dict) -> tuple:
    """
    Modo TEST: usa todos los capataces/residentes (igual que producción)
    pero envía TODO al TEST_EMAIL en lugar de a los destinatarios reales.
    """
    needed_res, needed_cap, recipients = build_mappings(personal, grupos)

    # Un recipient de prueba por cada persona real (mismo adjunto, distinto dest.)
    test_recipients = []
    for r in recipients:
        test_r = dict(r)
        test_r['correo'] = TEST_EMAIL
        test_r['nombre'] = f'[TEST] {r["nombre"]}'
        test_recipients.append(test_r)

    return needed_res, needed_cap, test_recipients


# ── Gmail SMTP ─────────────────────────────────────────────────────────────
def enviar_resumen(registros: list[dict], fecha: str, dry_run: bool) -> None:
    """Envía correo de resumen de estado al administrador (RESUMEN_EMAIL)."""
    if not GMAIL_PASS:
        return
    modo = '[DRY RUN] ' if dry_run else ''
    filas = []
    for r in registros:
        estado = '✓' if r['ok'] else '✗ ERROR'
        adjuntos_str = ', '.join(r['adjuntos']) if r['adjuntos'] else '—'
        filas.append(f"  {estado}  {r['nombre']} <{r['correo']}>\n"
                     f"       Adjuntos: {adjuntos_str}")
    cuerpo = (
        f'{modo}Resumen de envío — Informes Semanales Raíces · {fecha}\n'
        f'{"="*60}\n\n'
        + '\n\n'.join(filas)
        + f'\n\n{"="*60}\n'
        + f'Total: {sum(1 for r in registros if r["ok"])} OK · '
        + f'{sum(1 for r in registros if not r["ok"])} errores\n'
    )
    msg = MIMEMultipart()
    msg['From']    = f'Informes Raíces <{GMAIL_USER}>'
    msg['To']      = RESUMEN_EMAIL
    msg['Subject'] = f'{modo}[Resumen] Informes Semanales · {fecha}'
    msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
            s.ehlo(); s.starttls()
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, RESUMEN_EMAIL, msg.as_string())
        print(f'  [Resumen] enviado a {RESUMEN_EMAIL} ✓')
    except Exception as e:
        print(f'  [Resumen] ERROR SMTP: {e}')


def enviar_correo(destinatario: str, nombre: str,
                  adjuntos: dict[str, str], fecha: str) -> bool:
    msg = MIMEMultipart('mixed')
    msg['From']    = f'Informes Raíces <{GMAIL_USER}>'
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
        needed_res, needed_cap, recipients = build_mappings_test(personal, grupos)
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
    registros_resumen: list[dict] = []

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
            registros_resumen.append({'nombre': r['nombre'], 'correo': r['correo'],
                                      'adjuntos': list(adjuntos), 'ok': True})
            ok += 1
        else:
            print(f'  Enviando a {r["nombre"]} <{r["correo"]}>'
                  f' ({len(adjuntos)} adjuntos)...', end=' ', flush=True)
            exito = enviar_correo(r['correo'], r['nombre'], adjuntos, fecha)
            registros_resumen.append({'nombre': r['nombre'], 'correo': r['correo'],
                                      'adjuntos': list(adjuntos), 'ok': exito})
            if exito:
                print('✓')
                ok += 1
            else:
                err += 1

    print(f'\n{"="*60}')
    print(f'  Resultado: {ok} OK · {err} errores')
    print(f'{"="*60}\n')

    # Enviar resumen de estado al administrador
    print('[Resumen] Enviando correo de estado...')
    enviar_resumen(registros_resumen, fecha, DRY_RUN)

    if err:
        sys.exit(1)


if __name__ == '__main__':
    main()

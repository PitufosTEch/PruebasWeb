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

        # 2. Residente (un informe por residente usando su proyecto principal)
        for nombre, proj_id in residentes_proyectos.items():
            await _seleccionar_proyecto_ui(page, proj_id, current_proj)
            print(f'  [Residente: {nombre} / {proj_id}] ', end='', flush=True)
            html = await _capturar(page, 'await window._raicesInformeFns.residente()')
            if html:
                resultados[('residente', nombre, proj_id)] = html
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
            fb_res = (persona.get('residente_nombre') or '').strip()
            if fb_res:
                entry['residente_nombre'] = fb_res  # puede ser "__todos__" o nombre exacto
            else:
                match = next(
                    (r for r in res_a_proy
                     if _norm(nombre) in _norm(r) or _norm(r) in _norm(nombre)),
                    None
                )
                entry['residente_nombre'] = match

        if 'por_capataz' in tipos:
            # Soporte para campo explícito en Firebase
            fb_cap = (persona.get('capataz_nombre') or '').strip()
            if fb_cap:
                entry['capataz_nombre'] = fb_cap  # puede ser "__todos__" o nombre exacto
            else:
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
        if rn == '__todos__':
            # Expandir: un informe por cada residente activo (multi-obra de ese residente)
            for res_name, pids in res_a_proy.items():
                if res_name not in needed_res:
                    needed_res[res_name] = pids[0]
        elif rn and rn in res_a_proy:
            needed_res[rn] = res_a_proy[rn][0]
        cn = r.get('capataz_nombre')
        if cn == '__todos__':
            for cap, pids in cap_a_proy.items():
                needed_cap[cap] = pids
        elif cn and cn in cap_a_proy:
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
    n_ok  = sum(1 for r in registros if r['ok'])
    n_err = sum(1 for r in registros if not r['ok'])

    # ── Texto plano (fallback) ──────────────────────────────────────────────
    filas_txt = []
    for r in registros:
        estado = '✓' if r['ok'] else '✗ ERROR'
        adjuntos_str = ', '.join(r['adjuntos']) if r['adjuntos'] else '—'
        filas_txt.append(f"  {estado}  {r['nombre']} <{r['correo']}>\n"
                         f"       Adjuntos: {adjuntos_str}")
    cuerpo_txt = (
        f'{modo}Resumen de envío — Informes Semanales Raíces · {fecha}\n'
        f'{"="*60}\n\n'
        + '\n\n'.join(filas_txt)
        + f'\n\n{"="*60}\n'
        + f'Total: {n_ok} OK · {n_err} errores\n'
    )

    # ── HTML ────────────────────────────────────────────────────────────────
    def _chip_color(adj: str) -> str:
        a = adj.lower()
        if 'adqui'  in a: return 'background:#FFF4E6;color:#B35A00'
        if 'estado' in a or 'pago' in a: return 'background:#F0EBFF;color:#5E35B1'
        if 'resid'  in a: return 'background:#EFF6EC;color:#2D6A4F'
        return 'background:#EBF5FF;color:#1D6FA5'  # Ejecutivo y otros

    filas_html = ''
    for r in registros:
        ok = r['ok']
        color_borde = '#40916C' if ok else '#D62828'
        color_estado = '#2D6A4F' if ok else '#D62828'
        texto_estado = 'Enviado ✓' if ok else 'ERROR ✗'
        adjs = r['adjuntos'] if r['adjuntos'] else []
        chips = ' · '.join(r['adjuntos']) if adjs else '—'
        filas_html += f"""
        <tr>
          <td style="padding:0;width:4px;background:{color_borde}">&nbsp;</td>
          <td style="padding:13px 20px;border-bottom:1px solid #E0EBE5;font-family:Arial,sans-serif">
            <span style="font-weight:600;font-size:13px;color:#1C1C1A">{r['nombre']}</span><br>
            <span style="font-size:11px;color:#8AA398">{r['correo']}</span>
          </td>
          <td style="padding:13px 20px;border-bottom:1px solid #E0EBE5;font-size:11px;color:#556B5E;text-align:right;font-family:Arial,sans-serif">
            <span style="font-family:Arial,sans-serif;font-size:10px;font-weight:700;
                         letter-spacing:.06em;text-transform:uppercase;color:{color_estado}">{texto_estado}</span><br>
            <span style="margin-top:4px;display:inline-block">{chips}</span>
          </td>
        </tr>"""

    estado_titulo = 'completado sin errores' if n_err == 0 else f'completado con {n_err} error{"es" if n_err!=1 else ""}'
    color_titulo_span = '#2D6A4F' if n_err == 0 else '#D62828'
    asunto_prefix = f'{modo}' if modo else ''

    cuerpo_html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F0F4F2;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F0F4F2;padding:32px 16px 48px">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0"
       style="background:#fff;border:1px solid #D6E4DB;border-radius:6px;overflow:hidden;max-width:620px;width:100%">

  <!-- HEADER -->
  <tr><td style="padding:28px 32px 22px;border-bottom:1px solid #E0EBE5">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:bottom">
        <div style="font-family:Arial,sans-serif;font-size:10px;font-weight:700;
                    letter-spacing:.14em;text-transform:uppercase;color:#2D6A4F;margin-bottom:8px">
          {asunto_prefix}Constructora Las Ra&iacute;ces &middot; Informes Semanales
        </div>
        <div style="font-family:Arial,sans-serif;font-size:24px;font-weight:700;
                    color:#1C1C1A;line-height:1.1">
          Env&iacute;o <span style="color:{color_titulo_span}">{estado_titulo}</span>
        </div>
        <div style="font-size:12px;color:#8AA398;margin-top:6px">{fecha}</div>
      </td>
      <td style="vertical-align:bottom;text-align:right;padding-left:16px;white-space:nowrap">
        <div style="font-family:Arial,sans-serif;font-size:52px;font-weight:700;
                    color:#2D6A4F;line-height:1">{len(registros)}</div>
        <div style="font-size:11px;color:#8AA398;text-transform:uppercase;
                    letter-spacing:.06em;margin-top:2px">Destinatarios</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- FILAS -->
  <tr><td style="padding:0">
    <table width="100%" cellpadding="0" cellspacing="0">
{filas_html}
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="padding:14px 32px;border-top:1px solid #E0EBE5;background:#F8FAF9">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:12px;color:#556B5E;font-family:Arial,sans-serif">
        <span style="font-weight:700;color:#2D6A4F">{n_ok} enviados</span>
        &nbsp;&middot;&nbsp;
        <span style="font-weight:700;color:{'#D62828' if n_err else '#8AA398'}">{n_err} errores</span>
      </td>
      <td style="font-size:11px;color:#8AA398;text-align:right;font-family:Arial,sans-serif">
        Ra&iacute;ces &mdash; Sistema autom&aacute;tico de informes
      </td>
    </tr></table>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

    # ── Armar mensaje multipart/alternative ────────────────────────────────
    msg = MIMEMultipart('alternative')
    msg['From']    = f'Informes Raíces <{GMAIL_USER}>'
    msg['To']      = RESUMEN_EMAIL
    msg['Subject'] = f'{modo}[Resumen] Informes Semanales · {fecha}'
    msg.attach(MIMEText(cuerpo_txt,  'plain', 'utf-8'))
    msg.attach(MIMEText(cuerpo_html, 'html',  'utf-8'))
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
                rn = r.get('residente_nombre')
                if rn == '__todos__':
                    # Un adjunto por cada residente activo
                    for key, html in resultados.items():
                        if isinstance(key, tuple) and key[0] == 'residente':
                            res_nombre = key[1].replace(' ', '_')
                            adjuntos[f'Residente_{res_nombre}'] = html
                elif rn:
                    for key, html in resultados.items():
                        if isinstance(key, tuple) and key[0] == 'residente' and key[1] == rn:
                            adjuntos['Residente'] = html
                            break
                else:
                    print(f'  ! {r["nombre"]}: sin residente_nombre, '
                          'agrega el campo a personal_global en Firebase')

            # Capataz (uno por proyecto)
            elif tipo == 'por_capataz':
                cn = r.get('capataz_nombre')
                if cn == '__todos__':
                    # Recibir todos los reportes de todos los capataces
                    for key, html in resultados.items():
                        if isinstance(key, tuple) and key[0] == 'capataz':
                            _, cap_n, pid = key
                            label = f'Capataz_{cap_n.split()[0]}_{pid}'
                            adjuntos[label] = html
                elif cn:
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

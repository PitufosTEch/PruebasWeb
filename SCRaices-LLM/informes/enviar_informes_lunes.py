"""
enviar_informes_lunes.py
========================
Genera y envía los informes semanales HTML desde rodrigolagoslira@gmail.com
a los destinatarios registrados en Firebase (personal_global).

Datos: data_snapshot.json (rama data-snapshot) + Firebase REST API.
Envío: Gmail SMTP con app password (secret GMAIL_APP_PASSWORD).

Variables de entorno:
  FIREBASE_URL         URL base Firebase (sin .json)
  GMAIL_APP_PASSWORD   App password de Gmail (16 chars, sin espacios)
  DRY_RUN              'true' → solo loguea, no envía (default: false en CI)
"""

import concurrent.futures
import html as html_lib
import json
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Configuración ──────────────────────────────────────────────────────────
FIREBASE_URL   = os.environ.get('FIREBASE_URL', 'https://scraices-dashboard-default-rtdb.firebaseio.com').rstrip('/')
GMAIL_USER     = 'rodrigolagoslira@gmail.com'
GMAIL_PASS     = os.environ.get('GMAIL_APP_PASSWORD', '')
DRY_RUN        = os.environ.get('DRY_RUN', 'false').lower() != 'false'
# TEST_EMAIL: si está definido, ignora personal_global y envía SOLO a este correo
TEST_EMAIL     = os.environ.get('TEST_EMAIL', '').strip()

SNAPSHOT_URL = (
    'https://raw.githubusercontent.com/PitufosTEch/PruebasWeb/'
    'data-snapshot/data_snapshot.json'
)

ACTIVE_PROJ_IDS = {
    'P119', 'P38', 'P126', 'P39', 'P127',
    'P12',  'P14', 'P116', 'P31', 'P131', 'P28',
}

CHECKPOINTS = [
    {'key': 'hpc',           'label': 'HPC'},
    {'key': 'te1',           'label': 'TE1'},
    {'key': 'visita_as',     'label': 'V.AS'},
    {'key': 'resol_as',      'label': 'R.AS'},
    {'key': 'visita_f1',     'label': 'V.F1'},
    {'key': 'fecha_f1',      'label': 'F1'},
    {'key': 'artefactado',   'label': 'Artef.'},
    {'key': 'empalme',       'label': 'Empalme'},
    {'key': 'visita_dom',    'label': 'V.DOM'},
    {'key': 'fecha_v_dom',   'label': 'F.V.DOM'},
    {'key': 'recepcion_dom', 'label': 'Recep.'},
    {'key': 'fecha_recep',   'label': 'F.Recep'},
]

INFORME_LABELS = {
    'html_navegable':    'Ejecutivo Multi-Obras',
    'adquisiciones_html':'Adquisiciones',
    'recepciones_html':  'Recepciones',
    'estados_pago_html': 'Estados de Pago',
    'residente':         'Residente',
    'por_capataz':       'Capataz',
}

# ── Helpers de datos ───────────────────────────────────────────────────────
def esc(s):
    return html_lib.escape(str(s or ''))

def fmt_peso(v):
    try:
        n = float(str(v).replace(',', '').replace('$', '').replace('\xa0', '').strip())
        return f'${n:,.0f}'.replace(',', '.')
    except Exception:
        return '—'

def fmt_fecha(s):
    if not s:
        return '—'
    s = str(s)[:10]
    p = s.split('-')
    if len(p) == 3:
        return f'{p[2]}/{p[1]}/{p[0]}'
    return s

def pct_col(pct):
    if pct >= 80: return '#16a34a'
    if pct >= 40: return '#d97706'
    return '#6b7280'

def pct_bg(pct):
    if pct >= 80: return '#f0fdf4'
    if pct >= 40: return '#fffbeb'
    return '#f8fafc'

def pct_bd(pct):
    if pct >= 80: return '#bbf7d0'
    if pct >= 40: return '#fde68a'
    return '#e2e8f0'

def get_flags(benef: dict, seg_data: dict) -> dict:
    seg  = seg_data.get(str(benef.get('ID_Benef', '')), {})
    has  = seg.get('_has', {})
    return {
        'hpc':           bool(benef.get('habil')),
        'te1':           bool(benef.get('has_te1')),
        'visita_as':     bool(has.get('visita_as')),
        'resol_as':      bool(has.get('resol_as')),
        'visita_f1':     bool(has.get('visita_f1')),
        'fecha_f1':      bool(has.get('fecha_f1')),
        'artefactado':   bool(has.get('artefactado')),
        'empalme':       bool(has.get('empalme')),
        'visita_dom':    bool(has.get('visita_dom')),
        'fecha_v_dom':   bool(has.get('fecha_v_dom')),
        'recepcion_dom': bool(has.get('recepcion_dom')),
        'fecha_recep':   bool(benef.get('fecha_recepcion') or has.get('fecha_recep')),
    }

# ── Carga de datos ─────────────────────────────────────────────────────────
def load_snapshot() -> dict:
    print(f'  Cargando snapshot desde data-snapshot …')
    r = requests.get(SNAPSHOT_URL, timeout=60)
    r.raise_for_status()
    snap = r.json()
    ts = snap.get('ts', 0)
    age_min = (datetime.now().timestamp() * 1000 - ts) / 60000
    print(f'  Snapshot OK — age: {age_min:.0f} min')
    return snap

def fb_get(path: str):
    r = requests.get(f'{FIREBASE_URL}/{path}.json', timeout=20)
    r.raise_for_status()
    return r.json() or {}

def load_firebase() -> dict:
    keys = ['personal_global', 'grupos', 'avance_gantt',
            'gantt_programa', 'observaciones', 'personal_obra',
            'despachos_data', 'cierres_forzados']
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fb_get, k): k for k in keys}
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
                print(f'  Firebase/{key}: OK')
            except Exception as e:
                print(f'  Firebase/{key}: ERROR — {e}')
                results[key] = {}
    return results

# ── CSS compartido ─────────────────────────────────────────────────────────
def _css() -> str:
    return """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f1f5f9;color:#1e293b;padding:16px}
.wrap{max-width:960px;margin:0 auto}
.hdr{background:linear-gradient(135deg,#1e293b 0%,#334155 100%);color:#fff;
     padding:18px 22px;border-radius:12px;margin-bottom:14px}
.hdr h1{font-size:17px;font-weight:700}
.hdr p{font-size:11px;color:#94a3b8;margin-top:3px}
.obra{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
      margin-bottom:12px;overflow:hidden}
.obra-hdr{background:#f8fafc;border-bottom:1px solid #e2e8f0;
          padding:9px 14px;display:flex;align-items:center;justify-content:space-between}
.obra-title{font-size:13px;font-weight:700;color:#334155}
.obra-sub{font-size:10px;color:#64748b;margin-top:2px}
.obra-body{padding:10px 14px}
.sec{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;
     letter-spacing:.5px;margin:10px 0 5px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.stat{background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:7px 11px}
.stat-v{font-size:16px;font-weight:700}
.stat-l{font-size:10px;color:#64748b;margin-top:1px}
.cp-grid{display:grid;gap:4px;margin:6px 0}
.cp-card{border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;background:#f8fafc}
.cp-top{display:flex;align-items:center;justify-content:space-between;padding:4px 7px 3px}
.cp-lbl{font-size:8px;font-weight:600;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cp-val{font-size:10px;font-weight:700;white-space:nowrap}
.cp-bar-bg{height:3px;background:rgba(0,0,0,.07)}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:#f1f5f9;color:#64748b;font-weight:600;padding:5px 8px;
   text-align:left;border-bottom:1px solid #e2e8f0}
td{padding:5px 8px;border-bottom:1px solid #f1f5f9;color:#374151;vertical-align:middle}
tr:last-child td{border-bottom:none}
.dot-ok{display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%}
.dot-no{display:inline-block;width:8px;height:8px;background:#d1d5db;border-radius:50%}
.badge{font-size:10px;font-weight:600;padding:2px 7px;border-radius:12px}
.foot{text-align:center;color:#94a3b8;font-size:10px;margin-top:16px;padding:8px}
</style>
"""

def _head(titulo: str, subtitulo: str, fecha: str) -> str:
    return (
        f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
        f'<title>{esc(titulo)}</title>{_css()}</head><body><div class="wrap">'
        f'<div class="hdr"><h1>{esc(titulo)}</h1>'
        f'<p>{esc(subtitulo)} · Generado: {esc(fecha)}</p></div>'
    )

def _foot() -> str:
    return '<div class="foot">Informe automático Constructora Raíces · No responder este correo.</div></div></body></html>'

def _cp_grid(vivs: list, seg_data: dict, cols: int = 12) -> str:
    """Genera la grilla de checkpoints para una lista de viviendas."""
    totales = {cp['key']: 0 for cp in CHECKPOINTS}
    n_total = len(vivs)
    for v in vivs:
        flags = get_flags(v, seg_data)
        for cp in CHECKPOINTS:
            if flags.get(cp['key']):
                totales[cp['key']] += 1

    cards = []
    for cp in CHECKPOINTS:
        n   = totales[cp['key']]
        pct = round(n / n_total * 100) if n_total else 0
        col = pct_col(pct); bg = pct_bg(pct); bd = pct_bd(pct)
        cards.append(
            f'<div class="cp-card" style="background:{bg};border-color:{bd};">'
            f'<div class="cp-top">'
            f'<span class="cp-lbl">{esc(cp["label"])}</span>'
            f'<span class="cp-val" style="color:{col};">{n}'
            f'<span style="font-size:8px;font-weight:400;color:#94a3b8;">/{n_total}</span></span>'
            f'</div>'
            f'<div class="cp-bar-bg"><div style="height:100%;width:{pct}%;background:{col};border-radius:0 2px 2px 0;"></div></div>'
            f'</div>'
        )
    return (
        f'<div class="cp-grid" style="grid-template-columns:repeat({cols},minmax(0,1fr));">'
        + ''.join(cards) + '</div>'
    )

def _benef_table(vivs: list, seg_data: dict) -> str:
    """Tabla detallada de beneficiarios con todos los checkpoints."""
    rows = []
    cp_headers = ''.join(f'<th title="{esc(cp["label"])}">{esc(cp["label"])}</th>' for cp in CHECKPOINTS)
    for idx, v in enumerate(vivs):
        flags = get_flags(v, seg_data)
        nombre = esc(f'{v.get("NOMBRES","").strip()} {v.get("APELLIDOS","").strip()}')
        pct_v  = v.get('pctBenef') or v.get('pctTotal') or 0
        try:   pct_v = float(pct_v)
        except: pct_v = 0
        dots = ''.join(
            f'<td style="text-align:center"><span class="dot-{"ok" if flags.get(cp["key"]) else "no"}"></span></td>'
            for cp in CHECKPOINTS
        )
        recep_class = 'background:#f0fdf4' if flags.get('fecha_recep') else ''
        rows.append(
            f'<tr style="{recep_class}">'
            f'<td style="color:#94a3b8;text-align:center">{idx+1}</td>'
            f'<td>{nombre}</td>'
            f'<td style="font-size:10px;color:#64748b;font-family:monospace">{esc(str(v.get("ID_Benef","")))} · {esc(str(v.get("tipologia",""))or"—")}</td>'
            f'{dots}'
            f'<td style="text-align:right;font-weight:700;color:{pct_col(pct_v)}">{pct_v:.1f}%</td>'
            f'</tr>'
        )
    return (
        '<div style="overflow-x:auto"><table>'
        f'<tr><th>#</th><th>Beneficiario</th><th>ID / Tipología</th>'
        f'{cp_headers}<th style="text-align:right">% Av.</th></tr>'
        + ''.join(rows) + '</table></div>'
    )

# ── Generadores de informes ────────────────────────────────────────────────

def gen_ejecutivo(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Ejecutivo Multi-Obras (html_navegable)."""
    proyectos  = snap.get('PROYECTOS_DATA', [])
    beneficios = snap.get('BENEFICIARIOS_DATA', [])
    seg_data   = snap.get('SEGUIMIENTO_DATA', {})
    avance_fb  = fb.get('avance_gantt', {})
    grupos_fb  = fb.get('grupos', {})

    obras = [p for p in proyectos if p.get('ID_proy') in ACTIVE_PROJ_IDS]
    obras.sort(key=lambda p: (avance_fb.get(p['ID_proy'], {}) or {}).get('pct', 0), reverse=True)

    n_total_benef = sum(1 for b in beneficios if b.get('ID_Proy') in ACTIVE_PROJ_IDS)
    n_obras = len(obras)

    h = _head('Informe Ejecutivo · Multi Obras',
               f'{n_obras} obras activas · {n_total_benef} beneficiarios', fecha)

    # KPIs globales
    total_recep = sum(1 for b in beneficios
                      if b.get('ID_Proy') in ACTIVE_PROJ_IDS and b.get('fecha_recepcion'))
    pct_recep_g = round(total_recep / n_total_benef * 100) if n_total_benef else 0
    h += (
        '<div class="stats">'
        f'<div class="stat"><div class="stat-v">{n_obras}</div><div class="stat-l">Obras activas</div></div>'
        f'<div class="stat"><div class="stat-v">{n_total_benef}</div><div class="stat-l">Beneficiarios</div></div>'
        f'<div class="stat"><div class="stat-v" style="color:{pct_col(pct_recep_g)}">{total_recep}</div><div class="stat-l">Recepcionados</div></div>'
        f'<div class="stat"><div class="stat-v" style="color:{pct_col(pct_recep_g)}">{pct_recep_g}%</div><div class="stat-l">% Recepción global</div></div>'
        '</div>'
    )

    for proy in obras:
        pid   = proy.get('ID_proy', '')
        nom   = proy.get('NOMBRE_PROYECTO', '')
        vivs  = [b for b in beneficios if str(b.get('ID_Proy')) == str(pid)]
        n_v   = len(vivs)
        n_hpc = sum(1 for v in vivs if get_flags(v, seg_data).get('hpc'))
        n_rec = sum(1 for v in vivs if get_flags(v, seg_data).get('fecha_recep'))
        pct_r = round(n_rec / n_v * 100) if n_v else 0

        av_gantt  = (avance_fb.get(pid) or {}).get('pct', None)
        av_str    = f'{av_gantt:.1f}%' if av_gantt is not None else '—'

        # Capataces del proyecto
        grupos = grupos_fb.get(pid, []) or []
        capataces = ', '.join(g.get('capataz', '') for g in grupos if g.get('capataz')) or '—'

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div><div class="obra-title">{esc(pid)} · {esc(nom)}</div>'
            f'<div class="obra-sub">{n_v} viviendas · Capataz: {esc(capataces)}</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:14px;font-weight:700;color:{pct_col(pct_r)}">{n_rec}/{n_v}</div>'
            f'<div style="font-size:10px;color:#64748b">Recepcionadas · Gantt: {av_str}</div>'
            f'</div></div>'
            f'<div class="obra-body">'
            f'<div class="sec">Checkpoints</div>'
        )
        h += _cp_grid(vivs, seg_data, cols=len(CHECKPOINTS))
        h += '</div></div>'

    h += _foot()
    return h


def gen_residente(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Residente — detalle completo por obra con tabla de beneficiarios."""
    proyectos  = snap.get('PROYECTOS_DATA', [])
    beneficios = snap.get('BENEFICIARIOS_DATA', [])
    seg_data   = snap.get('SEGUIMIENTO_DATA', {})
    avance_fb  = fb.get('avance_gantt', {})
    grupos_fb  = fb.get('grupos', {})

    obras = [p for p in proyectos if p.get('ID_proy') in ACTIVE_PROJ_IDS]
    obras.sort(key=lambda p: (avance_fb.get(p['ID_proy'], {}) or {}).get('pct', 0), reverse=True)

    h = _head('Informe Residente · Multi Obras',
               f'{len(obras)} obras activas', fecha)

    for proy in obras:
        pid  = proy.get('ID_proy', '')
        nom  = proy.get('NOMBRE_PROYECTO', '')
        vivs = [b for b in beneficios if str(b.get('ID_Proy')) == str(pid)]
        n_v  = len(vivs)
        n_rec = sum(1 for v in vivs if get_flags(v, seg_data).get('fecha_recep'))
        pct_r = round(n_rec / n_v * 100) if n_v else 0
        av    = (avance_fb.get(pid) or {}).get('pct', None)

        grupos = grupos_fb.get(pid, []) or []
        grupo_rows = ''
        for g in grupos:
            gvivs = [v for v in vivs if str(v.get('ID_Benef', '')) in
                     [str(x) for x in (g.get('beneficiarios') or [])]]
            grupo_rows += (
                f'<tr><td>{esc(g.get("nombre",""))}</td>'
                f'<td>{esc(g.get("capataz","") or "—")}</td>'
                f'<td>{len(gvivs)}</td></tr>'
            )

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div><div class="obra-title">{esc(pid)} · {esc(nom)}</div>'
            f'<div class="obra-sub">{n_v} viviendas</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:14px;font-weight:700;color:{pct_col(pct_r)}">{pct_r}% recep.</div>'
            f'<div style="font-size:10px;color:#64748b">Gantt: {f"{av:.1f}%" if av is not None else "—"}</div>'
            f'</div></div>'
            f'<div class="obra-body">'
            f'<div class="sec">Checkpoints globales</div>'
        )
        h += _cp_grid(vivs, seg_data, cols=len(CHECKPOINTS))
        h += f'<div class="sec" style="margin-top:10px">Detalle de viviendas</div>'
        h += _benef_table(vivs, seg_data)
        h += '</div></div>'

    h += _foot()
    return h


def gen_capataz(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Capataz — una sección por capataz con sus beneficiarios."""
    proyectos  = snap.get('PROYECTOS_DATA', [])
    beneficios = snap.get('BENEFICIARIOS_DATA', [])
    seg_data   = snap.get('SEGUIMIENTO_DATA', {})
    grupos_fb  = fb.get('grupos', {})

    # Indexar benef por ID
    benef_idx = {str(b.get('ID_Benef', '')): b for b in beneficios}

    # Recolectar todos los capataces con sus viviendas
    capataz_data: dict[str, list] = {}   # nombre_capataz → [benef, ...]
    capataz_obra:  dict[str, list] = {}  # nombre_capataz → [nombre_obra, ...]

    for proy in proyectos:
        if proy.get('ID_proy') not in ACTIVE_PROJ_IDS:
            continue
        pid = proy.get('ID_proy', '')
        nom = f'{pid} · {proy.get("NOMBRE_PROYECTO","")}'
        grupos = grupos_fb.get(pid, []) or []
        vivs_proy = [b for b in beneficios if str(b.get('ID_Proy')) == str(pid)]

        for g in grupos:
            cap = g.get('capataz', '').strip()
            if not cap:
                continue
            # Intentar obtener beneficiarios del grupo
            ids_grupo = [str(x) for x in (g.get('beneficiarios') or [])]
            if ids_grupo:
                gvivs = [benef_idx[i] for i in ids_grupo if i in benef_idx]
            else:
                # fallback: todas las viviendas del proyecto si no hay asignación
                gvivs = vivs_proy

            if cap not in capataz_data:
                capataz_data[cap] = []
                capataz_obra[cap] = []
            capataz_data[cap].extend(gvivs)
            if nom not in capataz_obra[cap]:
                capataz_obra[cap].append(nom)

    n_cap = len(capataz_data)
    h = _head('Informe Capataz · Multi Obras',
               f'{n_cap} capataces · {sum(len(v) for v in capataz_data.values())} asignaciones', fecha)

    for cap_name, vivs in sorted(capataz_data.items()):
        obras_str = ', '.join(capataz_obra[cap_name])
        n_v   = len(vivs)
        n_rec = sum(1 for v in vivs if get_flags(v, seg_data).get('fecha_recep'))
        pct_r = round(n_rec / n_v * 100) if n_v else 0

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div><div class="obra-title">Capataz: {esc(cap_name)}</div>'
            f'<div class="obra-sub">{esc(obras_str)}</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:14px;font-weight:700;color:{pct_col(pct_r)}">{n_rec}/{n_v} recep.</div>'
            f'</div></div>'
            f'<div class="obra-body">'
            f'<div class="sec">Checkpoints</div>'
        )
        h += _cp_grid(vivs, seg_data, cols=len(CHECKPOINTS))
        h += f'<div class="sec" style="margin-top:10px">Viviendas asignadas</div>'
        h += _benef_table(vivs, seg_data)
        h += '</div></div>'

    h += _foot()
    return h


def gen_adquisiciones(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Adquisiciones — despachos por obra."""
    proyectos = snap.get('PROYECTOS_DATA', [])
    despachos = snap.get('DESPACHOS_DATA', [])
    benef_list = snap.get('BENEFICIARIOS_DATA', [])

    benef_idx = {str(b.get('ID_Benef', '')): b for b in benef_list}

    obras = [p for p in proyectos if p.get('ID_proy') in ACTIVE_PROJ_IDS]

    total_desp = sum(1 for d in despachos if d.get('ID_Proy') in ACTIVE_PROJ_IDS)
    h = _head('Informe Adquisiciones · Multi Obras',
               f'{len(obras)} obras · {total_desp} despachos', fecha)

    for proy in obras:
        pid = proy.get('ID_proy', '')
        nom = proy.get('NOMBRE_PROYECTO', '')
        desps = [d for d in despachos if str(d.get('ID_Proy', '')) == str(pid)]

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div class="obra-title">{esc(pid)} · {esc(nom)}</div>'
            f'<div class="obra-sub">{len(desps)} despachos</div>'
            f'</div>'
            f'<div class="obra-body">'
        )
        if desps:
            rows = []
            for d in sorted(desps, key=lambda x: str(x.get('Fecha_despacho', '') or ''), reverse=True):
                bid   = str(d.get('ID_Benef', ''))
                bname = ''
                if bid in benef_idx:
                    b = benef_idx[bid]
                    bname = f'{b.get("NOMBRES","").strip()} {b.get("APELLIDOS","").strip()}'
                rows.append(
                    f'<tr>'
                    f'<td>{esc(fmt_fecha(d.get("Fecha_despacho","")))}</td>'
                    f'<td>{esc(str(d.get("Tipo_despacho","") or "—"))}</td>'
                    f'<td>{esc(bname or bid or "—")}</td>'
                    f'<td>{esc(str(d.get("tipologia","") or "—"))}</td>'
                    f'<td style="text-align:right">{esc(str(d.get("Nro_despacho","") or "—"))}</td>'
                    f'</tr>'
                )
            h += (
                '<div style="overflow-x:auto"><table>'
                '<tr><th>Fecha</th><th>Tipo</th><th>Beneficiario</th>'
                '<th>Tipología</th><th style="text-align:right">N°</th></tr>'
                + ''.join(rows) + '</table></div>'
            )
        else:
            h += '<p style="color:#94a3b8;font-size:11px;padding:6px 0">Sin despachos registrados.</p>'
        h += '</div></div>'

    h += _foot()
    return h


def gen_recepciones(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Recepciones — estado de recepción por obra."""
    proyectos  = snap.get('PROYECTOS_DATA', [])
    beneficios = snap.get('BENEFICIARIOS_DATA', [])
    seg_data   = snap.get('SEGUIMIENTO_DATA', {})

    obras = [p for p in proyectos if p.get('ID_proy') in ACTIVE_PROJ_IDS]

    h = _head('Informe Recepciones · Multi Obras',
               f'{len(obras)} obras activas', fecha)

    for proy in obras:
        pid  = proy.get('ID_proy', '')
        nom  = proy.get('NOMBRE_PROYECTO', '')
        vivs = [b for b in beneficios if str(b.get('ID_Proy')) == str(pid)]
        n_rec = sum(1 for v in vivs if get_flags(v, seg_data).get('fecha_recep'))
        pct_r = round(n_rec / len(vivs) * 100) if vivs else 0

        rows = []
        for v in vivs:
            flags  = get_flags(v, seg_data)
            recep  = v.get('fecha_recepcion', '') or ''
            nombre = f'{v.get("NOMBRES","").strip()} {v.get("APELLIDOS","").strip()}'

            # Checkpoints previos a recepción
            cp_dom  = flags.get('visita_dom')
            cp_fvdom= flags.get('fecha_v_dom')
            cp_rdom = flags.get('recepcion_dom')

            estado = (
                '✓ Recepcionada' if flags.get('fecha_recep') else
                'Dom. aprobado'  if cp_rdom else
                'V.DOM realizada' if cp_dom else
                'Pendiente'
            )
            estado_col = '#16a34a' if flags.get('fecha_recep') else (
                '#2563eb' if cp_rdom else
                '#d97706' if cp_dom else '#6b7280'
            )
            pct_v = v.get('pctBenef') or v.get('pctTotal') or 0
            try: pct_v = float(pct_v)
            except: pct_v = 0

            rows.append(
                f'<tr>'
                f'<td>{esc(nombre)}</td>'
                f'<td style="font-size:10px;font-family:monospace;color:#64748b">{esc(str(v.get("ID_Benef","")))}</td>'
                f'<td>{esc(str(v.get("tipologia","") or "—"))}</td>'
                f'<td style="text-align:center"><span class="dot-{"ok" if cp_dom else "no"}"></span></td>'
                f'<td style="text-align:center"><span class="dot-{"ok" if cp_rdom else "no"}"></span></td>'
                f'<td style="color:{pct_col(pct_v)};text-align:right;font-weight:700">{pct_v:.1f}%</td>'
                f'<td style="color:{estado_col};font-weight:600;font-size:10px">{esc(estado)}</td>'
                f'<td style="font-size:10px">{esc(fmt_fecha(recep)) if recep else "—"}</td>'
                f'</tr>'
            )

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div><div class="obra-title">{esc(pid)} · {esc(nom)}</div>'
            f'<div class="obra-sub">{len(vivs)} viviendas</div></div>'
            f'<span class="badge" style="background:{pct_bg(pct_r)};color:{pct_col(pct_r)};border:1px solid {pct_bd(pct_r)}">'
            f'{n_rec}/{len(vivs)} · {pct_r}% recepcionadas</span>'
            f'</div>'
            f'<div class="obra-body"><div style="overflow-x:auto"><table>'
            f'<tr><th>Beneficiario</th><th>ID</th><th>Tipología</th>'
            f'<th>V.DOM</th><th>Recep.DOM</th><th style="text-align:right">% Av.</th>'
            f'<th>Estado</th><th>Fecha Recep.</th></tr>'
            + ''.join(rows) +
            f'</table></div></div></div>'
        )

    h += _foot()
    return h


def gen_estados_pago(snap: dict, fb: dict, fecha: str) -> str:
    """Informe Estados de Pago — solicitudes y EEPP por obra."""
    proyectos  = snap.get('PROYECTOS_DATA', [])
    solpago    = snap.get('SOLPAGO_DATA', [])  or []
    eepp       = snap.get('EEPP_DATA', [])     or []
    beneficios = snap.get('BENEFICIARIOS_DATA', [])
    avance_fb  = fb.get('avance_gantt', {})

    benef_idx  = {str(b.get('ID_Benef', '')): b for b in beneficios}

    obras = [p for p in proyectos
             if p.get('ID_proy') in ACTIVE_PROJ_IDS and p.get('estado') == 'ejecucion']

    h = _head('Informe Estados de Pago · Multi Obras',
               f'{len(obras)} obras en ejecución', fecha)

    for proy in obras:
        pid  = proy.get('ID_proy', '')
        nom  = proy.get('NOMBRE_PROYECTO', '')
        av   = (avance_fb.get(pid) or {}).get('pct', None)

        sps  = [s for s in solpago if str(s.get('ID_Proy', '')) == str(pid)]
        eeps = [e for e in eepp    if str(e.get('ID_Proy', '')) == str(pid)]

        total_sp  = sum(float(str(s.get('Monto', 0) or 0).replace(',', '').replace('$','')) for s in sps if s.get('Monto'))
        total_ee  = sum(float(str(e.get('Monto_ep', 0) or 0).replace(',', '').replace('$','')) for e in eeps if e.get('Monto_ep'))

        sp_rows = []
        for s in sorted(sps, key=lambda x: str(x.get('Fecha_solicitud', '') or ''), reverse=True):
            bid = str(s.get('ID_Benef', ''))
            bn  = ''
            if bid in benef_idx:
                b = benef_idx[bid]; bn = f'{b.get("NOMBRES","").strip()} {b.get("APELLIDOS","").strip()}'
            estado = str(s.get('Estado_solicitud', '') or '—')
            estado_col = '#16a34a' if 'aprobad' in estado.lower() else '#d97706' if 'pendiente' in estado.lower() else '#6b7280'
            sp_rows.append(
                f'<tr><td>{esc(fmt_fecha(s.get("Fecha_solicitud","")))}</td>'
                f'<td>{esc(bn or bid)}</td>'
                f'<td style="color:{estado_col};font-weight:600;font-size:10px">{esc(estado)}</td>'
                f'<td style="text-align:right;font-family:monospace">{esc(fmt_peso(s.get("Monto","")))}</td>'
                f'</tr>'
            )

        h += (
            f'<div class="obra">'
            f'<div class="obra-hdr">'
            f'<div><div class="obra-title">{esc(pid)} · {esc(nom)}</div>'
            f'<div class="obra-sub">Avance Gantt: {f"{av:.1f}%" if av is not None else "—"}</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:11px;color:#64748b">Sol. Pago: <strong style="color:#7c3aed">{fmt_peso(total_sp)}</strong></div>'
            f'<div style="font-size:11px;color:#64748b">EEPP: <strong style="color:#2563eb">{fmt_peso(total_ee)}</strong></div>'
            f'</div></div>'
            f'<div class="obra-body">'
        )

        if sp_rows:
            h += (
                f'<div class="sec">Solicitudes de Pago ({len(sps)})</div>'
                f'<div style="overflow-x:auto"><table>'
                f'<tr><th>Fecha</th><th>Beneficiario</th><th>Estado</th>'
                f'<th style="text-align:right">Monto</th></tr>'
                + ''.join(sp_rows) + '</table></div>'
            )
        else:
            h += '<p style="color:#94a3b8;font-size:11px">Sin solicitudes de pago registradas.</p>'

        h += '</div></div>'

    h += _foot()
    return h


# ── Dispatch de informes ───────────────────────────────────────────────────
GENERATORS = {
    'html_navegable':    gen_ejecutivo,
    'residente':         gen_residente,
    'por_capataz':       gen_capataz,
    'adquisiciones_html':gen_adquisiciones,
    'recepciones_html':  gen_recepciones,
    'estados_pago_html': gen_estados_pago,
}

def generar_informe(tipo: str, snap: dict, fb: dict, fecha: str) -> str:
    fn = GENERATORS.get(tipo)
    if fn is None:
        return f'<html><body><p>Tipo de informe desconocido: {tipo}</p></body></html>'
    return fn(snap, fb, fecha)

# ── Envío de correo ────────────────────────────────────────────────────────
def enviar_correo(destinatario: str, nombre: str,
                  adjuntos: dict[str, str], fecha: str) -> bool:
    """Envía un correo con los informes como adjuntos HTML."""
    msg = MIMEMultipart('mixed')
    msg['From']    = GMAIL_USER
    msg['To']      = destinatario
    msg['Subject'] = f'Informes Semanales · Constructora Raíces · {fecha}'

    tipos_str = ', '.join(INFORME_LABELS.get(t, t) for t in adjuntos)
    body = MIMEText(
        f'Estimado/a {nombre},\n\n'
        f'Se adjuntan los informes semanales correspondientes al {fecha}:\n'
        + ''.join(f'  • {INFORME_LABELS.get(t, t)}\n' for t in adjuntos)
        + '\nPara visualizarlos, abra el archivo adjunto en su navegador web.\n\n'
        f'Constructora Raíces · Informe automático · No responda este correo.',
        'plain', 'utf-8'
    )
    msg.attach(body)

    for tipo, html_content in adjuntos.items():
        filename = f'informe_{tipo}_{fecha.replace("/","_")}.html'
        part = MIMEBase('text', 'html')
        part.set_payload(html_content.encode('utf-8'))
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=filename)
        part.add_header('Content-Type', 'text/html; charset=utf-8')
        msg.attach(part)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, destinatario, msg.as_string())
        return True
    except Exception as e:
        print(f'  ERROR al enviar a {destinatario}: {e}')
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

    # 1. Cargar datos
    print('[ 1/3 ] Cargando datos …')
    snap = load_snapshot()
    fb   = load_firebase()

    # 2. Construir lista de destinatarios
    print('\n[ 2/3 ] Procesando destinatarios …')
    if test_mode:
        # Modo prueba: SOLO el correo indicado, todos los tipos de informe
        todos_tipos = list(GENERATORS.keys())
        destinatarios = [{'correo': TEST_EMAIL, 'nombre': 'Prueba', 'tipos': todos_tipos}]
        print(f'  ⚠ MODO PRUEBA — envío exclusivo a {TEST_EMAIL}')
        print(f'  Tipos incluidos: {", ".join(todos_tipos)}')
    else:
        personal = fb.get('personal_global', {}) or {}
        destinatarios = []
        for key, persona in personal.items():
            correo  = (persona.get('correo') or '').strip()
            tipos   = persona.get('informes') or []
            nombre  = persona.get('nombre', 'Equipo')
            if not correo or not tipos:
                continue
            destinatarios.append({'correo': correo, 'nombre': nombre, 'tipos': tipos})
            print(f'  → {nombre} <{correo}> : {", ".join(tipos)}')

    if not destinatarios:
        print('  ! Sin destinatarios configurados con correo e informes asignados.')
        sys.exit(0)

    # 3. Pre-generar cada tipo único (evitar regenerar el mismo informe varias veces)
    tipos_requeridos = set(t for d in destinatarios for t in d['tipos'])
    print(f'\n[ 3/3 ] Generando {len(tipos_requeridos)} tipo(s) de informe …')
    cache_html: dict[str, str] = {}
    for tipo in sorted(tipos_requeridos):
        print(f'  Generando: {INFORME_LABELS.get(tipo, tipo)} …', end=' ')
        try:
            cache_html[tipo] = generar_informe(tipo, snap, fb, fecha)
            size_kb = len(cache_html[tipo]) / 1024
            print(f'OK ({size_kb:.0f} KB)')
        except Exception as e:
            print(f'ERROR — {e}')
            cache_html[tipo] = f'<html><body><p>Error generando informe {tipo}: {e}</p></body></html>'

    # 4. Enviar (o simular)
    print(f'\n{"─"*60}')
    ok = err = 0
    for d in destinatarios:
        adjuntos = {t: cache_html[t] for t in d['tipos'] if t in cache_html}
        if not adjuntos:
            continue
        tipos_str = ', '.join(INFORME_LABELS.get(t, t) for t in adjuntos)
        if DRY_RUN:
            print(f'  [DRY] {d["nombre"]} <{d["correo"]}> → {tipos_str}')
            ok += 1
        else:
            print(f'  Enviando a {d["nombre"]} <{d["correo"]}> …', end=' ')
            if enviar_correo(d['correo'], d['nombre'], adjuntos, fecha):
                print('✓')
                ok += 1
            else:
                print('✗')
                err += 1

    print(f'\n{"="*60}')
    print(f'  Resultado: {ok} enviados, {err} errores')
    print(f'{"="*60}\n')

    if err > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()

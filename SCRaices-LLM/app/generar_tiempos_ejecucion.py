"""Genera HTML con tabla de tiempos de ejecucion de todos los proyectos desde 2021"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import json
from data_manager import DataManager
from datetime import datetime, timedelta
from pathlib import Path

def pf(f):
    if not f or str(f) in ['nan','NaT','','None']:
        return None
    for fmt in ['%m/%d/%Y','%d/%m/%Y','%Y-%m-%d','%d-%m-%Y']:
        try:
            return datetime.strptime(str(f).split()[0], fmt)
        except:
            pass
    return None

def generar():
    dm = DataManager()
    proy = dm.get_table_data('Proyectos')
    ben = dm.get_table_data('Beneficiario')
    desp = dm.get_table_data('Despacho')

    results = []
    for _, pr in proy.iterrows():
        fi = pf(pr.get('fecha_inicio', ''))
        if not fi or fi.year < 2021:
            continue
        pid = str(pr['ID_proy'])
        nombre = str(pr['NOMBRE_PROYECTO'])
        comuna = str(pr.get('COMUNA', ''))
        estado = str(pr.get('estado_general', ''))
        dur = 0
        try:
            dur = int(float(str(pr.get('duracion', '0'))))
        except:
            pass
        fv = fi + timedelta(days=dur) if dur > 0 else None

        bens_p = ben[ben['ID_Proy'].astype(str) == pid]
        n_viv = len(bens_p)
        if n_viv == 0:
            continue
        ids_b = set(bens_p['ID_Benef'].astype(str))

        desp_p = desp[desp['ID_Benef'].astype(str).isin(ids_b)]
        fd_list = [pf(d.get('Fecha', '')) for _, d in desp_p.iterrows()]
        fd_list = [f for f in fd_list if f]
        primer_desp = min(fd_list) if fd_list else None

        fr_list = []
        for _, b in bens_p.iterrows():
            fr = pf(b.get('F_R_dom', ''))
            if fr:
                fr_list.append(fr)
        n_recep = len(fr_list)
        primera_r = min(fr_list) if fr_list else None
        ultima_r = max(fr_list) if fr_list else None

        dias_contrato = (ultima_r - fi).days if ultima_r and fi else None
        exceso = dias_contrato - dur if dias_contrato and dur > 0 else None
        dias_obra = (ultima_r - primer_desp).days if ultima_r and primer_desp else None

        results.append({
            'nombre': nombre, 'comuna': comuna, 'estado': estado, 'n_viv': n_viv,
            'fi': fi.strftime('%Y-%m-%d'), 'dur': dur,
            'fv': fv.strftime('%Y-%m-%d') if fv else '',
            'pd': primer_desp.strftime('%Y-%m-%d') if primer_desp else '',
            'pr': primera_r.strftime('%Y-%m-%d') if primera_r else '',
            'ur': ultima_r.strftime('%Y-%m-%d') if ultima_r else '',
            'nr': n_recep, 'dc': dias_contrato, 'ex': exceso, 'do': dias_obra
        })

    results.sort(key=lambda x: x['fi'])
    print(f"Proyectos desde 2021: {len(results)}")

    data_json = json.dumps(results, ensure_ascii=False)
    hoy = datetime.now().strftime('%d/%m/%Y %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tiempos de Ejecucion — SCRaices</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
body{{font-family:'IBM Plex Sans',sans-serif}}
.mono,.font-mono{{font-family:'IBM Plex Mono',monospace}}
table{{border-collapse:collapse}}
th,td{{white-space:nowrap}}
tr:hover td{{background:#f8fafc !important}}
.bar-c{{position:relative;height:18px;min-width:220px}}
.bar{{position:absolute;height:100%;border-radius:3px;top:0}}
.fbtn{{padding:6px 14px;border-radius:8px;font-size:12px;font-weight:500;background:white;color:#6b7280;border:1px solid #e5e7eb;cursor:pointer;transition:all .15s}}
.fbtn:hover{{border-color:#9ca3af}}
.fbtn.active{{background:#7c3aed;color:white;border-color:#7c3aed;box-shadow:0 1px 3px rgba(124,58,237,.3)}}
.sort-btn{{cursor:pointer;user-select:none}}
.sort-btn:hover{{color:#7c3aed}}
</style>
</head><body class="bg-gray-50 text-gray-800">

<div class="bg-slate-900 text-white px-6 py-3 flex items-center justify-between">
<div class="font-bold text-lg tracking-tight"><span class="text-indigo-400">SC</span> Tiempos de Ejecucion</div>
<div class="text-xs text-gray-400">Proyectos desde 2021 &middot; Generado: {hoy}</div>
</div>

<div class="max-w-[1600px] mx-auto px-4 py-5">

<div class="flex items-center gap-3 mb-4 flex-wrap">
<button onclick="setFilter('todos')" class="fbtn active" data-f="todos">Todos</button>
<button onclick="setFilter('finalizado')" class="fbtn" data-f="finalizado">Finalizados</button>
<button onclick="setFilter('ejecucion')" class="fbtn" data-f="ejecucion">En Ejecucion</button>
<button onclick="setFilter('excedido')" class="fbtn" data-f="excedido">Excedidos</button>
<button onclick="setFilter('pendiente')" class="fbtn" data-f="pendiente">Sin Recepcion</button>
<button id="btnOcultos" onclick="toggleModalOcultos()" class="fbtn" style="border-color:#f59e0b;color:#92400e;background:#fffbeb;display:none">
<svg class="inline w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg>
<span id="txtOcultos">0 ocultos</span>
</button>
<div class="ml-auto flex items-center gap-4 text-xs text-gray-500">
<span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-slate-200 inline-block border border-slate-300"></span>Plazo contrato</span>
<span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-blue-400 inline-block"></span>Pre-despacho</span>
<span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-emerald-500 inline-block"></span>Ejecucion obra</span>
<span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded bg-red-400 inline-block"></span>Exceso plazo</span>
</div>
</div>

<div id="kpis" class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-5"></div>

<div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
<table class="w-full text-xs">
<thead>
<tr class="bg-gray-50 border-b border-gray-200 text-[10px] uppercase tracking-wide text-gray-500">
<th class="px-3 py-2.5 text-left sticky left-0 bg-gray-50 z-10 sort-btn" onclick="sortBy('nombre')">Proyecto &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-left">Comuna</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('n_viv')">Viv &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('fi')">Inicio &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-center">1er Desp</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('dur')">Plazo &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-center">Venc.</th>
<th class="px-2 py-2.5 text-center">1ra Recep</th>
<th class="px-2 py-2.5 text-center">Ult Recep</th>
<th class="px-2 py-2.5 text-center">Recep</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('dc')">Dias Ini→Rec &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('do')">Dias Obra &#x25B4;&#x25BE;</th>
<th class="px-2 py-2.5 text-center sort-btn" onclick="sortBy('ex')">Dif &#x25B4;&#x25BE;</th>
<th class="px-3 py-2.5 text-left" style="min-width:250px">Timeline</th>
</tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>
</div>

<!-- Modal ocultos -->
<div id="modalOcultos" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:100;align-items:center;justify-content:center" onclick="if(event.target===this)toggleModalOcultos()">
<div style="background:white;border-radius:16px;width:480px;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.2)">
<div style="padding:16px 20px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between">
<h3 style="font-weight:700;font-size:14px">Proyectos Ocultos</h3>
<button onclick="toggleModalOcultos()" style="color:#9ca3af;font-size:20px;cursor:pointer;border:none;background:none">&times;</button>
</div>
<div id="modalBody" style="padding:16px"></div>
<div style="padding:12px 20px;border-top:1px solid #f3f4f6;display:flex;justify-content:space-between;align-items:center">
<button onclick="mostrarTodos()" style="font-size:12px;color:#7c3aed;font-weight:600;cursor:pointer;border:none;background:none">Mostrar todos</button>
<button onclick="toggleModalOcultos()" style="padding:6px 16px;background:#1e293b;color:white;font-size:12px;border-radius:8px;cursor:pointer;border:none">Cerrar</button>
</div>
</div>
</div>

<script>
const DATA = {data_json};
const LS_KEY = 'scraices_tiempos_ocultos';
let currentFilter = 'todos';
let sortField = 'fi';
let sortAsc = true;

function getOcultos() {{ try {{ return JSON.parse(localStorage.getItem(LS_KEY)) || []; }} catch {{ return []; }} }}
function setOcultos(arr) {{ localStorage.setItem(LS_KEY, JSON.stringify(arr)); render(); renderModal(); }}

function ocultarProy(nombre) {{
    const oc = getOcultos();
    if (!oc.includes(nombre)) oc.push(nombre);
    setOcultos(oc);
}}
function mostrarProy(nombre) {{
    setOcultos(getOcultos().filter(n => n !== nombre));
}}
function mostrarTodos() {{
    setOcultos([]);
}}

function toggleModalOcultos() {{
    const m = document.getElementById('modalOcultos');
    const show = m.style.display === 'none';
    m.style.display = show ? 'flex' : 'none';
    if (show) renderModal();
}}

function renderModal() {{
    const oc = getOcultos();
    const body = document.getElementById('modalBody');
    const btn = document.getElementById('btnOcultos');
    const txt = document.getElementById('txtOcultos');
    btn.style.display = oc.length > 0 ? 'inline-flex' : 'none';
    txt.textContent = oc.length + ' oculto' + (oc.length !== 1 ? 's' : '');
    if (oc.length === 0) {{
        body.innerHTML = '<p style="color:#9ca3af;text-align:center;padding:24px;font-size:13px">No hay proyectos ocultos</p>';
        return;
    }}
    let html = '';
    oc.forEach(nombre => {{
        html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#f9fafb;border-radius:10px;border:1px solid #e5e7eb;margin-bottom:8px">
            <span style="font-weight:600;font-size:13px;color:#1f2937">${{nombre}}</span>
            <button onclick="mostrarProy('${{nombre.replace(/'/g,\"\\\\'\")}}')" style="padding:4px 12px;background:#7c3aed;color:white;font-size:11px;font-weight:600;border-radius:8px;cursor:pointer;border:none">Mostrar</button>
        </div>`;
    }});
    body.innerHTML = html;
}}

function ff(iso) {{
    if (!iso) return '—';
    const p = iso.split('-');
    return p[2]+'/'+p[1]+'/'+p[0].slice(2);
}}

function setFilter(f) {{
    currentFilter = f;
    document.querySelectorAll('.fbtn').forEach(b => {{
        b.classList.toggle('active', b.dataset.f === f);
    }});
    render();
}}

function sortBy(field) {{
    if (sortField === field) sortAsc = !sortAsc;
    else {{ sortField = field; sortAsc = true; }}
    render();
}}

function render() {{
    const ocultos = getOcultos();
    let filtered = DATA.filter(r => !ocultos.includes(r.nombre));
    if (currentFilter === 'finalizado') filtered = filtered.filter(r => r.estado.toLowerCase().includes('finaliz'));
    else if (currentFilter === 'ejecucion') filtered = filtered.filter(r => r.estado.toLowerCase().includes('ejecuci'));
    else if (currentFilter === 'excedido') filtered = filtered.filter(r => r.ex !== null && r.ex > 0);
    else if (currentFilter === 'pendiente') filtered = filtered.filter(r => r.nr === 0);

    // Sort
    filtered.sort((a, b) => {{
        let va = a[sortField], vb = b[sortField];
        if (va === null || va === '') va = sortAsc ? 99999 : -99999;
        if (vb === null || vb === '') vb = sortAsc ? 99999 : -99999;
        if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        return sortAsc ? va - vb : vb - va;
    }});

    // KPIs
    const total = filtered.length;
    const completos = filtered.filter(r => r.nr === r.n_viv && r.nr > 0);
    const excedidos = filtered.filter(r => r.ex !== null && r.ex > 0);
    const totalViv = filtered.reduce((s,r) => s + r.n_viv, 0);
    const totalRecep = filtered.reduce((s,r) => s + r.nr, 0);
    const avgDias = completos.length ? Math.round(completos.reduce((s,r) => s + r.dc, 0) / completos.length) : 0;
    const avgObra = completos.filter(r=>r.do).length ? Math.round(completos.filter(r=>r.do).reduce((s,r) => s + r.do, 0) / completos.filter(r=>r.do).length) : 0;

    document.getElementById('kpis').innerHTML = `
        <div class="bg-white rounded-xl p-3 border border-gray-200"><div class="text-[10px] uppercase text-gray-500">Proyectos</div><div class="text-2xl font-bold font-mono mt-1">${{total}}</div></div>
        <div class="bg-white rounded-xl p-3 border border-blue-200"><div class="text-[10px] uppercase text-blue-600">Viviendas</div><div class="text-2xl font-bold font-mono text-blue-600 mt-1">${{totalViv}}</div><div class="text-[10px] text-gray-400">${{totalRecep}} recep. (${{totalViv?Math.round(totalRecep/totalViv*100):0}}%)</div></div>
        <div class="bg-white rounded-xl p-3 border border-green-200"><div class="text-[10px] uppercase text-green-600">100% Completos</div><div class="text-2xl font-bold font-mono text-green-600 mt-1">${{completos.length}}</div></div>
        <div class="bg-white rounded-xl p-3 border border-red-200"><div class="text-[10px] uppercase text-red-600">Excedidos</div><div class="text-2xl font-bold font-mono text-red-600 mt-1">${{excedidos.length}}</div></div>
        <div class="bg-white rounded-xl p-3 border border-violet-200"><div class="text-[10px] uppercase text-violet-600">Prom Inicio→Recep</div><div class="text-2xl font-bold font-mono text-violet-600 mt-1">${{avgDias}}d</div></div>
        <div class="bg-white rounded-xl p-3 border border-indigo-200"><div class="text-[10px] uppercase text-indigo-600">Prom Dias Obra</div><div class="text-2xl font-bold font-mono text-indigo-600 mt-1">${{avgObra}}d</div></div>
    `;

    const maxDays = Math.max(...filtered.map(r => Math.max(r.dur || 0, r.dc || 0, (r.dur||0)+(r.ex>0?r.ex:0))), 100);
    const scale = 220 / maxDays;

    let rows = '';
    filtered.forEach(r => {{
        const esExcedido = r.ex !== null && r.ex > 0;
        const completo = r.nr === r.n_viv && r.nr > 0;
        const rowBg = esExcedido ? 'background:#fef2f2' : '';

        let difHtml = '—';
        if (r.ex !== null) {{
            const color = r.ex > 0 ? '#ef4444' : '#22c55e';
            const sign = r.ex > 0 ? '+' : '';
            difHtml = `<span class="font-mono font-bold" style="color:${{color}}">${{sign}}${{r.ex}}d</span>`;
        }}

        const pctRecep = r.n_viv > 0 ? Math.round(r.nr / r.n_viv * 100) : 0;
        const recepColor = pctRecep === 100 ? 'text-green-600' : pctRecep > 0 ? 'text-blue-600' : 'text-gray-400';

        let badge = '';
        const el = r.estado.toLowerCase();
        if (el.includes('finaliz')) badge = '<span class="text-[8px] bg-green-100 text-green-700 px-1 rounded ml-1">FIN</span>';
        else if (el.includes('ejecuci')) badge = '<span class="text-[8px] bg-blue-100 text-blue-700 px-1 rounded ml-1">EJ</span>';
        else if (el.includes('sin ej')) badge = '<span class="text-[8px] bg-gray-100 text-gray-500 px-1 rounded ml-1">SIN</span>';

        const plazoW = Math.max(r.dur * scale, 2);
        let preW = 0;
        if (r.pd && r.fi) {{
            const d1 = new Date(r.fi), d2 = new Date(r.pd);
            preW = Math.max(((d2-d1)/(86400000)) * scale, 0);
        }}
        const obraW = r.do ? Math.max(r.do * scale, 2) : 0;
        const exW = (r.ex && r.ex > 0) ? Math.max(r.ex * scale, 2) : 0;

        const timeline = `<div class="bar-c">
            <div class="bar bg-slate-200 border border-slate-300" style="left:0;width:${{plazoW}}px"></div>
            ${{preW > 0 ? `<div class="bar bg-blue-400 opacity-60" style="left:0;width:${{preW}}px"></div>` : ''}}
            ${{obraW > 0 ? `<div class="bar bg-emerald-500" style="left:${{preW}}px;width:${{obraW}}px"></div>` : ''}}
            ${{exW > 0 ? `<div class="bar bg-red-400" style="left:${{plazoW}}px;width:${{exW}}px"></div>` : ''}}
        </div>`;

        rows += `<tr style="${{rowBg}}">
            <td class="px-3 py-2 font-semibold text-gray-800 sticky left-0 bg-white z-10" style="${{rowBg}}"><span class="inline-flex items-center gap-1.5">${{r.nombre}}${{badge}}<button onclick="ocultarProy('${{r.nombre.replace(/'/g,"\\\\'")}}')" title="Ocultar proyecto" style="opacity:.25;cursor:pointer;border:none;background:none;padding:2px;line-height:1" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=.25"><svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg></button></span></td>
            <td class="px-2 py-2 text-gray-500">${{r.comuna}}</td>
            <td class="px-2 py-2 text-center font-mono font-semibold">${{r.n_viv}}</td>
            <td class="px-2 py-2 text-center font-mono text-gray-500">${{ff(r.fi)}}</td>
            <td class="px-2 py-2 text-center font-mono text-gray-500">${{ff(r.pd)}}</td>
            <td class="px-2 py-2 text-center font-mono font-semibold">${{r.dur}}d</td>
            <td class="px-2 py-2 text-center font-mono text-gray-500">${{ff(r.fv)}}</td>
            <td class="px-2 py-2 text-center font-mono text-gray-500">${{ff(r.pr)}}</td>
            <td class="px-2 py-2 text-center font-mono font-semibold">${{ff(r.ur)}}</td>
            <td class="px-2 py-2 text-center font-mono ${{recepColor}} font-bold">${{r.nr}}/${{r.n_viv}}</td>
            <td class="px-2 py-2 text-center font-mono">${{r.dc !== null ? r.dc+'d' : '—'}}</td>
            <td class="px-2 py-2 text-center font-mono">${{r.do !== null ? r.do+'d' : '—'}}</td>
            <td class="px-2 py-2 text-center">${{difHtml}}</td>
            <td class="px-3 py-2">${{timeline}}</td>
        </tr>`;
    }});
    document.getElementById('tbody').innerHTML = rows;
}}

render();
renderModal();
</script>
</body></html>"""

    out = Path(__file__).parent.parent / 'dashboard' / 'tiempos_ejecucion.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML generado: {out}")

if __name__ == '__main__':
    generar()

#!/usr/bin/env python3
"""
Generador de Comparador de Proyectos — SCRaices
Compara rendimiento entre residentes (Jairo Alvarez vs Arturo Neira)
Métricas: Ritmo de Avance, Plazos de Ejecución, Ritmo de Despachos
"""

import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))

from data_manager import DataManager
import pandas as pd
import numpy as np

PESOS_VIV = {
    'A_Habilitacion': 0.05, 'A_Fund': 0.06, 'A_Planta_Alc': 0.03, 'A_Radier': 0.04,
    'A_E_Tabiques': 0.06, 'A_E_Techumbre': 0.06, 'A_rev Ext': 0.04, 'A_vent': 0.03,
    'A_Cubierta': 0.04, 'A_Ent_Cielo': 0.03, 'A_ent_alero': 0.02, 'A_Red_AP': 0.04,
    'A_Red_Elect': 0.04, 'A_rev_ZS': 0.03, 'A_rev_ZH': 0.03, 'A_Aisl_Muro': 0.03,
    'A_Aisl_Cielo': 0.03, 'A_Cer_Piso': 0.04, 'A_Cer_muro': 0.03, 'A_pint_Ext': 0.03,
    'A_pint_int': 0.03, 'A_puertas': 0.03, 'A_molduras': 0.02, 'A_Art_Ba\u00f1o': 0.03,
    'A_Art_cocina': 0.03, 'A_Art_Elec': 0.03, 'A_AP_Ext': 0.03, 'A_ALC_Ext': 0.03,
    'A_Ins_Elec_Ext': 0.02
}

def parse_pct(v):
    if pd.isna(v) or v == '': return 0.0
    s = str(v).replace('%', '').strip()
    try: return float(s) / 100.0
    except: return 0.0

def parse_monto(v):
    if pd.isna(v): return 0
    try: return float(str(v).replace('$', '').replace('.', '').replace(',', '.').strip())
    except: return 0

def generar_comparador():
    dm = DataManager()
    benef = dm.get_table_data('Beneficiario')
    desp = dm.get_table_data('Despacho')
    insp = dm.get_table_data('Ejecucion')
    solpago = dm.get_table_data('Solpago')
    proy = dm.get_table_data('Proyectos')

    jairo_pids = proy[proy['Encargado'].str.contains('jalvarez', case=False, na=False)]['ID_proy'].tolist()
    arturo_pids = proy[proy['Encargado'].str.contains('aneira', case=False, na=False)]['ID_proy'].tolist()

    def calc_avance_benef(bid):
        rows = insp[insp['ID_benef'] == bid]
        if len(rows) == 0: return 0.0
        totals = {}
        for col in PESOS_VIV:
            if col in rows.columns:
                totals[col] = sum(parse_pct(v) for v in rows[col])
        avance = sum(totals.get(col, 0) * peso for col, peso in PESOS_VIV.items())
        return max(0.0, min(1.0, avance))

    results = []
    for pid in set(jairo_pids + arturo_pids):
        p_benefs = benef[benef['ID_Proy'] == pid]
        n_viv = len(p_benefs)
        if n_viv < 3: continue

        p_desp = desp[desp['ID_proy'] == pid]
        if len(p_desp) < 5: continue

        p_info = proy[proy['ID_proy'] == pid].iloc[0]
        residente = 'Jairo Alvarez' if pid in jairo_pids else 'Arturo Neira'

        desp_dates = pd.to_datetime(p_desp['Fecha'], errors='coerce').dropna()
        if len(desp_dates) < 2: continue

        fecha_ini = desp_dates.min()
        fecha_fin = desp_dates.max()
        dias = max((fecha_fin - fecha_ini).days, 1)
        n_desp = len(p_desp)

        bids = p_benefs['ID_Benef'].tolist()
        avances = [calc_avance_benef(b) for b in bids]
        avg_avance = float(np.mean(avances)) if avances else 0.0

        por_mes = {}
        for d in desp_dates:
            key = d.strftime('%Y-%m')
            por_mes[key] = por_mes.get(key, 0) + 1

        p_sp = solpago[solpago['ID_Benef'].isin(bids)]
        total_pagado = sum(parse_monto(m) for m in p_sp['Monto']) if len(p_sp) > 0 and 'Monto' in p_sp.columns else 0

        results.append({
            'id': str(pid),
            'nombre': str(p_info.get('NOMBRE_PROYECTO', pid)),
            'comuna': str(p_info.get('COMUNA', '')),
            'residente': residente,
            'n_viv': int(n_viv),
            'n_desp': int(n_desp),
            'dias_activo': int(dias),
            'fecha_ini': str(fecha_ini.date()),
            'fecha_fin': str(fecha_fin.date()),
            'desp_por_mes': round(float(n_desp / (dias / 30.0)), 1),
            'desp_por_viv': round(float(n_desp / n_viv), 1),
            'avg_avance': round(float(avg_avance * 100), 1),
            'por_mes': dict(sorted(por_mes.items())),
            'total_pagado': int(round(total_pagado)),
        })

    results.sort(key=lambda x: (x['residente'], x['id']))

    # Generate HTML
    data_json = json.dumps(results, ensure_ascii=False)
    html = generate_html(data_json)

    output = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'comparador.html')
    output = os.path.normpath(output)
    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Comparador generado: {output}')
    print(f'  {len(results)} proyectos ({len([r for r in results if "Jairo" in r["residente"]])} Jairo, {len([r for r in results if "Arturo" in r["residente"]])} Arturo)')
    return output


def generate_html(data_json):
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SCRaices — Comparador de Proyectos</title>
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg-primary: #0a0f1a;
    --bg-card: #111827;
    --bg-hover: #1f2937;
    --border: #1e293b;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --accent-jairo: #3b82f6;
    --accent-arturo: #f59e0b;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg-primary); color: var(--text-primary); font-family: 'IBM Plex Sans', sans-serif; }}
  .font-mono {{ font-family: 'IBM Plex Mono', monospace; }}
  .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
  .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
  .bar-jairo {{ background: linear-gradient(90deg, #3b82f6, #60a5fa); }}
  .bar-arturo {{ background: linear-gradient(90deg, #f59e0b, #fbbf24); }}
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const {{ useState, useMemo, useCallback }} = React;

const PROJECTS = {data_json};

const JAIRO_COLOR = '#3b82f6';
const ARTURO_COLOR = '#f59e0b';

function formatPeso(n) {{
  if (n >= 1e6) return '$' + (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return '$' + (n/1e3).toFixed(0) + 'K';
  return '$' + n;
}}

// ===== KPI Card =====
function KPI({{ label, jairo, arturo, unit, better }}) {{
  const jVal = typeof jairo === 'number' ? jairo : 0;
  const aVal = typeof arturo === 'number' ? arturo : 0;
  const jWins = better === 'higher' ? jVal >= aVal : jVal <= aVal;
  return (
    <div className="bg-[#111827] rounded-xl p-4 border border-[#1e293b]">
      <div className="text-xs text-slate-400 mb-3 uppercase tracking-wider">{{label}}</div>
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <div className="text-[10px] text-blue-400 mb-1">Jairo</div>
          <div className={{`text-2xl font-bold font-mono ${{jWins ? 'text-blue-400' : 'text-slate-400'}}`}}>
            {{typeof jairo === 'string' ? jairo : jairo?.toFixed?.(1) ?? '-'}}
            <span className="text-xs text-slate-500 ml-1">{{unit}}</span>
          </div>
        </div>
        <div className="flex-1 text-right">
          <div className="text-[10px] text-amber-400 mb-1">Arturo</div>
          <div className={{`text-2xl font-bold font-mono ${{!jWins ? 'text-amber-400' : 'text-slate-400'}}`}}>
            {{typeof arturo === 'string' ? arturo : arturo?.toFixed?.(1) ?? '-'}}
            <span className="text-xs text-slate-500 ml-1">{{unit}}</span>
          </div>
        </div>
      </div>
    </div>
  );
}}

// ===== Bar Chart =====
function BarChart({{ data, metric, label, unit, color }}) {{
  const maxVal = Math.max(...data.map(d => d[metric] || 0), 1);
  return (
    <div className="bg-[#111827] rounded-xl p-4 border border-[#1e293b]">
      <div className="text-xs text-slate-400 mb-3 uppercase tracking-wider">{{label}}</div>
      <div className="space-y-1.5 max-h-[400px] overflow-y-auto hide-scrollbar">
        {{data.map(d => (
          <div key={{d.id}} className="flex items-center gap-2 text-xs">
            <div className="w-12 text-slate-500 font-mono shrink-0">{{d.id}}</div>
            <div className="flex-1 h-5 bg-[#0a0f1a] rounded overflow-hidden relative">
              <div
                className={{`h-full rounded ${{d.residente.includes('Jairo') ? 'bar-jairo' : 'bar-arturo'}}`}}
                style={{{{ width: `${{Math.max((d[metric] / maxVal) * 100, 2)}}%` }}}}
              />
            </div>
            <div className="w-16 text-right font-mono text-slate-300">
              {{typeof d[metric] === 'number' ? (d[metric] % 1 === 0 ? d[metric] : d[metric].toFixed(1)) : d[metric]}}
              {{unit && <span className="text-slate-500 text-[10px] ml-0.5">{{unit}}</span>}}
            </div>
          </div>
        ))}}
      </div>
    </div>
  );
}}

// ===== Timeline Chart (despachos/mes) =====
function TimelineChart({{ jairoProjects, arturoProjects }}) {{
  // Aggregate monthly despachos per resident
  const allMonths = new Set();
  const aggregate = (projects) => {{
    const byMonth = {{}};
    projects.forEach(p => {{
      Object.entries(p.por_mes).forEach(([m, count]) => {{
        allMonths.add(m);
        byMonth[m] = (byMonth[m] || 0) + count;
      }});
    }});
    return byMonth;
  }};

  const jByMonth = aggregate(jairoProjects);
  const aByMonth = aggregate(arturoProjects);
  const months = [...allMonths].sort();

  // Show last 24 months
  const recentMonths = months.slice(-24);
  const maxVal = Math.max(
    ...recentMonths.map(m => Math.max(jByMonth[m] || 0, aByMonth[m] || 0)),
    1
  );

  return (
    <div className="bg-[#111827] rounded-xl p-4 border border-[#1e293b]">
      <div className="text-xs text-slate-400 mb-3 uppercase tracking-wider">Despachos por Mes (agregado)</div>
      <div className="flex items-end gap-[2px] h-48 overflow-x-auto hide-scrollbar">
        {{recentMonths.map(m => {{
          const jH = ((jByMonth[m] || 0) / maxVal) * 100;
          const aH = ((aByMonth[m] || 0) / maxVal) * 100;
          return (
            <div key={{m}} className="flex flex-col items-center gap-0.5 min-w-[20px] flex-1 h-full justify-end group relative">
              <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 px-2 py-1 rounded text-[10px] whitespace-nowrap hidden group-hover:block z-10 border border-slate-700">
                {{m}}: J={{jByMonth[m]||0}} A={{aByMonth[m]||0}}
              </div>
              <div className="flex gap-[1px] items-end flex-1 w-full">
                <div className="flex-1 bar-jairo rounded-t" style={{{{ height: `${{Math.max(jH, 1)}}%` }}}} />
                <div className="flex-1 bar-arturo rounded-t" style={{{{ height: `${{Math.max(aH, 1)}}%` }}}} />
              </div>
              <div className="text-[8px] text-slate-600 -rotate-45 origin-top-left w-[30px]">
                {{m.slice(2)}}
              </div>
            </div>
          );
        }})}}
      </div>
    </div>
  );
}}

// ===== Project Table =====
function ProjectTable({{ projects, sortBy, onSort }}) {{
  const sorted = [...projects].sort((a, b) => {{
    const dir = sortBy.dir === 'asc' ? 1 : -1;
    return ((a[sortBy.key] || 0) - (b[sortBy.key] || 0)) * dir;
  }});

  const cols = [
    {{ key: 'id', label: 'Proy', w: 'w-14' }},
    {{ key: 'residente', label: 'Residente', w: 'w-24' }},
    {{ key: 'n_viv', label: 'Viv', w: 'w-10' }},
    {{ key: 'n_desp', label: 'Desp', w: 'w-12' }},
    {{ key: 'desp_por_mes', label: 'D/Mes', w: 'w-14' }},
    {{ key: 'desp_por_viv', label: 'D/Viv', w: 'w-14' }},
    {{ key: 'avg_avance', label: 'Avance', w: 'w-16' }},
    {{ key: 'dias_activo', label: 'Dias', w: 'w-14' }},
    {{ key: 'total_pagado', label: 'Pagado', w: 'w-20' }},
  ];

  return (
    <div className="bg-[#111827] rounded-xl border border-[#1e293b] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-[#0f172a]">
              {{cols.map(c => (
                <th key={{c.key}}
                    className={{`px-3 py-2.5 text-left text-slate-400 font-medium cursor-pointer hover:text-slate-200 ${{c.w}}`}}
                    onClick={{() => onSort(c.key)}}>
                  {{c.label}}
                  {{sortBy.key === c.key && <span className="ml-1">{{sortBy.dir === 'asc' ? '\u25B2' : '\u25BC'}}</span>}}
                </th>
              ))}}
            </tr>
          </thead>
          <tbody>
            {{sorted.map(p => (
              <tr key={{p.id}} className="border-t border-[#1e293b] hover:bg-[#1f2937] transition-colors">
                <td className="px-3 py-2 font-mono font-bold">{{p.id}}</td>
                <td className="px-3 py-2">
                  <span className={{`inline-block w-2 h-2 rounded-full mr-1.5 ${{p.residente.includes('Jairo') ? 'bg-blue-500' : 'bg-amber-500'}}`}} />
                  {{p.residente.split(' ')[0]}}
                </td>
                <td className="px-3 py-2 font-mono">{{p.n_viv}}</td>
                <td className="px-3 py-2 font-mono">{{p.n_desp}}</td>
                <td className="px-3 py-2 font-mono">{{p.desp_por_mes}}</td>
                <td className="px-3 py-2 font-mono">{{p.desp_por_viv}}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-16 h-2 bg-[#0a0f1a] rounded-full overflow-hidden">
                      <div className={{`h-full rounded-full ${{p.avg_avance >= 100 ? 'bg-emerald-500' : p.avg_avance >= 50 ? 'bg-blue-500' : 'bg-amber-500'}}`}}
                           style={{{{ width: `${{Math.min(p.avg_avance, 100)}}%` }}}} />
                    </div>
                    <span className="font-mono">{{p.avg_avance}}%</span>
                  </div>
                </td>
                <td className="px-3 py-2 font-mono">{{p.dias_activo}}</td>
                <td className="px-3 py-2 font-mono text-slate-400">{{formatPeso(p.total_pagado)}}</td>
              </tr>
            ))}}
          </tbody>
        </table>
      </div>
    </div>
  );
}}

// ===== Scatter Plot =====
function ScatterPlot({{ projects, xKey, yKey, xLabel, yLabel }}) {{
  const padding = 40;
  const w = 600, h = 300;
  const xVals = projects.map(p => p[xKey] || 0);
  const yVals = projects.map(p => p[yKey] || 0);
  const xMax = Math.max(...xVals, 1);
  const yMax = Math.max(...yVals, 1);

  return (
    <div className="bg-[#111827] rounded-xl p-4 border border-[#1e293b]">
      <div className="text-xs text-slate-400 mb-3 uppercase tracking-wider">
        {{xLabel}} vs {{yLabel}}
      </div>
      <svg viewBox={{`0 0 ${{w + padding*2}} ${{h + padding*2}}`}} className="w-full">
        {{/* Axes */}}
        <line x1={{padding}} y1={{h+padding}} x2={{w+padding}} y2={{h+padding}} stroke="#334155" strokeWidth="1"/>
        <line x1={{padding}} y1={{padding}} x2={{padding}} y2={{h+padding}} stroke="#334155" strokeWidth="1"/>
        {{/* Labels */}}
        <text x={{w/2+padding}} y={{h+padding+30}} fill="#64748b" fontSize="11" textAnchor="middle">{{xLabel}}</text>
        <text x={{12}} y={{h/2+padding}} fill="#64748b" fontSize="11" textAnchor="middle" transform={{`rotate(-90, 12, ${{h/2+padding}})`}}>{{yLabel}}</text>
        {{/* Grid */}}
        {{[0.25, 0.5, 0.75, 1].map(frac => (
          <g key={{frac}}>
            <line x1={{padding}} y1={{h+padding - h*frac}} x2={{w+padding}} y2={{h+padding - h*frac}} stroke="#1e293b" strokeWidth="0.5"/>
            <text x={{padding-5}} y={{h+padding - h*frac + 4}} fill="#475569" fontSize="9" textAnchor="end">{{(yMax*frac).toFixed(0)}}</text>
          </g>
        ))}}
        {{[0.25, 0.5, 0.75, 1].map(frac => (
          <g key={{frac}}>
            <line x1={{padding + w*frac}} y1={{padding}} x2={{padding + w*frac}} y2={{h+padding}} stroke="#1e293b" strokeWidth="0.5"/>
            <text x={{padding + w*frac}} y={{h+padding+14}} fill="#475569" fontSize="9" textAnchor="middle">{{(xMax*frac).toFixed(0)}}</text>
          </g>
        ))}}
        {{/* Points */}}
        {{projects.map(p => {{
          const cx = padding + (p[xKey] / xMax) * w;
          const cy = h + padding - (p[yKey] / yMax) * h;
          const isJairo = p.residente.includes('Jairo');
          return (
            <g key={{p.id}}>
              <circle cx={{cx}} cy={{cy}} r={{5 + p.n_viv * 0.3}}
                fill={{isJairo ? '#3b82f680' : '#f59e0b80'}}
                stroke={{isJairo ? '#3b82f6' : '#f59e0b'}}
                strokeWidth="1.5"/>
              <text x={{cx}} y={{cy - 8}} fill="#94a3b8" fontSize="9" textAnchor="middle">{{p.id}}</text>
            </g>
          );
        }})}}
      </svg>
    </div>
  );
}}

// ===== App =====
function App() {{
  const [filter, setFilter] = useState('all');
  const [sortBy, setSortBy] = useState({{ key: 'desp_por_mes', dir: 'desc' }});

  const filtered = useMemo(() => {{
    if (filter === 'jairo') return PROJECTS.filter(p => p.residente.includes('Jairo'));
    if (filter === 'arturo') return PROJECTS.filter(p => p.residente.includes('Arturo'));
    return PROJECTS;
  }}, [filter]);

  const jairoProjects = PROJECTS.filter(p => p.residente.includes('Jairo'));
  const arturoProjects = PROJECTS.filter(p => p.residente.includes('Arturo'));

  // Aggregate KPIs
  const avg = (arr, key) => arr.length ? arr.reduce((s, p) => s + (p[key]||0), 0) / arr.length : 0;

  const handleSort = useCallback((key) => {{
    setSortBy(prev => ({{ key, dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc' }}));
  }}, []);

  return (
    <div className="min-h-screen p-4 md:p-6 max-w-7xl mx-auto">
      {{/* Header */}}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-slate-500 font-mono text-sm mr-2">SC</span>
            Comparador de Proyectos
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            {{PROJECTS.length}} proyectos | Jairo Alvarez vs Arturo Neira
          </p>
        </div>
        <div className="flex gap-1.5 text-xs">
          {{['all', 'jairo', 'arturo'].map(f => (
            <button key={{f}}
              onClick={{() => setFilter(f)}}
              className={{`px-3 py-1.5 rounded-lg transition-colors ${{
                filter === f
                  ? f === 'jairo' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : f === 'arturo' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'bg-slate-700 text-slate-200 border border-slate-600'
                  : 'bg-[#111827] text-slate-400 border border-[#1e293b] hover:border-slate-600'
              }}`}}>
              {{f === 'all' ? 'Todos' : f === 'jairo' ? 'Jairo' : 'Arturo'}}
            </button>
          ))}}
        </div>
      </div>

      {{/* Legend */}}
      <div className="flex gap-6 mb-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-blue-500"/> Jairo Alvarez ({{jairoProjects.length}} proy)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-amber-500"/> Arturo Neira ({{arturoProjects.length}} proy)
        </span>
      </div>

      {{/* KPIs */}}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <KPI label="Despachos/Mes (prom)" jairo={{avg(jairoProjects, 'desp_por_mes')}} arturo={{avg(arturoProjects, 'desp_por_mes')}} unit="d/m" better="higher"/>
        <KPI label="Despachos/Vivienda" jairo={{avg(jairoProjects, 'desp_por_viv')}} arturo={{avg(arturoProjects, 'desp_por_viv')}} unit="d/v" better="higher"/>
        <KPI label="Avance Promedio" jairo={{avg(jairoProjects, 'avg_avance')}} arturo={{avg(arturoProjects, 'avg_avance')}} unit="%" better="higher"/>
        <KPI label="Dias Activo (prom)" jairo={{avg(jairoProjects, 'dias_activo')}} arturo={{avg(arturoProjects, 'dias_activo')}} unit="d" better="lower"/>
      </div>

      {{/* Charts Row 1 */}}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <BarChart data={{filtered}} metric="desp_por_mes" label="Ritmo de Despachos (por mes)" unit="d/m"/>
        <BarChart data={{filtered}} metric="avg_avance" label="Avance Inspeccion (%)" unit="%"/>
      </div>

      {{/* Charts Row 2 */}}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <ScatterPlot projects={{filtered}} xKey="dias_activo" yKey="desp_por_mes" xLabel="Dias Activo" yLabel="Despachos/Mes"/>
        <ScatterPlot projects={{filtered}} xKey="n_viv" yKey="avg_avance" xLabel="Viviendas" yLabel="Avance %"/>
      </div>

      {{/* Timeline */}}
      <div className="mb-4">
        <TimelineChart jairoProjects={{jairoProjects}} arturoProjects={{arturoProjects}} />
      </div>

      {{/* Table */}}
      <ProjectTable projects={{filtered}} sortBy={{sortBy}} onSort={{handleSort}} />

      {{/* Footer */}}
      <div className="text-center text-[10px] text-slate-600 mt-6 font-mono">
        SCRaices Comparador v1.0 | Generado {{new Date().toLocaleDateString('es-CL')}}
      </div>
    </div>
  );
}}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>'''


if __name__ == '__main__':
    output = generar_comparador()
    import subprocess
    subprocess.Popen(['powershell', '-Command', f"Start-Process '{output}'"])

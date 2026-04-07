"""
Panel Coordinador de Obras - Vista multi-proyecto
Genera un HTML standalone con resumen de todos los proyectos en ejecucion.
Output: dashboard/panel_coordinador.html
"""
import sys
sys.path.insert(0, '.')
import json
from datetime import datetime, timedelta
from data_manager import DataManager
from pathlib import Path
import pandas as pd

PESOS_VIV = {
    'A_Fund': 0.02, 'A_Radier': 0.04, 'A_Planta_Alc': 0.01,
    'A_E_Tabiques': 0.06, 'A_E_Techumbre': 0.04, 'A_rev Ext': 0.06,
    'A_vent': 0.03, 'A_Cubierta': 0.03, 'A_Ent_Cielo': 0.02,
    'A_ent_alero': 0.02, 'A_Red_AP': 0.03, 'A_Red_Elect': 0.04,
    'A_rev_ZS': 0.04, 'A_rev_ZH': 0.02, 'A_Aisl_Muro': 0.04,
    'A_Aisl_Cielo': 0.03, 'A_Cer_Piso': 0.05, 'A_Cer_muro': 0.03,
    'A_pint_Ext': 0.04, 'A_pint_int': 0.02, 'A_puertas': 0.05,
    'A_molduras': 0.02, 'A_Art_Baño': 0.05, 'A_Art_cocina': 0.02,
    'A_Art_Elec': 0.04, 'A_AP_Ext': 0.05, 'A_ALC_Ext': 0.05,
    'A_Ins_Elec_Ext': 0.05
}

SECUENCIA_PRINCIPAL = [
    "01_FUNDACIONES", "12_ALCANTARILLADO", "02_1ERA_ETAPA", "28_VENTANAS",
    "29_EIFS", "03_2DA_ETAPA", "13_GASFITERIA", "07_CERAMICO_PISO",
    "08_CERAMICO_MURO", "09_PINTURA_EXT", "10_PINTURA_INT", "14_OBRAS_EXT"
]

FAMILIA_ETAPAS = {
    "Fundaciones": ["01_FUNDACIONES", "12_ALCANTARILLADO"],
    "1era Etapa": ["02_1ERA_ETAPA", "28_VENTANAS", "29_EIFS"],
    "2da Etapa": ["03_2DA_ETAPA"],
    "Gasfiteria": ["13_GASFITERIA"],
    "Ceramica": ["07_CERAMICO_PISO", "08_CERAMICO_MURO"],
    "Pintura": ["09_PINTURA_EXT", "10_PINTURA_INT"],
    "Obras Ext.": ["14_OBRAS_EXT"]
}

def mapear_segmento(seg):
    """Mapea un segmento de Tipo_despacho al codigo de etapa (misma logica que dashboard v3)"""
    t = seg.lower().strip()
    if 'fundacion' in t and 'eifs' not in t and 'aislacion' not in t: return '01_FUNDACIONES'
    if 'alcantarillado' in t: return '12_ALCANTARILLADO'
    if '1era' in t: return '02_1ERA_ETAPA'
    if 'ventana' in t: return '28_VENTANAS'
    if 'eifs' in t or 'aislacion fund' in t: return '29_EIFS'
    if '2da' in t: return '03_2DA_ETAPA'
    if 'piso' in t and 'ceram' in t: return '07_CERAMICO_PISO'
    if '07-' in t and 'piso' in t: return '07_CERAMICO_PISO'
    if 'muro' in t and 'ceram' in t: return '08_CERAMICO_MURO'
    if '08-' in t and 'muro' in t: return '08_CERAMICO_MURO'
    if 'pintura ext' in t or '09-' in t: return '09_PINTURA_EXT'
    if 'pintura int' in t or '10-' in t: return '10_PINTURA_INT'
    if 'pintura' in t and 'r.c' in t: return '09_PINTURA_EXT'
    if 'gasfiter' in t or 'sol. ac' in t or 'artefact' in t or 'cocina' in t or 'calefont' in t: return '13_GASFITERIA'
    if 'obra' in t and 'ext' in t: return '14_OBRAS_EXT'
    if 'ap ext' in t or '05-' in t: return '14_OBRAS_EXT'
    return None

def mapear_tipo_despacho(tipo):
    """Mapea un Tipo_despacho completo (puede contener multiples etapas separadas por coma)"""
    if not tipo or str(tipo) in ['nan', '', 'None']:
        return set()
    etapas = set()
    for seg in str(tipo).split(','):
        key = mapear_segmento(seg)
        if key:
            etapas.add(key)
    return etapas

def _to_float(val):
    if pd.isna(val) or val == '' or val is None:
        return 0.0
    s = str(val).strip().replace('%', '').replace(',', '.').strip()
    try:
        return float(s) / 100.0
    except:
        return 0.0

def parse_monto(val):
    if pd.isna(val) or val == '' or val is None:
        return 0
    s = str(val).strip().replace('$', '').replace('.', '').replace(',', '.')
    try:
        return int(float(s))
    except:
        return 0

def parse_fecha(fecha_str):
    if not fecha_str or str(fecha_str) in ['nan', 'NaT', '', 'None']:
        return None
    for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(str(fecha_str).split()[0], fmt)
        except:
            pass
    return None


def generar_panel():
    print("=" * 60)
    print("PANEL COORDINADOR DE OBRAS")
    print("=" * 60)
    dm = DataManager()
    proyectos = dm.get_table_data('Proyectos')
    beneficiarios = dm.get_table_data('Beneficiario')
    despachos = dm.get_table_data('Despacho')
    solicitudes = dm.get_table_data('soldepacho')
    ejecucion = dm.get_table_data('Ejecucion')
    solpago = dm.get_table_data('Solpago')
    control_bgb = dm.get_table_data('controlBGB')
    documentacion = dm.get_table_data('documentacion')
    control_eepp_raw = dm.conn.spreadsheet.worksheet('controlEEPP').get_all_values()
    eepp_headers = control_eepp_raw[0] if control_eepp_raw else []
    eepp_rows = [dict(zip(eepp_headers, r + ['']*(len(eepp_headers)-len(r)))) for r in control_eepp_raw[1:]]

    # Filtrar proyectos en ejecucion (misma regla que dashboard v3)
    proyectos_ej_raw = proyectos[proyectos['estado_general'].str.lower().str.contains('ejecuci', na=False)].copy()
    print(f"Proyectos en ejecucion (tabla): {len(proyectos_ej_raw)}")

    # Excluir finalizados por recepciones completas (F_R_dom)
    def pf_check(f):
        if not f or str(f) in ['nan','NaT','','None']: return False
        return True

    finalizados_recep = set()
    for _, pr in proyectos_ej_raw.iterrows():
        pid = str(pr['ID_proy'])
        bens_p = beneficiarios[beneficiarios['ID_Proy'].astype(str) == pid]
        if len(bens_p) == 0:
            continue
        con_recep = sum(1 for _, b in bens_p.iterrows() if pf_check(b.get('F_R_dom', '')))
        if con_recep == len(bens_p):
            finalizados_recep.add(pid)

    proyectos_ej = proyectos_ej_raw[~proyectos_ej_raw['ID_proy'].astype(str).isin(finalizados_recep)].copy()
    if finalizados_recep:
        print(f"  Excluidos por recepciones completas: {len(finalizados_recep)}")
    print(f"Proyectos activos (sin finalizados): {len(proyectos_ej)}")
    hoy = datetime.now()

    pesos = dict(PESOS_VIV)
    if 'A_Art_Baño' not in ejecucion.columns and 'A_Art_Bano' in ejecucion.columns:
        pesos['A_Art_Bano'] = pesos.pop('A_Art_Baño')
    viv_cols = [c for c in pesos.keys() if c in ejecucion.columns]
    rc_cols = [c for c in ejecucion.columns if c.startswith('AB_')]
    hab_col = 'A_Habilitacion' if 'A_Habilitacion' in ejecucion.columns else None
    all_insp = viv_cols + rc_cols + ([hab_col] if hab_col else [])
    for col in all_insp:
        ejecucion[col] = ejecucion[col].apply(_to_float)

    # Determinar que beneficiarios tienen RC
    benef_con_rc = set()
    for _, b in beneficiarios.iterrows():
        tip_rc = str(b.get('Tipologia RC', '')).strip().lower()
        if tip_rc not in ['nan', '', 'none']:
            benef_con_rc.add(str(b['ID_Benef']))

    # Beneficiarios con TE1 subido
    benef_con_te1 = set()
    for _, dd in documentacion.iterrows():
        if 'documentacion_' in str(dd.get('T1', '')):
            benef_con_te1.add(str(dd.get('ID_benef', '')))

    # Linea critica: Fundaciones + 1era Etapa + 2da Etapa + Gasfiteria + Ceramica
    # Cuando todas estan despachadas, la vivienda tiene lo medular y falta solo cierre
    LINEA_CRITICA = [
        "01_FUNDACIONES", "12_ALCANTARILLADO",     # Fundaciones
        "02_1ERA_ETAPA", "28_VENTANAS", "29_EIFS",  # 1era Etapa
        "03_2DA_ETAPA",                              # 2da Etapa
        "13_GASFITERIA",                             # Gasfiteria
        "07_CERAMICO_PISO", "08_CERAMICO_MURO"       # Ceramica
    ]

    def get_insp(id_b):
        eb = ejecucion[ejecucion['ID_benef'].astype(str) == str(id_b)]
        if len(eb) == 0: return None
        acum = eb[all_insp].sum()
        pv = sum(min(max(acum.get(c,0),0),1)*w for c,w in pesos.items() if c in acum.index)
        tiene_rc = str(id_b) in benef_con_rc
        if tiene_rc:
            rv = [min(max(acum.get(c,0),0),1) for c in rc_cols if c in acum.index]
            pr = sum(rv)/len(rv) if rv else 0
        else:
            pr = 0
        hv = min(max(acum.get(hab_col,0),0),1) if hab_col else 0
        if tiene_rc:
            return round((pv*0.7 + pr*0.25 + hv*0.05)*100, 1)
        else:
            # Sin RC: Viv pesa 95%, Hab 5%
            return round((pv*0.95 + hv*0.05)*100, 1)

    solpago_ok = solpago[solpago['Estado'].astype(str).str.lower().str.contains('aprobad', na=False)]
    panel_data = []
    gs = {'total_viv':0,'terminadas':0,'en_tiempo':0,'atencion':0,'criticas':0,'sin_despacho':0,
          'total_pagado':0,'total_solicitudes':0,'contratos_90d':0,'contratos_vencidos':0,
          'etapas_global':{f:{'d':0,'t':0} for f in FAMILIA_ETAPAS}}
    alertas_g = []

    for _, p in proyectos_ej.iterrows():
        pid = str(p.get('ID_proy',''))
        nombre = str(p.get('NOMBRE_PROYECTO',''))
        comuna = str(p.get('COMUNA',''))
        fi_dt = parse_fecha(p.get('fecha_inicio',''))
        dur = 0
        try: dur = int(float(str(p.get('duracion','0'))))
        except: pass
        fi_iso = fi_dt.strftime('%Y-%m-%d') if fi_dt else ''
        venc_iso, dias_r, dias_t, pct_p = '', None, 0, 0
        if fi_dt and dur > 0:
            vd = fi_dt + timedelta(days=dur)
            venc_iso = vd.strftime('%Y-%m-%d')
            dias_r = (vd - hoy).days
            dias_t = max(0, (hoy - fi_dt).days)
            pct_p = min(100, max(0, round(dias_t/dur*100)))

        benefs = beneficiarios[beneficiarios['ID_Proy'].astype(str) == pid]
        ids_b = set(benefs['ID_Benef'].astype(str).values)
        nv = len(benefs)
        if nv == 0: continue

        dp = despachos[despachos['ID_Benef'].astype(str).isin(ids_b)]
        sp = solicitudes[solicitudes['ID_Benef'].astype(str).isin(ids_b)]
        term,ent,atc,crit,sind,tpag,solp = 0,0,0,0,0,0,0
        n_hpc, n_te1, n_recep, n_ecrit = 0, 0, 0, 0
        nombres_crit = []
        dias_list, desp_pcts, insp_vals = [],[],[]
        et_proy = {f:{'d':0,'t':0} for f in FAMILIA_ETAPAS}

        for _, b in benefs.iterrows():
            ib = str(b.get('ID_Benef',''))
            # HPC
            hpc_raw = str(b.get('Habil para construir', '')).strip().upper()
            if hpc_raw == 'TRUE': n_hpc += 1
            # TE1
            if ib in benef_con_te1: n_te1 += 1
            # Recepcion definitiva
            frd = str(b.get('F_R_dom', '')).strip()
            if frd and frd.lower() not in ['nan', '', 'nat', 'none']: n_recep += 1

            db = dp[dp['ID_Benef'].astype(str)==ib]
            # Mapear despachos a etapas (misma logica que dashboard v3)
            ed = set()
            for _, dd in db.iterrows():
                ed.update(mapear_tipo_despacho(dd.get('Tipo_despacho', '')))
            # Linea critica completa (todo lo medular despachado, falta solo cierre)
            if all(ec in ed for ec in LINEA_CRITICA): n_ecrit += 1
            ed_seq = ed & set(SECUENCIA_PRINCIPAL)
            nd = len(ed_seq)
            nt = len(SECUENCIA_PRINCIPAL)
            desp_pcts.append(round(nd/nt*100) if nt>0 else 0)
            sb = sp[sp['ID_Benef'].astype(str)==ib]
            for _, s in sb.iterrows():
                sol_etapas = mapear_tipo_despacho(s.get('Tipo_despacho',''))
                for se in sol_etapas:
                    if se in SECUENCIA_PRINCIPAL and se not in ed_seq: solp += 1
            ip = get_insp(ib)
            if ip is not None: insp_vals.append(ip)
            pb = solpago_ok[solpago_ok['ID_Benef'].astype(str)==ib]
            tpag += sum(parse_monto(m) for m in pb['monto'].values) if len(pb)>0 else 0
            fds = [parse_fecha(d.get('Fecha','')) for _,d in db.iterrows()]
            fds = [f for f in fds if f]
            if len(fds)>=2: dias_list.append((max(fds)-min(fds)).days)
            if nd==nt and ip is not None and ip>=90: term += 1
            elif nd==0: sind += 1
            else:
                if fds:
                    dd = (hoy-max(fds)).days
                    if dd>21:
                        crit+=1
                        nom_b = f"{b.get('NOMBRES','')} {b.get('APELLIDOS','')}".strip()
                        nombres_crit.append(nom_b)
                    elif dd>7: atc+=1
                    else: ent+=1
                else: ent+=1
            for f,ets in FAMILIA_ETAPAS.items():
                for e in ets:
                    et_proy[f]['t']+=1; gs['etapas_global'][f]['t']+=1
                    if e in ed: et_proy[f]['d']+=1; gs['etapas_global'][f]['d']+=1

        avd = round(sum(desp_pcts)/len(desp_pcts)) if desp_pcts else 0
        avi = round(sum(insp_vals)/len(insp_vals)) if insp_vals else 0
        dpr = round(sum(dias_list)/len(dias_list)) if dias_list else 0
        delta = avd - pct_p

        gp = control_bgb[control_bgb['ID_proy'].astype(str)==pid] if 'ID_proy' in control_bgb.columns else pd.DataFrame()
        gpv = sum(1 for _,g in gp.iterrows() if parse_fecha(g.get('Fecha_vcmto','')) and 0<=(parse_fecha(g.get('Fecha_vcmto',''))-hoy).days<60)

        ep = [e for e in eepp_rows if str(e.get('ID_proy',''))==pid]
        epp,ept = 0,0
        for e in ep:
            try: mu=float(str(e.get('monto_ep','0')).replace(',','.').replace(' ',''))
            except: mu=0
            ept+=mu
            if 'pagad' in str(e.get('estado_ep','')).lower(): epp+=mu

        als = []
        if dias_r is not None and dias_r<0:
            als.append({'tipo':'danger','msg':f'CONTRATO VENCIDO hace {abs(dias_r)} dias'}); gs['contratos_vencidos']+=1
        elif dias_r is not None and dias_r<=90:
            als.append({'tipo':'danger','msg':f'Fase cierre EGR — {dias_r}d para vencimiento'}); gs['contratos_90d']+=1
        if crit>0: als.append({'tipo':'warn','msg':f'{crit} vivienda{"s" if crit>1 else ""} critica{"s" if crit>1 else ""}'})
        if gpv>0: als.append({'tipo':'info','msg':f'{gpv} garantia{"s" if gpv>1 else ""} por vencer (<60d)'})
        if solp>5: als.append({'tipo':'warn','msg':f'{solp} solicitudes esperando despacho'})

        if dias_r is not None and dias_r<0: alertas_g.append({'proy':nombre,'tipo':'danger','msg':f'Contrato vencido hace {abs(dias_r)} dias','u':0})
        elif dias_r is not None and dias_r<=90: alertas_g.append({'proy':nombre,'tipo':'danger','msg':f'Fase cierre EGR activa ({dias_r}d)','u':1})
        if crit>=3: alertas_g.append({'proy':nombre,'tipo':'warn','msg':f'{crit} viviendas criticas','u':2})
        if gpv>0: alertas_g.append({'proy':nombre,'tipo':'info','msg':f'{gpv} garantias vencen en <60d','u':3})

        # Semaforo: rojo si vencido o >3 criticas, amarillo si <90d o criticas>0 o delta<-10, verde el resto
        if (dias_r is not None and dias_r < 0) or crit >= 3:
            semaforo = 'rojo'
        elif (dias_r is not None and dias_r <= 90) or crit > 0 or delta < -10:
            semaforo = 'amarillo'
        else:
            semaforo = 'verde'

        panel_data.append({'id':pid,'nombre':nombre,'comuna':comuna,'n_viv':nv,
            'fi':fi_iso,'dur':dur,'venc':venc_iso,'dr':dias_r,'dt':dias_t,'pp':pct_p,
            'term':term,'ent':ent,'atc':atc,'crit':crit,'sind':sind,
            'avd':avd,'avi':avi,'tpag':tpag,'dpr':dpr,'sol':solp,'delta':delta,'als':als,
            'epp':round(epp,2),'ept':round(ept,2),
            'n_hpc':n_hpc,'n_te1':n_te1,'n_recep':n_recep,'n_ecrit':n_ecrit,'semaforo':semaforo,
            'nombres_crit':nombres_crit})
        gs['total_viv']+=nv; gs['terminadas']+=term; gs['en_tiempo']+=ent
        gs['atencion']+=atc; gs['criticas']+=crit; gs['sin_despacho']+=sind
        gs['total_pagado']+=tpag; gs['total_solicitudes']+=solp

    # Orden: por fecha inicio descendente (mas recientes primero), mismo que dashboard v3
    panel_data.sort(key=lambda p: p['fi'] if p['fi'] else '', reverse=True)
    alertas_g.sort(key=lambda a:a['u'])
    print(f"Proyectos: {len(panel_data)}, Viviendas: {gs['total_viv']}")
    html = gen_html(panel_data, gs, alertas_g)
    out = Path(__file__).parent.parent / 'dashboard' / 'panel_coordinador.html'
    with open(out, 'w', encoding='utf-8') as f: f.write(html)
    print(f"Panel generado: {out}")


def gen_html(pd_list, gs, alg):
    hoy_s = datetime.now().strftime('%d/%m/%Y %H:%M')
    data_json = json.dumps(pd_list, ensure_ascii=False)
    alertas_json = json.dumps(alg, ensure_ascii=False)
    etapas_json = json.dumps(gs.get('etapas_global', {}), ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Panel Coordinador — SCRaices</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
body{{font-family:'IBM Plex Sans',sans-serif}}
.mono,.font-mono{{font-family:'IBM Plex Mono',monospace}}
.pc{{background:white;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);transition:all .2s}}
.pc:hover{{box-shadow:0 4px 12px rgba(0,0,0,.1)}}
.pc.hidden-proj{{opacity:.35;order:999}}
.pb{{font-size:9px;font-weight:700;padding:3px 8px;border-radius:6px;white-space:nowrap}}
.ac{{font-size:9px;font-weight:600;padding:2px 8px;border-radius:4px}}
.ac-danger{{background:#fee2e2;color:#991b1b}}.ac-warn{{background:#fef3c7;color:#92400e}}.ac-info{{background:#e0e7ff;color:#3730a3}}
.btn-hide{{cursor:pointer;transition:all .15s}}
.btn-hide:hover{{background:#f1f5f9}}
.modal-bg{{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:100;display:none;align-items:center;justify-content:center}}
.modal-bg.show{{display:flex}}
.modal-box{{background:white;border-radius:16px;width:480px;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.2)}}
</style>
</head><body class="bg-gray-50 text-gray-800">

<div class="bg-slate-900 text-white px-6 py-3 flex items-center justify-between sticky top-0 z-50">
<div class="font-bold text-lg tracking-tight"><span class="text-indigo-400">SC</span> Panel Coordinador</div>
<div class="flex items-center gap-4">
<button id="btnOcultos" onclick="toggleModal()" class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-gray-300 transition cursor-pointer border border-slate-700">
<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg>
<span id="txtOcultos">0 ocultos</span>
</button>
<div class="flex items-center gap-4 text-xs text-gray-400"><span id="txtProyCount">{len(pd_list)} proyectos</span><span>&middot;</span><span>Generado: {hoy_s}</span></div>
</div></div>

<!-- Modal gestionar ocultos -->
<div id="modalOcultos" class="modal-bg" onclick="if(event.target===this)toggleModal()">
<div class="modal-box">
<div class="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
<h3 class="font-bold text-sm">Gestionar Proyectos Ocultos</h3>
<button onclick="toggleModal()" class="text-gray-400 hover:text-gray-600 text-lg cursor-pointer">&times;</button>
</div>
<div id="modalBody" class="p-5"></div>
<div class="px-5 py-3 border-t border-gray-100 flex justify-between">
<button onclick="mostrarTodos()" class="text-xs text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer">Mostrar todos</button>
<button onclick="toggleModal()" class="px-4 py-1.5 bg-slate-900 text-white text-xs rounded-lg hover:bg-slate-800 cursor-pointer">Cerrar</button>
</div>
</div>
</div>

<div class="max-w-[1400px] mx-auto px-5 py-5">
<div id="kpiStrip" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5"></div>
<div class="flex items-center gap-2 mb-3"><div class="w-1 h-4 bg-indigo-500 rounded"></div><span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Proyectos en Ejecucion</span></div>
<div id="cardsGrid" class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4 mb-6"></div>
<div class="flex items-center gap-2 mb-3"><div class="w-1 h-4 bg-indigo-500 rounded"></div><span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Ranking Avance vs Plazo</span></div>
<div id="rankingTable" class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto mb-6"></div>
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
<div id="alertasBox" class="bg-white rounded-xl border border-gray-200 shadow-sm p-4"></div>
<div id="etapasBox" class="bg-white rounded-xl border border-gray-200 shadow-sm p-4"></div>
</div>
</div>

<script>
const ALL_DATA = {data_json};
const ALL_ALERTAS = {alertas_json};
const ETAPAS_GLOBAL = {etapas_json};
const LS_KEY = 'scraices_panel_ocultos';

function getOcultos() {{
  try {{ return JSON.parse(localStorage.getItem(LS_KEY)) || []; }}
  catch {{ return []; }}
}}
function setOcultos(ids) {{
  localStorage.setItem(LS_KEY, JSON.stringify(ids));
  render();
}}
function toggleOculto(pid) {{
  const oc = getOcultos();
  const idx = oc.indexOf(pid);
  if (idx >= 0) oc.splice(idx, 1); else oc.push(pid);
  setOcultos(oc);
}}
function mostrarTodos() {{
  setOcultos([]);
  renderModal();
}}

function fp(n) {{
  if (n >= 1e9) return '$' + (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return '$' + Math.round(n/1e6) + 'M';
  return '$' + n.toLocaleString('es-CL', {{maximumFractionDigits:0}});
}}
function fpf(n) {{ return '$' + n.toLocaleString('es-CL', {{maximumFractionDigits:0}}); }}
function ff(iso) {{
  if (!iso) return '\u2014';
  const p = iso.split('-');
  return p.length === 3 ? p[2]+'/'+p[1]+'/'+p[0] : iso;
}}
function bc(pct) {{
  if (pct >= 100) return '#ef4444';
  if (pct >= 80) return '#f59e0b';
  if (pct >= 50) return '#3b82f6';
  return '#22c55e';
}}

function render() {{
  const ocultos = getOcultos();
  const visibles = ALL_DATA.filter(p => !ocultos.includes(p.id));
  const nOc = ocultos.length;

  document.getElementById('txtOcultos').textContent = nOc + ' oculto' + (nOc !== 1 ? 's' : '');
  document.getElementById('btnOcultos').style.borderColor = nOc > 0 ? '#f59e0b' : '';
  document.getElementById('txtProyCount').textContent = visibles.length + ' proyectos';

  // KPIs
  const gs = {{total_viv:0,terminadas:0,en_tiempo:0,atencion:0,criticas:0,sin_despacho:0,total_pagado:0,contratos_90d:0,contratos_vencidos:0}};
  visibles.forEach(p => {{
    gs.total_viv += p.n_viv; gs.terminadas += p.term; gs.en_tiempo += p.ent;
    gs.atencion += p.atc; gs.criticas += p.crit; gs.sin_despacho += p.sind;
    gs.total_pagado += p.tpag;
    if (p.dr !== null && p.dr < 0) gs.contratos_vencidos++;
    else if (p.dr !== null && p.dr <= 90) gs.contratos_90d++;
  }});
  const avg = visibles.length ? Math.round(visibles.reduce((s,p) => s+p.avd, 0) / visibles.length) : 0;
  const pctTerm = gs.total_viv > 0 ? Math.round(gs.terminadas/gs.total_viv*100) : 0;
  const pctCrit = gs.total_viv > 0 ? Math.round(gs.criticas/gs.total_viv*100) : 0;

  document.getElementById('kpiStrip').innerHTML = `
    <div class="bg-white rounded-xl p-3.5 border border-gray-200 shadow-sm"><div class="text-[10px] uppercase tracking-wide text-gray-500">Proyectos Activos</div><div class="text-2xl font-bold font-mono mt-1">${{visibles.length}}</div></div>
    <div class="bg-white rounded-xl p-3.5 border border-blue-200 shadow-sm"><div class="text-[10px] uppercase tracking-wide text-blue-600">Viviendas</div><div class="text-2xl font-bold font-mono text-blue-600 mt-1">${{gs.total_viv}}</div><div class="text-[10px] text-gray-400 mt-0.5">${{gs.terminadas}} terminadas (${{pctTerm}}%)</div></div>
    <div class="bg-white rounded-xl p-3.5 border border-violet-200 shadow-sm"><div class="text-[10px] uppercase tracking-wide text-violet-600">Avance Despacho</div><div class="text-2xl font-bold font-mono text-violet-600 mt-1">${{avg}}%</div></div>
    <div class="bg-white rounded-xl p-3.5 border border-red-200 shadow-sm" title="${{visibles.filter(p=>p.crit>0).map(p=>p.nombre+': '+p.crit+' ('+p.nombres_crit.join(', ')+')').join('\\n')}}" style="cursor:help"><div class="text-[10px] uppercase tracking-wide text-red-600">Criticas</div><div class="text-2xl font-bold font-mono text-red-600 mt-1">${{gs.criticas}}</div><div class="text-[10px] text-gray-400 mt-0.5">${{pctCrit}}%</div></div>
    <div class="bg-white rounded-xl p-3.5 border border-purple-200 shadow-sm"><div class="text-[10px] uppercase tracking-wide text-purple-600">Total Pagado M.O.</div><div class="text-lg font-bold font-mono text-purple-700 mt-1">${{fpf(gs.total_pagado)}}</div></div>
    <div class="bg-white rounded-xl p-3.5 border border-amber-200 shadow-sm"><div class="text-[10px] uppercase tracking-wide text-amber-600">Contratos &lt;90d</div><div class="text-2xl font-bold font-mono text-amber-600 mt-1">${{gs.contratos_90d}}</div><div class="text-[10px] text-gray-400 mt-0.5">${{gs.contratos_vencidos}} vencido${{gs.contratos_vencidos!==1?'s':''}}</div></div>`;

  // Cards
  const allCards = ALL_DATA.map(p => {{
    const hidden = ocultos.includes(p.id);
    const dr = p.dr;
    let bdg;
    if (dr === null) bdg = '<span class="pb bg-gray-100 text-gray-600 border border-gray-200">Sin fecha</span>';
    else if (dr < 0) bdg = `<span class="pb bg-red-100 text-red-700 border border-red-300">VENCIDO ${{Math.abs(dr)}}d</span>`;
    else if (dr <= 90) bdg = `<span class="pb bg-yellow-100 text-yellow-800 border border-yellow-300">${{dr}}d</span>`;
    else bdg = `<span class="pb bg-green-100 text-green-700 border border-green-300">${{dr}}d</span>`;

    let cc = 'pc';
    if (dr !== null && dr < 0) cc = 'pc border-red-300';
    else if (dr !== null && dr <= 90) cc = 'pc border-yellow-300';
    if (hidden) cc += ' hidden-proj';

    const pf = Math.min(p.pp, 100), fc = bc(p.pp);
    const p90 = p.dur > 90 ? Math.round((p.dur-90)/p.dur*100) : null;
    const m90 = p90 !== null ? `<div class="absolute top-[-3px] w-[2px] h-3 bg-red-600 rounded-sm" style="left:${{p90}}%"></div>` : '';

    let tll;
    if (dr !== null && dr < 0) tll = `<span class="font-mono font-semibold text-red-500">EXCEDIDO +${{Math.abs(dr)}}d</span>`;
    else tll = `<span class="font-mono font-semibold">${{p.dt}}d / ${{p.dur}}d (${{p.pp}}%)</span>`;

    const tot = p.n_viv;
    const segDefs = [
      ['term','bg-green-500','terminadas','#22c55e'],
      ['ent','bg-blue-500','en tiempo','#3b82f6'],
      ['atc','bg-amber-500','atencion','#f59e0b'],
      ['crit','bg-red-500','criticas','#ef4444'],
      ['sind','bg-gray-300','sin despacho','#cbd5e1']
    ];
    let segs = '', leg = '';
    segDefs.forEach(([k,cl,lb,hx]) => {{
      const n = p[k];
      if (n > 0) {{
        const pc_ = Math.max(Math.round(n/tot*100), 5);
        const tc_ = k === 'sind' ? 'text-gray-600' : 'text-white';
        const tooltip = (k === 'crit' && p.nombres_crit && p.nombres_crit.length > 0) ? ` title="${{p.nombres_crit.join('\\n')}}" style="width:${{pc_}}%;cursor:help"` : ` style="width:${{pc_}}%"`;
        segs += `<div class="${{cl}} ${{tc_}} flex items-center justify-center text-[9px] font-bold"${{tooltip}}>${{n}}</div>`;
        const legTooltip = (k === 'crit' && p.nombres_crit && p.nombres_crit.length > 0) ? ` title="${{p.nombres_crit.join('\\n')}}" style="cursor:help"` : '';
        leg += `<span class="flex items-center gap-1"${{legTooltip}}><div class="w-2 h-2 rounded-sm shrink-0" style="background:${{hx}}"></div>${{n}} ${{lb}}</span>`;
      }}
    }});

    let alh = '';
    if (p.als && p.als.length > 0) {{
      let chs = '';
      p.als.forEach(a => {{
        const ic = a.tipo==='danger' ? '&#x1F534;' : a.tipo==='warn' ? '&#x1F536;' : '&#x1F4CB;';
        chs += `<span class="ac ac-${{a.tipo}}">${{ic}} ${{a.msg}}</span>`;
      }});
      const abg = p.als.some(a => a.tipo==='danger') ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200';
      alh = `<div class="px-4 py-2 border-t ${{abg}} flex gap-2 flex-wrap">${{chs}}</div>`;
    }}

    const hideIcon = hidden
      ? '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>'
      : '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M3 3l18 18"/></svg>';
    const hideTitle = hidden ? 'Mostrar proyecto' : 'Ocultar proyecto';
    const hideBtn = `<button onclick="toggleOculto('${{p.id}}')" title="${{hideTitle}}" class="btn-hide p-1.5 rounded-lg text-gray-400 hover:text-gray-700">${{hideIcon}}</button>`;

    // Semaforo
    const semCol = p.semaforo === 'rojo' ? '#ef4444' : p.semaforo === 'amarillo' ? '#f59e0b' : '#22c55e';
    const semBorder = p.semaforo === 'rojo' ? 'border-l-4 border-l-red-500' : p.semaforo === 'amarillo' ? 'border-l-4 border-l-yellow-400' : 'border-l-4 border-l-green-500';

    // Delta prominente
    const deltaSign = p.delta > 0 ? '+' : '';
    const deltaCol = p.delta > 5 ? '#22c55e' : p.delta < -5 ? '#ef4444' : '#f59e0b';

    // Indicadores de documentacion
    function indic(label, n, total, color) {{
      const pct = total > 0 ? Math.round(n/total*100) : 0;
      const bg = pct === 100 ? 'bg-green-100 text-green-700 border-green-200' : pct > 0 ? `bg-${{color}}-50 text-${{color}}-700 border-${{color}}-200` : 'bg-gray-50 text-gray-400 border-gray-200';
      return `<div class="flex items-center justify-between px-2.5 py-1 rounded border ${{bg}}"><span class="text-[9px] font-medium">${{label}}</span><span class="text-[10px] font-bold font-mono">${{n}}/${{total}}</span></div>`;
    }}

    return `<div class="${{cc}} ${{semBorder}}" data-pid="${{p.id}}">
<div class="px-4 pt-3 pb-2 flex items-start justify-between">
  <div class="flex items-center gap-2.5">
    <div class="w-3 h-3 rounded-full shrink-0" style="background:${{semCol}}"></div>
    <div><div class="font-bold text-sm text-gray-800">${{p.nombre}}</div><div class="text-[11px] text-gray-500 mt-0.5">${{p.comuna}} &middot; ${{p.n_viv}} viv</div></div>
  </div>
  <div class="flex items-center gap-1.5">${{hideBtn}}${{bdg}}</div>
</div>
<div class="px-4 pb-1"><div class="flex items-center gap-3 mb-1"><div class="flex-1"><div class="relative h-1.5 bg-gray-200 rounded-full overflow-visible"><div class="h-full rounded-full" style="width:${{pf}}%;background:${{fc}}"></div>${{m90}}</div><div class="flex justify-between text-[9px] text-gray-400 mt-0.5"><span>${{ff(p.fi)}}</span>${{tll}}<span>${{ff(p.venc)}}</span></div></div><div class="text-center shrink-0 ml-2 px-2 py-1 rounded-lg border" style="border-color:${{deltaCol}}20;background:${{deltaCol}}10"><div class="text-[8px] text-gray-400 uppercase">Delta</div><div class="text-sm font-bold font-mono" style="color:${{deltaCol}}">${{deltaSign}}${{p.delta}}%</div></div></div></div>
<div class="px-4 pb-2"><div class="flex h-5 rounded-md overflow-hidden gap-px">${{segs}}</div><div class="flex gap-3 mt-1 text-[9px] text-gray-500 flex-wrap">${{leg}}</div></div>
<div class="px-4 pb-2 grid grid-cols-4 gap-1.5">
  ${{indic('HPC', p.n_hpc, p.n_viv, 'green')}}
  ${{indic('TE1', p.n_te1, p.n_viv, 'amber')}}
  ${{indic('L.Critica', p.n_ecrit, p.n_viv, 'purple')}}
  ${{indic('Recep.Def', p.n_recep, p.n_viv, 'blue')}}
</div>
<div class="grid grid-cols-5 gap-px bg-gray-100 border-t border-gray-200">
<div class="bg-white p-2 text-center"><div class="text-[9px] text-gray-400 uppercase">Av.Desp</div><div class="text-base font-bold font-mono text-violet-600 mt-0.5">${{p.avd}}%</div></div>
<div class="bg-white p-2 text-center"><div class="text-[9px] text-gray-400 uppercase">Av.Insp</div><div class="text-base font-bold font-mono text-indigo-600 mt-0.5">${{p.avi}}%</div></div>
<div class="bg-white p-2 text-center"><div class="text-[9px] text-gray-400 uppercase">Pagado</div><div class="text-xs font-bold font-mono text-purple-700 mt-0.5">${{fp(p.tpag)}}</div></div>
<div class="bg-white p-2 text-center"><div class="text-[9px] text-gray-400 uppercase">Dias Prom</div><div class="text-base font-bold font-mono mt-0.5">${{p.dpr}}d</div></div>
<div class="bg-white p-2 text-center"><div class="text-[9px] text-gray-400 uppercase">Solicitudes</div><div class="text-base font-bold font-mono text-purple-500 mt-0.5">${{p.sol}}</div></div>
</div>${{alh}}</div>`;
  }});
  document.getElementById('cardsGrid').innerHTML = allCards.join('');

  // Ranking (solo visibles)
  const rs = [...visibles].sort((a,b) => a.delta - b.delta);
  let rows = '';
  rs.forEach(p => {{
    const dc = p.delta > 5 ? '#22c55e' : p.delta < -5 ? '#ef4444' : '#f59e0b';
    const ds = p.delta > 0 ? '+' : '';
    const pc_ = bc(p.pp);
    rows += `<tr class="hover:bg-gray-50"><td class="px-3 py-2.5 font-semibold text-gray-800">${{p.nombre}}</td><td class="px-3 py-2.5 text-gray-500">${{p.comuna}}</td><td class="px-3 py-2.5 font-mono font-semibold text-center">${{p.n_viv}}</td><td class="px-3 py-2.5"><span class="font-mono font-semibold" style="color:${{pc_}}">${{p.pp}}%</span><div class="inline-block w-16 h-1.5 bg-gray-200 rounded-full ml-2 align-middle"><div class="h-full rounded-full" style="width:${{Math.min(p.pp,100)}}%;background:${{pc_}}"></div></div></td><td class="px-3 py-2.5"><span class="font-mono font-semibold">${{p.avd}}%</span><div class="inline-block w-16 h-1.5 bg-gray-200 rounded-full ml-2 align-middle"><div class="h-full rounded-full" style="width:${{p.avd}}%;background:#8b5cf6"></div></div></td><td class="px-3 py-2.5"><span class="font-mono font-semibold">${{p.avi}}%</span><div class="inline-block w-16 h-1.5 bg-gray-200 rounded-full ml-2 align-middle"><div class="h-full rounded-full" style="width:${{p.avi}}%;background:#6366f1"></div></div></td><td class="px-3 py-2.5 font-mono font-bold text-center" style="color:${{dc}}">${{ds}}${{p.delta}}%</td><td class="px-3 py-2.5 font-mono font-semibold text-center" style="color:${{p.crit>0?'#ef4444':'#94a3b8'}}">${{p.crit}}</td><td class="px-3 py-2.5 font-mono text-xs">${{fp(p.tpag)}}</td></tr>`;
  }});
  document.getElementById('rankingTable').innerHTML = `<table class="w-full text-xs"><thead><tr class="bg-gray-50 border-b border-gray-200 text-[10px] uppercase tracking-wide text-gray-500"><th class="px-3 py-2.5 text-left">Proyecto</th><th class="px-3 py-2.5 text-left">Comuna</th><th class="px-3 py-2.5 text-center">Viv</th><th class="px-3 py-2.5 text-left">Plazo</th><th class="px-3 py-2.5 text-left">Av.Desp</th><th class="px-3 py-2.5 text-left">Av.Insp</th><th class="px-3 py-2.5 text-center">&#916;</th><th class="px-3 py-2.5 text-center">Crit</th><th class="px-3 py-2.5 text-left">Pagado</th></tr></thead><tbody class="divide-y divide-gray-100">${{rows}}</tbody></table>`;

  // Alertas (solo de visibles)
  const visIds = new Set(visibles.map(p => p.nombre));
  const filtAlertas = ALL_ALERTAS.filter(a => visIds.has(a.proy)).slice(0, 10);
  let alr = '';
  filtAlertas.forEach(a => {{
    const dot = a.tipo==='danger' ? '#ef4444' : a.tipo==='warn' ? '#f59e0b' : '#3b82f6';
    alr += `<div class="flex items-center gap-2 py-2 border-b border-gray-100 last:border-0 text-sm"><div class="w-2 h-2 rounded-full shrink-0" style="background:${{dot}}"></div><span><strong>${{a.proy}}</strong> — ${{a.msg}}</span></div>`;
  }});
  document.getElementById('alertasBox').innerHTML = `<h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Alertas Activas</h3>${{alr || "<p class='text-gray-400 text-sm'>Sin alertas</p>"}}`;

  // Etapas
  const fc_ = {{'Fundaciones':'#22c55e','1era Etapa':'#3b82f6','2da Etapa':'#3b82f6','Gasfiteria':'#8b5cf6','Ceramica':'#8b5cf6','Pintura':'#a855f7','Obras Ext.':'#94a3b8'}};
  let ebs = '';
  Object.entries(ETAPAS_GLOBAL).forEach(([f,d]) => {{
    const pct = d.t > 0 ? Math.round(d.d/d.t*100) : 0;
    const c = fc_[f] || '#94a3b8';
    ebs += `<div class="flex items-center gap-2"><span class="text-[10px] w-20 text-right text-gray-500 shrink-0">${{f}}</span><div class="flex-1 h-3.5 bg-gray-200 rounded overflow-hidden"><div class="h-full flex items-center justify-center text-[8px] font-bold text-white" style="width:${{Math.max(pct,3)}}%;background:${{c}}">${{pct}}%</div></div></div>`;
  }});
  document.getElementById('etapasBox').innerHTML = `<h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Distribucion de Etapas</h3><p class="text-[11px] text-gray-400 mb-3">Despacho agregado — ${{gs.total_viv}} viviendas</p><div class="flex flex-col gap-1.5">${{ebs}}</div>`;

  renderModal();
}}

function renderModal() {{
  const ocultos = getOcultos();
  const body = document.getElementById('modalBody');
  if (!body) return;
  if (ocultos.length === 0) {{
    body.innerHTML = '<p class="text-gray-400 text-sm text-center py-6">No hay proyectos ocultos</p>';
    return;
  }}
  let html = '<div class="flex flex-col gap-2">';
  ocultos.forEach(pid => {{
    const p = ALL_DATA.find(d => d.id === pid);
    if (!p) return;
    html += `<div class="flex items-center justify-between px-3 py-2.5 bg-gray-50 rounded-lg border border-gray-200">
      <div><div class="font-semibold text-sm text-gray-800">${{p.nombre}}</div><div class="text-[11px] text-gray-500">${{p.comuna}} &middot; ${{p.n_viv}} viv</div></div>
      <button onclick="toggleOculto('${{p.id}}')" class="px-3 py-1 bg-indigo-600 text-white text-[10px] font-semibold rounded-lg hover:bg-indigo-700 cursor-pointer">Mostrar</button>
    </div>`;
  }});
  html += '</div>';
  body.innerHTML = html;
}}

function toggleModal() {{
  const m = document.getElementById('modalOcultos');
  m.classList.toggle('show');
  if (m.classList.contains('show')) renderModal();
}}

render();
</script>
</body></html>'''


if __name__ == '__main__':
    generar_panel()

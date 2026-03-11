"""
Dashboard v3 - Vista Unificada con Grupos de Trabajo
Fusiona Obras + Vista Proyecto en una sola interfaz con sistema de Grupos por capataz.
Output: dashboard/index_v3.html
"""
import sys
sys.path.insert(0, '.')
import json
import pandas as pd
from datetime import datetime
from data_manager import DataManager
from pathlib import Path

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

PARTIDAS_SHORT = {
    'A_Fund': 'Fundaciones', 'A_Radier': 'Radier', 'A_Planta_Alc': 'Alcantarillado',
    'A_E_Tabiques': 'Tabiques', 'A_E_Techumbre': 'Techumbre', 'A_rev Ext': 'Rev. Exterior',
    'A_vent': 'Ventanas', 'A_Cubierta': 'Cubierta', 'A_Ent_Cielo': 'Cielo',
    'A_ent_alero': 'Alero', 'A_Red_AP': 'Red Agua Pot.', 'A_Red_Elect': 'Red Electrica',
    'A_rev_ZS': 'Rev. Zona Seca', 'A_rev_ZH': 'Rev. Zona Humeda', 'A_Aisl_Muro': 'Aisl. Muro',
    'A_Aisl_Cielo': 'Aisl. Cielo', 'A_Cer_Piso': 'Ceramico Piso', 'A_Cer_muro': 'Ceramico Muro',
    'A_pint_Ext': 'Pintura Ext.', 'A_pint_int': 'Pintura Int.', 'A_puertas': 'Puertas',
    'A_molduras': 'Molduras', 'A_Art_Baño': 'Art. Bano', 'A_Art_cocina': 'Art. Cocina',
    'A_Art_Elec': 'Art. Electricos', 'A_AP_Ext': 'Agua Pot. Ext.', 'A_ALC_Ext': 'Alcant. Ext.',
    'A_Ins_Elec_Ext': 'Inst. Elec. Ext.'
}

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
    s = str(val).strip().replace('$', '').replace('.', '')
    s = s.replace(',', '.')
    try:
        return int(float(s))
    except:
        return 0

def generar_dashboard_v3_html():
    """Genera el archivo HTML del dashboard v3 con datos reales"""

    print("=" * 60)
    print("DASHBOARD v3 - Vista Unificada + Grupos de Trabajo")
    print("=" * 60)
    print("\nCargando datos desde Google Sheets...")
    dm = DataManager()

    proyectos = dm.get_table_data('Proyectos')
    beneficiarios = dm.get_table_data('Beneficiario')
    despachos = dm.get_table_data('Despacho')
    solicitudes = dm.get_table_data('soldepacho')
    ejecucion = dm.get_table_data('Ejecucion')
    solpago = dm.get_table_data('Solpago')
    maestros = dm.get_table_data('Maestros')
    tabla_pago = dm.get_table_data('Tabla_pago')
    tipologias = dm.get_table_data('Tipologias')
    control_bgb = dm.get_table_data('controlBGB')
    control_eepp_raw = dm.conn.spreadsheet.worksheet('controlEEPP').get_all_values()
    control_eepp_headers = control_eepp_raw[0] if control_eepp_raw else []
    control_eepp_rows = []
    for r in control_eepp_raw[1:]:
        row = {}
        for c, h in enumerate(control_eepp_headers):
            row[h] = r[c] if c < len(r) else ''
        control_eepp_rows.append(row)

    proyectos_activos = proyectos[
        proyectos['estado_general'].str.lower().str.contains('ejecuci|finalizado', na=False, regex=True)
    ].copy()
    print(f"Proyectos (ejecucion + finalizados): {len(proyectos_activos)}")

    proyectos_data = []
    for _, p in proyectos_activos.iterrows():
        fecha_inicio = str(p.get('fecha_inicio', ''))
        duracion = str(p.get('duracion', ''))
        fi_iso = ''
        if fecha_inicio and fecha_inicio not in ['nan', 'NaT', '']:
            for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                try:
                    fi_dt = datetime.strptime(fecha_inicio.split()[0], fmt)
                    fi_iso = fi_dt.strftime('%Y-%m-%d')
                    break
                except:
                    pass
        dur_dias = 0
        if duracion and duracion not in ['nan', '', 'None']:
            try:
                dur_dias = int(float(duracion))
            except:
                pass
        estado_raw = str(p.get('estado_general', '')).strip()
        estado = 'finalizado' if 'finalizado' in estado_raw.lower() else 'ejecucion'
        proyectos_data.append({
            'ID_proy': str(p.get('ID_proy', '')),
            'NOMBRE_PROYECTO': str(p.get('NOMBRE_PROYECTO', '')),
            'COMUNA': str(p.get('COMUNA', '')),
            'fecha_inicio': fi_iso,
            'duracion': dur_dias,
            'estado': estado
        })

    # Ordenar: ejecucion primero, luego finalizados; dentro de cada grupo fecha desc
    from functools import cmp_to_key
    def cmp_proy(a, b):
        ea = 0 if a['estado'] == 'ejecucion' else 1
        eb = 0 if b['estado'] == 'ejecucion' else 1
        if ea != eb: return ea - eb
        fa = a['fecha_inicio'] or '0000-00-00'
        fb = b['fecha_inicio'] or '0000-00-00'
        if fa > fb: return -1
        if fa < fb: return 1
        return 0
    proyectos_data.sort(key=cmp_to_key(cmp_proy))

    ids_proyectos = set(proyectos_activos['ID_proy'].astype(str).tolist())
    estados_validos = ['ejecuci', 'subsidiad', 'preparaci', 'terminad']
    beneficiarios_activos = beneficiarios[
        (beneficiarios['ID_Proy'].astype(str).isin(ids_proyectos)) &
        (beneficiarios['Estado'].str.lower().str.contains('|'.join(estados_validos), na=False, regex=True))
    ].copy()
    print(f"Beneficiarios en ejecucion: {len(beneficiarios_activos)}")

    # Construir diccionario de tipologías para nombres descriptivos
    tip_dict = {}
    for _, t in tipologias.iterrows():
        tid = str(t.get('IDU_tipol', ''))
        if not tid or tid in ['nan', '']: continue
        familia = str(t.get('Familia', '')).strip()
        dorm = str(t.get('dormitorios', '')).strip()
        plantas = str(t.get('plantas', '')).strip()
        caract = str(t.get('caracterizacion', '')).strip()
        nombre = str(t.get('tipologia', '')).strip()
        # Build: "Vivienda 2D 1P 58.15 m2" or "RC 1D 1P 25 m2"
        label = familia if familia and familia.lower() not in ['nan', ''] else nombre
        if dorm and dorm not in ['nan', '', '0']:
            label += f" {dorm}D"
        if plantas and plantas not in ['nan', '', '0']:
            label += f" {plantas}P"
        if caract and caract.lower() not in ['nan', '', 'none']:
            label += f" {caract}"
        tip_dict[tid] = label
    print(f"Tipologias cargadas: {len(tip_dict)}")

    beneficiarios_data = []
    for _, b in beneficiarios_activos.iterrows():
        tipologia = str(b.get('Tipologia Vivienda', ''))
        tipologia_rc = str(b.get('Tipologia RC', ''))
        tip_viv_id = tipologia if tipologia.lower() not in ['nan', '', 'none'] else ''
        tip_rc_id = tipologia_rc if tipologia_rc.lower() not in ['nan', '', 'none'] else ''
        # Nombre descriptivo de tipología
        tip_viv_nombre = tip_dict.get(tip_viv_id, '')
        tip_rc_nombre = tip_dict.get(tip_rc_id, '')
        if tip_viv_nombre and tip_rc_nombre:
            tipo_display = f"{tip_viv_nombre} + {tip_rc_nombre}"
        elif tip_viv_nombre:
            tipo_display = tip_viv_nombre
        elif tip_rc_nombre:
            tipo_display = tip_rc_nombre
        else:
            tipo_display = "Casa + RC" if tip_rc_id else "Casa"
        hpc_raw = str(b.get('Habil para construir', '')).strip().upper()
        habil = hpc_raw == 'TRUE'
        fecha_hpc_raw = str(b.get('fecha_habil_para_const', '')).strip()
        fecha_hpc = ''
        if fecha_hpc_raw and fecha_hpc_raw.lower() not in ['nan', '', 'nat', 'none']:
            try:
                if '-' in fecha_hpc_raw and len(fecha_hpc_raw) >= 10:
                    parts = fecha_hpc_raw.split('-')
                    if len(parts[0]) == 4:
                        fecha_hpc = fecha_hpc_raw[:10]
                    else:
                        fecha_hpc = f"{parts[2][:4]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                elif '/' in fecha_hpc_raw:
                    parts = fecha_hpc_raw.split('/')
                    fecha_hpc = f"{parts[2][:4]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            except:
                fecha_hpc = ''
        beneficiarios_data.append({
            'ID_Benef': int(b['ID_Benef']) if str(b['ID_Benef']).isdigit() else str(b['ID_Benef']),
            'ID_Proy': str(b.get('ID_Proy', '')),
            'NOMBRES': str(b.get('NOMBRES', '')),
            'APELLIDOS': str(b.get('APELLIDOS', '')),
            'tipologia': tipo_display,
            'tipologia_viv_id': tip_viv_id,
            'tipologia_rc_id': tip_rc_id,
            'habil': habil,
            'fecha_hpc': fecha_hpc
        })

    ids_beneficiarios = set([str(b['ID_Benef']) for b in beneficiarios_data])
    despachos_filtrados = despachos[
        despachos['ID_Benef'].astype(str).isin(ids_beneficiarios)
    ].copy()
    print(f"Despachos encontrados: {len(despachos_filtrados)}")

    despachos_data = []
    for _, d in despachos_filtrados.iterrows():
        fecha = str(d.get('Fecha', ''))
        if fecha and fecha not in ['nan', 'NaT', '']:
            try:
                fecha_dt = datetime.strptime(fecha.split()[0], '%m/%d/%Y')
                fecha = fecha_dt.strftime('%Y-%m-%d')
            except:
                pass
        if fecha and fecha not in ['nan', 'NaT', '']:
            id_benef = d.get('ID_Benef')
            try:
                id_benef = int(id_benef) if str(id_benef).isdigit() else str(id_benef)
            except:
                id_benef = str(id_benef)
            despachos_data.append({
                'ID_Benef': id_benef,
                'Tipo_despacho': str(d.get('Tipo_despacho', '')),
                'Fecha': fecha,
                'Guia': str(d.get('Guia', ''))
            })

    solicitudes_filtradas = solicitudes[
        solicitudes['ID_Benef'].astype(str).isin(ids_beneficiarios)
    ].copy()
    print(f"Solicitudes encontradas: {len(solicitudes_filtradas)}")

    solicitudes_data = []
    for _, s in solicitudes_filtradas.iterrows():
        fecha = str(s.get('Fecha', ''))
        fecha_creacion = str(s.get('fecha_creacion', ''))
        if fecha and fecha not in ['nan', 'NaT', '']:
            try:
                fecha_dt = datetime.strptime(fecha.split()[0], '%m/%d/%Y')
                fecha = fecha_dt.strftime('%Y-%m-%d')
            except:
                pass
        if fecha_creacion and fecha_creacion not in ['nan', 'NaT', '']:
            try:
                fecha_dt = datetime.strptime(fecha_creacion.split()[0], '%m/%d/%Y')
                fecha_creacion = fecha_dt.strftime('%Y-%m-%d')
            except:
                pass
        if fecha_creacion and fecha_creacion not in ['nan', 'NaT', '']:
            id_benef = s.get('ID_Benef')
            try:
                id_benef = int(id_benef) if str(id_benef).isdigit() else str(id_benef)
            except:
                id_benef = str(id_benef)
            solicitudes_data.append({
                'ID_Benef': id_benef,
                'Tipo_despacho': str(s.get('Tipo_despacho', '')),
                'Fecha': fecha if fecha not in ['nan', 'NaT', ''] else '',
                'fecha_creacion': fecha_creacion
            })

    # ===== INSPECCIONES =====
    print("Calculando avance por inspecciones...")
    pesos = dict(PESOS_VIV)
    shorts = dict(PARTIDAS_SHORT)
    if 'A_Art_Baño' not in ejecucion.columns and 'A_Art_Bano' in ejecucion.columns:
        pesos['A_Art_Bano'] = pesos.pop('A_Art_Baño')
        shorts['A_Art_Bano'] = shorts.pop('A_Art_Baño')

    viv_cols = [c for c in pesos.keys() if c in ejecucion.columns]
    rc_cols = [c for c in ejecucion.columns if c.startswith('AB_')]
    hab_col = 'A_Habilitacion' if 'A_Habilitacion' in ejecucion.columns else None
    CIERRE_COLS = ['empalme', 'preF1', 'desarme', 'ret_escombro', 'aseo']
    CIERRE_LABELS = {'empalme': 'E', 'preF1': 'P', 'desarme': 'D', 'ret_escombro': 'R', 'aseo': 'A'}
    cierre_cols = [c for c in CIERRE_COLS if c in ejecucion.columns]
    all_cols = viv_cols + rc_cols + ([hab_col] if hab_col else [])
    for col in all_cols:
        ejecucion[col] = ejecucion[col].apply(_to_float)

    inspecciones_data = []
    for id_benef in ids_beneficiarios:
        ejec_b = ejecucion[ejecucion['ID_benef'].astype(str) == str(id_benef)]
        if len(ejec_b) == 0:
            continue
        acum = ejec_b[all_cols].sum()
        pct_viv = sum(min(max(acum.get(col, 0), 0), 1) * peso for col, peso in pesos.items() if col in acum.index)
        rc_vals = [min(max(acum.get(col, 0), 0), 1) for col in rc_cols if col in acum.index]
        pct_rc = sum(rc_vals) / len(rc_vals) if rc_vals else 0
        hab_val = min(max(acum.get(hab_col, 0), 0), 1) if hab_col else 0
        pct_total = pct_viv * 0.7 + pct_rc * 0.25 + hab_val * 0.05
        partidas = {}
        for col in viv_cols:
            short = shorts.get(col, col)
            partidas[short] = round(min(max(acum.get(col, 0), 0), 1) * 100)
        ultima_fecha = ''
        n_insp = len(ejec_b)
        fechas = ejec_b['Fecha_creacion'].dropna()
        fechas = fechas[fechas.astype(str).str.strip() != '']
        for f in fechas:
            try:
                fecha_dt = datetime.strptime(str(f).split()[0], '%m/%d/%Y')
                f_iso = fecha_dt.strftime('%Y-%m-%d')
                if f_iso > ultima_fecha:
                    ultima_fecha = f_iso
            except:
                pass
        cierre = {}
        for col in cierre_cols:
            label = CIERRE_LABELS.get(col, col[0].upper())
            vals = ejec_b[col].dropna()
            vals = vals[vals.astype(str).str.strip() != '']
            estado = str(vals.iloc[-1]).strip() if len(vals) > 0 else ''
            cierre[label] = 1 if estado.lower() == 'terminado' else 0
        inspecciones_data.append({
            'ID_Benef': int(id_benef) if str(id_benef).isdigit() else str(id_benef),
            'pct_viv': round(pct_viv * 100, 1),
            'pct_rc': round(pct_rc * 100, 1),
            'pct_hab': round(hab_val * 100, 1),
            'pct_total': round(pct_total * 100, 1),
            'ultima_insp': ultima_fecha,
            'n_insp': n_insp,
            'partidas': partidas,
            'cierre': cierre
        })
    print(f"Inspecciones calculadas: {len(inspecciones_data)} beneficiarios con datos")

    # ===== SOLPAGO =====
    print("Procesando datos de pago (Solpago)...")
    solpago_filtrado = solpago[
        (solpago['ID_Benef'].astype(str).isin(ids_beneficiarios)) &
        (solpago['Estado'].astype(str).str.strip().str.lower() == 'aprobado')
    ].copy()
    print(f"Solpago filtrados (Aprobados): {len(solpago_filtrado)} de {len(solpago)} total")

    solpago_data = []
    for _, sp in solpago_filtrado.iterrows():
        fecha = str(sp.get('fecha', ''))
        if fecha and fecha not in ['nan', 'NaT', '']:
            try:
                fecha_dt = datetime.strptime(fecha.split()[0], '%m/%d/%Y')
                fecha = fecha_dt.strftime('%Y-%m-%d')
            except:
                pass
        id_benef = sp.get('ID_Benef')
        try:
            id_benef = int(id_benef) if str(id_benef).isdigit() else str(id_benef)
        except:
            id_benef = str(id_benef)
        monto = parse_monto(sp.get('monto', 0))
        estado = str(sp.get('Estado', '')).strip()
        familia = str(sp.get('Familia_pago', '')).strip()
        if (monto > 0 or (estado and estado.lower() not in ['nan', ''])) and familia.lower() != 'nan':
            solpago_data.append({
                'ID_Benef': id_benef,
                'Familia_pago': familia,
                'Tipo_pago': str(sp.get('Tipo_pago', '')),
                'monto': monto,
                'fecha': fecha if fecha not in ['nan', 'NaT', ''] else '',
                'maestro': str(sp.get('maestro', '')).strip(),
                'Estado': estado if estado.lower() != 'nan' else ''
            })
    print(f"Solpago procesados: {len(solpago_data)} registros")

    # Maestros dict
    maestros_dict = {}
    for _, m in maestros.iterrows():
        idu = str(m.get('IDU_maestros', '')).strip()
        nombre_comp = str(m.get('Nombre_comp', '')).strip()
        if not nombre_comp or nombre_comp.lower() == 'nan':
            nombres = str(m.get('Nombres', '')).strip()
            apellidos = str(m.get('Apellidos', '')).strip()
            nombre_comp = f"{nombres} {apellidos}".strip()
        if idu and idu.lower() != 'nan' and nombre_comp and nombre_comp.lower() != 'nan':
            maestros_dict[idu] = nombre_comp
    print(f"Maestros: {len(maestros_dict)} registros")

    # ===== PRESUPUESTO =====
    print("Procesando Tabla M.O. Base (Tabla_pago)...")
    tabla_pago_filtrada = tabla_pago[
        tabla_pago['ID_proy'].astype(str).isin(ids_proyectos)
    ].copy()

    def parse_monto_base(val):
        if pd.isna(val) or val == '' or val is None or str(val).strip() in ['-', 'nan']:
            return 0
        try:
            return float(val)
        except:
            return parse_monto(val)

    presupuesto_por_tipologia = {}
    for _, tp in tabla_pago_filtrada.iterrows():
        tipol_id = str(tp.get('IDU_Tipol', '')).strip()
        familia = str(tp.get('familia_pago', '')).strip()
        monto = parse_monto_base(tp.get('monto', 0))
        if tipol_id and tipol_id.lower() != 'nan' and familia and familia.lower() != 'nan':
            if tipol_id not in presupuesto_por_tipologia:
                presupuesto_por_tipologia[tipol_id] = {}
            presupuesto_por_tipologia[tipol_id][familia] = \
                presupuesto_por_tipologia[tipol_id].get(familia, 0) + monto
    print(f"Tabla_pago: {len(tabla_pago_filtrada)} registros, {len(presupuesto_por_tipologia)} tipologias")

    # ===== GARANTIAS =====
    garantias_data = []
    for _, g in control_bgb.iterrows():
        id_proy = str(g.get('ID_Proy', ''))
        if id_proy not in ids_proyectos:
            continue
        fecha_vcmto = str(g.get('Fecha_vcmto', ''))
        fecha_inicio = str(g.get('Fecha_inic', ''))
        fv_iso, fi_iso_g = '', ''
        for fraw, target in [(fecha_vcmto, 'fv'), (fecha_inicio, 'fi')]:
            if fraw and fraw not in ['nan', 'NaT', '']:
                for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(fraw.split()[0], fmt)
                        if target == 'fv':
                            fv_iso = dt.strftime('%Y-%m-%d')
                        else:
                            fi_iso_g = dt.strftime('%Y-%m-%d')
                        break
                    except:
                        pass
        monto = str(g.get('Monto', ''))
        try:
            monto_val = int(float(monto)) if monto not in ['nan', '', 'None'] else 0
        except:
            monto_val = 0
        garantias_data.append({
            'ID_Proy': id_proy, 'tipo': str(g.get('Tipo', '')), 'tipo1': str(g.get('Tipo1', '')),
            'num_bol': str(g.get('num_bol', '')), 'banco': str(g.get('Banco', '')),
            'monto_uf': monto_val, 'fecha_inicio': fi_iso_g, 'fecha_vcmto': fv_iso
        })
    print(f"Garantias (BGB): {len(garantias_data)} para proyectos activos")

    # ===== ESTADOS DE PAGO SERVIU =====
    def parse_monto_uf(raw):
        s = str(raw).strip()
        if not s or s in ['nan', 'None', '']:
            return 0
        try:
            if ',' in s and '.' in s:
                return round(float(s.replace('.', '').replace(',', '.')), 2)
            elif ',' in s:
                return round(float(s.replace(',', '.')), 2)
            else:
                return round(float(s), 2)
        except:
            return 0

    eepp_data = []
    for ep in control_eepp_rows:
        id_proy = str(ep.get('ID_Proy', ''))
        if id_proy not in ids_proyectos:
            continue
        fecha = str(ep.get('Fecha', ''))
        f_iso = ''
        if fecha and fecha not in ['nan', 'NaT', '']:
            for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(fecha.split()[0], fmt)
                    f_iso = dt.strftime('%Y-%m-%d')
                    break
                except:
                    pass
        id_benef = ep.get('ID_Benef', '')
        try:
            id_benef = int(id_benef) if str(id_benef).isdigit() else str(id_benef)
        except:
            id_benef = str(id_benef)
        monto_val = parse_monto_uf(ep.get('Monto', '0'))
        eepp_data.append({
            'ID_Proy': id_proy, 'ID_Benef': id_benef, 'Num_EP': str(ep.get('Num_EP', '')),
            'Monto': monto_val, 'Estado': str(ep.get('Estado', '')), 'Fecha': f_iso
        })
    print(f"Estados de Pago (EEPP): {len(eepp_data)} para proyectos activos")

    # v3: NO genera reportes

    html_content = generate_html_template_v3(
        proyectos_data, beneficiarios_data, despachos_data, solicitudes_data,
        inspecciones_data, solpago_data, maestros_dict,
        presupuesto_por_tipologia, garantias_data, eepp_data
    )

    output_path = Path(__file__).parent.parent / 'dashboard' / 'index_v3.html'
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\nDashboard v3 generado: {output_path}")
    print(f"  - Proyectos: {len(proyectos_data)}")
    print(f"  - Beneficiarios: {len(beneficiarios_data)}")
    print(f"  - Despachos: {len(despachos_data)}")
    print(f"  - Solicitudes: {len(solicitudes_data)}")
    print(f"  - Inspecciones: {len(inspecciones_data)}")
    print(f"  - Solpago: {len(solpago_data)}")
    print(f"  - Maestros: {len(maestros_dict)}")
    return str(output_path)


def generate_html_template_v3(proyectos, beneficiarios, despachos, solicitudes,
                               inspecciones, solpago=None, maestros=None,
                               presupuesto=None, garantias=None, eepp=None):
    """Genera HTML v3 con datos embebidos"""

    proyectos_json = json.dumps(proyectos, ensure_ascii=False, indent=2)
    beneficiarios_json = json.dumps(beneficiarios, ensure_ascii=False, indent=2)
    despachos_json = json.dumps(despachos, ensure_ascii=False, indent=2)
    solicitudes_json = json.dumps(solicitudes, ensure_ascii=False, indent=2)
    inspecciones_json = json.dumps(inspecciones, ensure_ascii=False, indent=2)
    solpago_json = json.dumps(solpago or [], ensure_ascii=False)
    maestros_json = json.dumps(maestros or {{}}, ensure_ascii=False)
    presupuesto_json = json.dumps(presupuesto or {{}}, ensure_ascii=False)
    garantias_json = json.dumps(garantias or [], ensure_ascii=False)
    eepp_json = json.dumps(eepp or [], ensure_ascii=False)

    etapas_config_path = Path(__file__).parent.parent / 'config' / 'etapas_config.json'
    try:
        with open(etapas_config_path, 'r', encoding='utf-8') as f:
            etapas_full = json.load(f)
        etapas_config_full_json = json.dumps(etapas_full, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  WARN: No se pudo cargar etapas_config.json: {{e}}")
        etapas_config_full_json = '{{}}'

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Control v3 - SG Raices</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-database-compat.js"></script>
    <script>
        // Firebase Config
        const firebaseConfig = {{
            apiKey: "AIzaSyDuM11JE-7klfBBrWsSSi1DF71HiXXYpW0",
            authDomain: "scraices-dashboard.firebaseapp.com",
            databaseURL: "https://scraices-dashboard-default-rtdb.firebaseio.com",
            projectId: "scraices-dashboard",
            storageBucket: "scraices-dashboard.firebasestorage.app",
            messagingSenderId: "158927821043",
            appId: "1:158927821043:web:2ca9bfdaff066dcc527f86"
        }};
        const fbApp = firebase.initializeApp(firebaseConfig);
        const fbDB = firebase.database();
    </script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        'raices-red': '#8B2332',
                        'raices-dark': '#1a1a2e'
                    }},
                    fontFamily: {{
                        sans: ['IBM Plex Sans', 'sans-serif'],
                        mono: ['IBM Plex Mono', 'monospace']
                    }}
                }}
            }}
        }}
    </script>
    <style>
        * {{ font-family: 'IBM Plex Sans', sans-serif; }}
        .font-mono {{ font-family: 'IBM Plex Mono', monospace; }}
        .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
        .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        @keyframes pulse-soft {{ 0%,100%{{opacity:1}} 50%{{opacity:.6}} }}
        .pulse-soft {{ animation: pulse-soft 2s ease-in-out infinite; }}
        .triple-bar {{ height:100%; border-radius:9999px; transition: width .5s ease; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .animate-pulse {{ animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }}
        @keyframes coherence-pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }} 50% {{ box-shadow: 0 0 0 4px rgba(239,68,68,0); }} }}
        .coherence-pulse {{ animation: coherence-pulse 2s ease-in-out infinite; }}
    </style>
</head>
<body class="bg-gray-50 text-gray-800 min-h-screen">
<div id="root"></div>
<script type="text/babel">

// ========== DATA ==========
const PROYECTOS_DATA = {proyectos_json};
const BENEFICIARIOS_DATA = {beneficiarios_json};
const DESPACHOS_DATA = {despachos_json};
const SOLICITUDES_DATA = {solicitudes_json};
const INSPECCIONES_DATA = {inspecciones_json};
const SOLPAGO_DATA = {solpago_json};
const MAESTROS_DATA = {maestros_json};
const PRESUPUESTO_DATA = {presupuesto_json};
const GARANTIAS_DATA = {garantias_json};
const EEPP_DATA = {eepp_json};
const ETAPAS_CONFIG_FULL = {etapas_config_full_json};

// ========== ETAPAS CONFIG ==========
const ETAPAS_CONFIG = ETAPAS_CONFIG_FULL.etapas || {{}};
const SECUENCIA_PRINCIPAL = ETAPAS_CONFIG_FULL.secuencia_principal || [];

// ========== FAMILIA PAGO MAP ==========
const FAMILIA_PAGO_MAP = {{
    "01 - Fundaciones": ["01_FUNDACIONES", "12_ALCANTARILLADO"],
    "02 - 1era Etapa": ["02_1ERA_ETAPA", "28_VENTANAS", "29_EIFS"],
    "03 - 2da Etapa": ["03_2DA_ETAPA", "07_CERAMICO_PISO", "09_PINTURA_EXT", "10_PINTURA_INT"],
    "04 - Gasfiteria": ["13_GASFITERIA"],
    "05 - Cerámica": ["08_CERAMICO_MURO"],
    "06 - Pintura": ["09_PINTURA_EXT", "10_PINTURA_INT"],
    "07 - Eléctricidad": [],
    "08 - Obras Exteriores": [],
    "11 - Recepcion": []
}};
const FAMILIA_LABELS = {{
    "01 - Fundaciones": "Fundaciones", "02 - 1era Etapa": "1era Etapa", "03 - 2da Etapa": "2da Etapa",
    "04 - Gasfiteria": "Gasfiteria", "05 - Cerámica": "Ceramica", "06 - Pintura": "Pintura",
    "07 - Eléctricidad": "Electricidad", "08 - Obras Exteriores": "OO.EE.", "11 - Recepcion": "Recepcion"
}};
const FAMILIAS_CRITICAS = ["01 - Fundaciones", "02 - 1era Etapa", "03 - 2da Etapa", "04 - Gasfiteria", "05 - Cerámica"];
const FAMILIA_PARTIDAS = {{
    "01 - Fundaciones": ["Fundaciones", "Radier", "Alcantarillado"],
    "02 - 1era Etapa": ["Tabiques", "Techumbre", "Rev. Exterior", "Ventanas", "Cubierta", "Cielo", "Alero", "Red Agua Pot.", "Red Electrica"],
    "03 - 2da Etapa": ["Rev. Zona Seca", "Rev. Zona Humeda", "Aisl. Muro", "Aisl. Cielo", "Ceramico Piso", "Ceramico Muro", "Pintura Ext.", "Pintura Int.", "Puertas", "Molduras"],
    "04 - Gasfiteria": ["Art. Bano", "Art. Cocina"],
    "05 - Cerámica": ["Ceramico Piso", "Ceramico Muro"],
    "07 - Eléctricidad": ["Art. Electricos"],
    "08 - Obras Exteriores": ["Agua Pot. Ext.", "Alcant. Ext.", "Inst. Elec. Ext."]
}};

// ========== UTILITY FUNCTIONS ==========
const getAvancePorFamilia = (idBenef) => {{
    const insp = INSPECCIONES_DATA.find(i => String(i.ID_Benef) === String(idBenef));
    if (!insp || !insp.partidas) return {{}};
    const result = {{}};
    Object.entries(FAMILIA_PARTIDAS).forEach(([fam, partidas]) => {{
        const vals = partidas.map(p => insp.partidas[p] ?? null).filter(v => v !== null);
        if (vals.length > 0) {{
            const pct = Math.round(vals.reduce((s,v) => s+v, 0) / vals.length);
            const completas = vals.filter(v => v >= 100).length;
            result[fam] = {{ pct, completas, total: vals.length, partidas: partidas.map(p => ({{ nombre: p, valor: insp.partidas[p] ?? 0 }})) }};
        }}
    }});
    return result;
}};

const fechaChile = () => {{
    const d = new Date();
    const o = d.getTimezoneOffset();
    const cl = new Date(d.getTime() - (o * 60000) + (-3 * 3600000) - (-o * 60000));
    const pad = (n) => String(n).padStart(2, '0');
    return `${{cl.getFullYear()}}-${{pad(cl.getMonth()+1)}}-${{pad(cl.getDate())}}T${{pad(cl.getHours())}}:${{pad(cl.getMinutes())}}`;
}};
const formatPeso = (n) => "$" + Number(n).toLocaleString("es-CL");
const getSolpago = (idBenef) => SOLPAGO_DATA.filter(s => String(s.ID_Benef) === String(idBenef));
const getTotalPagado = (idBenef) => getSolpago(idBenef).reduce((s, p) => s + p.monto, 0);
const getMaestroNombre = (id) => MAESTROS_DATA[id] || id || "Desconocido";
const getInspeccion = (idBenef) => INSPECCIONES_DATA.find(i => String(i.ID_Benef) === String(idBenef)) || null;

const getPagosPorFamilia = (idBenef) => {{
    const pagos = getSolpago(idBenef);
    const porFam = {{}};
    pagos.forEach(p => {{
        if (!porFam[p.Familia_pago]) porFam[p.Familia_pago] = {{ total: 0, count: 0, maestros: new Set() }};
        porFam[p.Familia_pago].total += p.monto;
        porFam[p.Familia_pago].count++;
        if (p.maestro && p.maestro !== 'nan') porFam[p.Familia_pago].maestros.add(getMaestroNombre(p.maestro));
    }});
    return porFam;
}};

// Mapea UN segmento de tipo_despacho a su etapa correspondiente
const mapearSegmento = (segmento) => {{
    if (!segmento) return null;
    const t = segmento.toLowerCase().trim();
    if (t.includes("fundacion") && !t.includes("eifs") && !t.includes("aislacion")) return "01_FUNDACIONES";
    if (t.includes("alcantarillado")) return "12_ALCANTARILLADO";
    if (t.includes("1era")) return "02_1ERA_ETAPA";
    if (t.includes("ventana")) return "28_VENTANAS";
    if (t.includes("eifs") || t.includes("aislacion fund")) return "29_EIFS";
    if (t.includes("2da")) return "03_2DA_ETAPA";
    if (t.includes("piso") && t.includes("ceram")) return "07_CERAMICO_PISO";
    if (t.includes("07-") && t.includes("piso")) return "07_CERAMICO_PISO";
    if (t.includes("muro") && t.includes("ceram")) return "08_CERAMICO_MURO";
    if (t.includes("08-") && t.includes("muro")) return "08_CERAMICO_MURO";
    if (t.includes("pintura ext") || t.includes("09-")) return "09_PINTURA_EXT";
    if (t.includes("pintura int") || t.includes("10-")) return "10_PINTURA_INT";
    if (t.includes("pintura") && t.includes("r.c")) return "09_PINTURA_EXT";
    if (t.includes("gasfiter") || t.includes("sol. ac") || t.includes("artefact") || t.includes("cocina") || t.includes("calefont")) return "13_GASFITERIA";
    if (t.includes("obra") && t.includes("ext")) return "14_OBRAS_EXT";
    if (t.includes("ap ext") || t.includes("05-")) return "14_OBRAS_EXT";
    return null;
}};

// Mapea un tipo_despacho completo (puede contener multiples etapas separadas por coma)
const mapearTipoDespacho = (tipo) => {{
    if (!tipo) return [];
    const segmentos = tipo.split(',');
    const etapas = [];
    segmentos.forEach(seg => {{
        const key = mapearSegmento(seg);
        if (key && !etapas.includes(key)) etapas.push(key);
    }});
    return etapas;
}};

const calcularDias = (fecha) => {{
    if (!fecha) return null;
    return Math.floor((new Date() - new Date(fecha)) / (1000 * 60 * 60 * 24));
}};

// ========== ESTADO ETAPAS ==========
const calcularEstadoEtapas = (idBenef) => {{
    // 1. Mapear DESPACHOS realizados
    const despachos = DESPACHOS_DATA.filter(d => String(d.ID_Benef) === String(idBenef));
    const etapasCompletadas = {{}};
    despachos.forEach(d => {{
        const keys = mapearTipoDespacho(d.Tipo_despacho);
        keys.forEach(key => {{
            if (!etapasCompletadas[key] || new Date(d.Fecha) > new Date(etapasCompletadas[key].fecha)) {{
                etapasCompletadas[key] = {{ fecha: d.Fecha, guia: d.Guia, dias: calcularDias(d.Fecha) }};
            }}
        }});
    }});

    // 2. Mapear SOLICITUDES de despacho
    const solicitudes = SOLICITUDES_DATA.filter(s => String(s.ID_Benef) === String(idBenef));
    const etapasSolicitadas = {{}};
    solicitudes.forEach(s => {{
        const keys = mapearTipoDespacho(s.Tipo_despacho);
        keys.forEach(key => {{
            const fechaSol = s.Fecha || s.fecha_creacion || '';
            if (fechaSol && (!etapasSolicitadas[key] || new Date(fechaSol) > new Date(etapasSolicitadas[key]?.fecha || '1900-01-01'))) {{
                etapasSolicitadas[key] = {{ fecha: fechaSol, dias: calcularDias(fechaSol) }};
            }}
        }});
    }});

    // 3. Calcular estado de cada etapa
    const resultado = {{}};
    Object.entries(ETAPAS_CONFIG).forEach(([etapaKey, config]) => {{
        const nombre = config.nombre || etapaKey;
        const dep = config.dependencia;
        const tiempoOptimo = config.tiempo_optimo;
        const tiempoAlerta = config.tiempo_alerta;
        const info = {{ estado: "bloqueado", nombre, codigo: config.codigo, fechaDespacho: null, fechaSolicitud: null, guia: null, diasTranscurridos: null, diasSolicitud: null }};

        if (etapasCompletadas[etapaKey]) {{
            info.estado = "despachado";
            info.fechaDespacho = etapasCompletadas[etapaKey].fecha;
            info.guia = etapasCompletadas[etapaKey].guia;
            info.diasTranscurridos = etapasCompletadas[etapaKey].dias;
            if (etapasSolicitadas[etapaKey]) {{
                info.fechaSolicitud = etapasSolicitadas[etapaKey].fecha;
            }}
        }} else if (etapasSolicitadas[etapaKey]) {{
            info.estado = "solicitado";
            info.fechaSolicitud = etapasSolicitadas[etapaKey].fecha;
            info.diasSolicitud = etapasSolicitadas[etapaKey].dias;
        }} else if (dep) {{
            if (etapasCompletadas[dep]) {{
                const fechaDep = new Date(etapasCompletadas[dep].fecha);
                const diasDesde = Math.floor((new Date() - fechaDep) / (1000*60*60*24));
                const durDep = ETAPAS_CONFIG[dep]?.duracion || 0;
                const diasEfectivos = Math.max(diasDesde - durDep, 0);
                info.estado = "en_tiempo";
                info.diasTranscurridos = diasEfectivos;
                if (tiempoAlerta !== null && diasEfectivos >= tiempoAlerta) info.estado = "critico";
                else if (tiempoOptimo !== null && diasEfectivos >= tiempoOptimo) info.estado = "atencion";
            }}
        }} else {{
            info.estado = "en_tiempo";
            info.diasTranscurridos = 0;
        }}

        resultado[etapaKey] = info;
    }});
    return resultado;
}};

const calcCoherencia = (idBenef, estadoEtapas) => {{
    const alertas = [];
    const pagos = getSolpago(idBenef);
    const insp = getInspeccion(idBenef);
    const avanceFam = getAvancePorFamilia(idBenef);

    // Alertas por familia: cruce Despacho + Pago + Inspeccion
    Object.entries(FAMILIA_PAGO_MAP).forEach(([fam, etapasKeys]) => {{
        const pagosFam = pagos.filter(p => p.Familia_pago === fam);
        const totalPagado = pagosFam.reduce((s, p) => s + p.monto, 0);
        const tieneDespacho = etapasKeys.some(k => estadoEtapas[k]?.estado === "despachado");
        const avance = avanceFam[fam];
        const avPct = avance ? avance.pct : null;

        // ROJO: Despacho + Pago pero inspeccion baja (<30%)
        if (totalPagado > 0 && tieneDespacho && avPct !== null && avPct < 30) {{
            alertas.push({{ tipo: "rojo", etapa: FAMILIA_LABELS[fam] || fam, msg: `Desp+Pago pero Insp ${{avPct}}% en ${{FAMILIA_LABELS[fam]}}` }});
        }}
        // ROJO: Inspeccion alta (>=70%) sin despacho registrado — datos inconsistentes
        else if (!tieneDespacho && avPct !== null && avPct >= 70 && etapasKeys.length > 0) {{
            alertas.push({{ tipo: "rojo", etapa: FAMILIA_LABELS[fam] || fam, msg: `Insp ${{avPct}}% pero sin despacho en ${{FAMILIA_LABELS[fam]}}` }});
        }}
        // NARANJA: Despacho sin pago en familia critica
        else if (tieneDespacho && totalPagado === 0 && FAMILIAS_CRITICAS.includes(fam)) {{
            alertas.push({{ tipo: "naranja", etapa: FAMILIA_LABELS[fam] || fam, msg: `Despacho sin pago M.O. en ${{FAMILIA_LABELS[fam]}}` }});
        }}
    }});

    // Alertas por solicitudes vencidas (solicitado hace mas de 14 dias sin despacho)
    Object.entries(estadoEtapas).forEach(([key, info]) => {{
        if (info.estado === "solicitado" && info.diasSolicitud > 14) {{
            alertas.push({{ tipo: "naranja", etapa: info.nombre, msg: `Solicitud hace ${{info.diasSolicitud}}d sin despacho` }});
        }}
    }});

    return alertas;
}};

const getUltimaEtapa = (estadoEtapas) => {{
    let ultima = null;
    SECUENCIA_PRINCIPAL.forEach(key => {{
        if (estadoEtapas[key]?.estado === "despachado") ultima = estadoEtapas[key];
    }});
    return ultima;
}};

const getProximaCritica = (estadoEtapas) => {{
    for (const key of SECUENCIA_PRINCIPAL) {{
        if (estadoEtapas[key]?.estado === "critico") return estadoEtapas[key];
    }}
    return null;
}};

const calcularAvance = (estadoEtapas) => {{
    const total = SECUENCIA_PRINCIPAL.length;
    const despachadas = SECUENCIA_PRINCIPAL.filter(k => estadoEtapas[k]?.estado === "despachado").length;
    return {{ despachadas, total, porcentaje: total > 0 ? Math.round((despachadas / total) * 100) : 0 }};
}};

const getEstadoGeneral = (estadoEtapas) => {{
    const estados = Object.values(estadoEtapas);
    if (estados.some(e => e.estado === "critico")) return "critico";
    if (estados.some(e => e.estado === "atencion")) return "atencion";
    return "en_tiempo";
}};

// ========== GRUPO COLORS & HELPERS ==========
const ACTIVIDADES_HAB = ["Empalme", "Pre-F1", "Desarme", "Escombros", "Aseo"];

const CONSULTAS_ETAPA = {{
    "02_1ERA_ETAPA": "Postes instalados?",
    "03_2DA_ETAPA": "TE1 solicitado?",
    "08_CERAMICO_MURO": "Empalme solicitado?",
    "13_GASFITERIA": "Accion Sanitaria?"
}};

const GRUPO_COLORS = [
    {{ bg:"bg-blue-50", border:"border-blue-200", text:"text-blue-700", accent:"bg-blue-500", light:"bg-blue-100", headerBg:"bg-blue-50", ring:"ring-blue-300" }},
    {{ bg:"bg-amber-50", border:"border-amber-200", text:"text-amber-700", accent:"bg-amber-500", light:"bg-amber-100", headerBg:"bg-amber-50", ring:"ring-amber-300" }},
    {{ bg:"bg-emerald-50", border:"border-emerald-200", text:"text-emerald-700", accent:"bg-emerald-500", light:"bg-emerald-100", headerBg:"bg-emerald-50", ring:"ring-emerald-300" }},
    {{ bg:"bg-rose-50", border:"border-rose-200", text:"text-rose-700", accent:"bg-rose-500", light:"bg-rose-100", headerBg:"bg-rose-50", ring:"ring-rose-300" }},
    {{ bg:"bg-violet-50", border:"border-violet-200", text:"text-violet-700", accent:"bg-violet-500", light:"bg-violet-100", headerBg:"bg-violet-50", ring:"ring-violet-300" }}
];

function agruparViviendas(viviendas, grupos) {{
    const sortByInicio = (a, b) => (a.primerDespacho || "9999").localeCompare(b.primerDespacho || "9999");
    if (!grupos || grupos.length === 0) {{
        const sorted = [...viviendas].sort(sortByInicio);
        return [{{ id:"_all", nombre:null, capataz:null, viviendas:sorted, colorIdx:-1 }}];
    }}
    const asignados = new Set();
    const result = grupos.map((g, idx) => {{
        const vivs = g.beneficiarios.map(bid => viviendas.find(v => String(v.ID_Benef) === String(bid))).filter(Boolean);
        vivs.sort(sortByInicio);
        vivs.forEach(v => asignados.add(String(v.ID_Benef)));
        return {{ id:g.id, nombre:g.nombre, capataz:g.capataz, viviendas:vivs, colorIdx:idx % GRUPO_COLORS.length }};
    }});
    const sinAsignar = viviendas.filter(v => !asignados.has(String(v.ID_Benef)));
    if (sinAsignar.length > 0) {{
        sinAsignar.sort(sortByInicio);
        result.push({{ id:"_sin_asignar", nombre:"Sin Asignar", capataz:null, viviendas:sinAsignar, colorIdx:-1 }});
    }}
    return result;
}}

function grupoResumen(vivs) {{
    const n = vivs.length;
    const avanceDesp = n ? Math.round(vivs.reduce((s,v) => s + v.avance.porcentaje, 0) / n) : 0;
    const conInsp = vivs.filter(v => getInspeccion(v.ID_Benef));
    const avanceInsp = conInsp.length ? Math.round(conInsp.reduce((s,v) => s + getInspeccion(v.ID_Benef).pct_total, 0) / conInsp.length) : 0;
    const criticas = vivs.filter(v => v.estadoGeneral === "critico").length;
    const terminadas = vivs.filter(v => {{
        const todasDesp = SECUENCIA_PRINCIPAL.every(k => v.estadoEtapas[k]?.estado === "despachado");
        const insp = getInspeccion(v.ID_Benef);
        return todasDesp && insp && insp.pct_total >= 90;
    }}).length;
    const habiles = vivs.filter(v => v.habil).length;
    return {{ n, avanceDesp, avanceInsp, criticas, terminadas, habiles }};
}}

// ========== ICONS ==========
const IconHome = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>;
const IconCheck = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M5 13l4 4L19 7" /></svg>;
const IconClock = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const IconAlert = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>;
const IconWarning = () => <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd"/></svg>;
const IconChevron = ({{open}}) => <svg className={{`w-4 h-4 transition-transform ${{open?"rotate-180":""}}`}} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M19 9l-7 7-7-7"/></svg>;
const IconChevronRight = () => <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M9 5l7 7-7 7" /></svg>;
const IconGrid = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>;
const IconUsers = () => <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>;
const IconEye = () => <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>;
const IconDollar = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
const IconSettings = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>;
const IconTrending = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>;
const IconSearch = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>;
const IconGroup = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>;
const IconDownload = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>;

// ========== CORE COMPONENTS ==========
const EstadoBadge = ({{ estado }}) => {{
    const colores = {{ critico: "bg-red-100 text-red-700", atencion: "bg-yellow-100 text-yellow-800", en_tiempo: "bg-green-100 text-green-700", despachado: "bg-blue-100 text-blue-700", solicitado: "bg-purple-100 text-purple-700", bloqueado: "bg-gray-100 text-gray-500" }};
    const labels = {{ critico: "CRITICO", atencion: "ATENCION", en_tiempo: "EN TIEMPO", despachado: "DESPACHADO", solicitado: "SOLICITADO", bloqueado: "BLOQUEADO" }};
    return <span className={{`px-2 py-0.5 rounded-full text-[10px] font-bold ${{colores[estado] || colores.bloqueado}}`}}>{{labels[estado] || estado}}</span>;
}};

const BarraProgreso = ({{ porcentaje }}) => (
    <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <div className={{`h-1.5 rounded-full transition-all ${{porcentaje >= 80 ? "bg-green-500" : porcentaje >= 50 ? "bg-blue-500" : porcentaje >= 25 ? "bg-yellow-500" : "bg-red-500"}}`}} style={{{{ width: `${{Math.min(porcentaje, 100)}}%` }}}} />
    </div>
);

const KPICard = ({{ titulo, valor, icono, color, subtitulo }}) => {{
    const colores = {{ blue: "border-blue-200", green: "border-green-200", yellow: "border-yellow-200", red: "border-red-200", violet: "border-violet-200", gray: "border-gray-200" }};
    const textColores = {{ blue: "text-blue-600", green: "text-green-600", yellow: "text-yellow-600", red: "text-red-600", violet: "text-violet-600", gray: "text-gray-600" }};
    return (
        <div className={{`bg-white border ${{colores[color] || colores.gray}} rounded-xl p-3 shadow-sm`}}>
            <div className="flex items-center gap-2 mb-1">
                <span className={{`${{textColores[color] || textColores.gray}}`}}>{{icono}}</span>
                <span className="text-[10px] text-gray-500 uppercase">{{titulo}}</span>
            </div>
            <p className={{`text-xl font-bold font-mono ${{textColores[color] || "text-gray-800"}}`}}>{{valor}}</p>
            {{subtitulo && <p className="text-[10px] text-gray-400 mt-0.5">{{subtitulo}}</p>}}
        </div>
    );
}};

const LineaTiempo = ({{ estadoEtapas, fechaHPC }}) => {{
    // Calcular Dia 0: fecha HPC, o si no existe, fecha fundacion
    const fundFecha = estadoEtapas["01_FUNDACIONES"]?.fechaDespacho;
    const dia0Str = fechaHPC || fundFecha || null;
    const dia0 = dia0Str ? new Date(dia0Str) : null;
    const hoy = new Date();
    const diasHoy = dia0 ? Math.floor((hoy - dia0) / (1000*60*60*24)) : null;

    // Calcular dias acumulados desde dia0 para cada etapa
    const diasAcum = {{}};
    const diasAcumSol = {{}};
    if (dia0) {{
        SECUENCIA_PRINCIPAL.forEach(key => {{
            const info = estadoEtapas[key];
            if (info?.estado === "despachado" && info.fechaDespacho) {{
                diasAcum[key] = Math.max(0, Math.floor((new Date(info.fechaDespacho) - dia0) / (1000*60*60*24)));
            }} else if (info?.estado === "solicitado" && info.fechaSolicitud) {{
                diasAcumSol[key] = Math.max(0, Math.floor((new Date(info.fechaSolicitud) - dia0) / (1000*60*60*24)));
            }}
        }});
    }}

    const colores = {{ despachado: "bg-blue-500 text-white", solicitado: "bg-purple-500 text-white", en_tiempo: "bg-green-50 text-green-700 border border-green-200", atencion: "bg-yellow-50 text-yellow-700 border border-yellow-200", critico: "bg-red-50 text-red-700 border border-red-200 pulse-soft", bloqueado: "bg-gray-100 text-gray-400 border border-gray-200" }};

    // Delta: diferencia con la etapa anterior despachada o solicitada
    const getAcumValue = (key) => diasAcum[key] ?? diasAcumSol[key] ?? null;
    const getDelta = (idx) => {{
        const curr = getAcumValue(SECUENCIA_PRINCIPAL[idx]);
        if (curr === null) return null;
        for (let j = idx - 1; j >= 0; j--) {{
            const prev = getAcumValue(SECUENCIA_PRINCIPAL[j]);
            if (prev !== null) return curr - prev;
        }}
        return curr;
    }};

    // Ultimo evento (despachado o solicitado) para calcular delta hasta HOY
    let ultimoAcum = null;
    for (let j = SECUENCIA_PRINCIPAL.length - 1; j >= 0; j--) {{
        const v = getAcumValue(SECUENCIA_PRINCIPAL[j]);
        if (v !== null) {{ ultimoAcum = v; break; }}
    }}
    const deltaHoy = (diasHoy !== null && ultimoAcum !== null) ? diasHoy - ultimoAcum : null;

    const formatFechaCorta = (iso) => {{ if (!iso) return ""; const p = iso.split("-"); return `${{p[2]}}/${{p[1]}}`; }};

    return (
        <div className="flex items-stretch gap-0 overflow-x-auto hide-scrollbar">
            {{/* HPC / Dia 0 */}}
            <div className={{`flex flex-col items-center rounded-l-lg px-2 py-1.5 ${{dia0 ? "bg-emerald-600 text-white" : "bg-gray-200 text-gray-500"}}`}} style={{{{minWidth:"56px"}}}}>
                <span className="text-[10px] font-bold">Dia 0</span>
                <span className="text-[9px] leading-tight text-center mt-0.5">{{fechaHPC ? "HPC" : fundFecha ? "Fund" : "---"}}</span>
            </div>
            {{SECUENCIA_PRINCIPAL.map((key, idx) => {{
                const info = estadoEtapas[key];
                const config = ETAPAS_CONFIG[key];
                const acum = diasAcum[key];
                const acumSol = diasAcumSol[key];
                const delta = getDelta(idx);

                return (
                    <React.Fragment key={{key}}>
                        {{/* Flecha con delta */}}
                        <div className="flex flex-col items-center justify-center px-0.5" style={{{{minWidth:"32px"}}}}>
                            <div className={{`h-0.5 w-full ${{info?.estado === "despachado" ? "bg-blue-400" : info?.estado === "solicitado" ? "bg-purple-300" : "bg-gray-200"}}`}} />
                            {{delta !== null && <span className="text-[8px] text-gray-400 font-mono mt-0.5">+{{delta}}d</span>}}
                        </div>
                        {{/* Etapa */}}
                        <div className={{`flex flex-col items-center px-2 py-1.5 ${{colores[info?.estado || "bloqueado"]}}`}} style={{{{minWidth:"68px"}}}} title={{acum !== undefined ? `Dia ${{acum}} desde inicio` : acumSol !== undefined ? `Solicitado dia ${{acumSol}} (${{formatFechaCorta(info?.fechaSolicitud)}})` : ""}}>
                            <span className="text-xs font-bold">
                                {{acum !== undefined ? `d${{acum}}` : acumSol !== undefined ? `d${{acumSol}}` : "\u2014"}}
                            </span>
                            <span className="text-[10px] leading-tight text-center mt-0.5">{{config?.nombre || key}}</span>
                            {{info?.estado === "solicitado" && <span className="text-[9px] opacity-75">{{formatFechaCorta(info.fechaSolicitud)}}</span>}}
                        </div>
                    </React.Fragment>
                );
            }})}}
            {{/* HOY */}}
            {{diasHoy !== null && (
                <React.Fragment>
                    <div className="flex flex-col items-center justify-center px-0.5" style={{{{minWidth:"32px"}}}}>
                        <div className="h-0.5 w-full bg-gray-300" style={{{{backgroundImage:"repeating-linear-gradient(90deg, #d1d5db 0, #d1d5db 4px, transparent 4px, transparent 8px)"}}}} />
                        {{deltaHoy !== null && deltaHoy > 0 && <span className="text-[8px] text-gray-400 font-mono mt-0.5">+{{deltaHoy}}d</span>}}
                    </div>
                    <div className="flex flex-col items-center rounded-r-lg px-2 py-1.5 bg-gray-700 text-white" style={{{{minWidth:"56px"}}}}>
                        <span className="text-[10px] font-bold">d{{diasHoy}}</span>
                        <span className="text-[9px] leading-tight text-center mt-0.5">HOY</span>
                    </div>
                </React.Fragment>
            )}}
        </div>
    );
}};

// ===== VIVIENDA CARD =====
const ViviendaCard = ({{ beneficiario, estadoEtapas, expanded, onToggle, grupoColor, obsCount, observaciones, addObservacion, deleteObservacion, actividades, toggleActividad, consultas, toggleConsulta }}) => {{
    const [obsTexto, setObsTexto] = React.useState("");
    const [showObsInput, setShowObsInput] = React.useState(false);
    const b = beneficiario;
    const avance = b.avance || calcularAvance(estadoEtapas);
    const insp = getInspeccion(b.ID_Benef);
    const totalPagado = getTotalPagado(b.ID_Benef);
    const alertas = calcCoherencia(b.ID_Benef, estadoEtapas);
    const alertasRojas = alertas.filter(a => a.tipo === "rojo");
    const alertasNaranjas = alertas.filter(a => a.tipo === "naranja");
    const ultima = getUltimaEtapa(estadoEtapas);
    const proximaCritica = getProximaCritica(estadoEtapas);
    const solicitadas = Object.entries(estadoEtapas).filter(([,e]) => e.estado === "solicitado");
    const estadoGeneral = b.estadoGeneral || getEstadoGeneral(estadoEtapas);

    const borderClass = alertasRojas.length > 0 ? "border-l-4 border-l-red-500 border-red-200" : estadoGeneral === "critico" ? "border-l-4 border-l-red-500 border-red-100" : estadoGeneral === "atencion" ? "border-l-4 border-l-yellow-500 border-yellow-100" : "border border-gray-200";
    const gc = grupoColor >= 0 ? GRUPO_COLORS[grupoColor] : null;

    return (
        <div className={{`bg-white ${{borderClass}} rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow ${{gc ? `ring-1 ${{gc.ring}}` : ""}}`}}>
            <div className="p-4 cursor-pointer hover:bg-gray-50/80 transition-colors" onClick={{onToggle}}>
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                        <span className="text-gray-400"><IconChevron open={{expanded}} /></span>
                        {{gc && <div className={{`w-1.5 h-10 rounded-full ${{gc.accent}}`}} />}}
                        <span className={{b.tipologia === "Casa + RC" ? "text-blue-600" : "text-gray-400"}}><IconHome /></span>
                        <div>
                            <h3 className="font-semibold text-gray-800">{{b.NOMBRES}} {{b.APELLIDOS}} {{obsCount > 0 && <span className="ml-1 inline-flex items-center gap-0.5 text-[9px] bg-amber-100 text-amber-700 border border-amber-300 rounded px-1 py-0.5 font-medium align-middle cursor-pointer" title={{`${{obsCount}} observacion(es)`}} onClick={{(e) => {{ e.stopPropagation(); if (!expanded) onToggle(); }}}}>&#9998; {{obsCount}}</span>}} {{b.habil ? <span className="ml-1 text-[9px] bg-green-100 text-green-700 border border-green-300 rounded px-1 py-0.5 font-medium align-middle">Habil para Construir</span> : <span className="ml-1 text-[9px] bg-red-100 text-red-600 border border-red-300 rounded px-1 py-0.5 font-medium align-middle">No Habilitada</span>}}</h3>
                            <p className="text-xs text-gray-500">{{b.tipologia}}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="text-right">
                            <div className="flex items-center gap-2 mb-0.5">
                                <span className="text-[10px] text-gray-400 w-8 font-mono">Desp</span>
                                <span className="text-xs text-gray-500">{{avance.despachadas}}/{{avance.total}}</span>
                                <span className="text-sm font-bold text-gray-700">{{avance.porcentaje}}%</span>
                            </div>
                            <div className="flex items-center gap-2 mb-0.5">
                                <span className="text-[10px] text-gray-400 w-8 font-mono">Insp</span>
                                <span className={{`text-sm font-bold ${{insp ? (insp.pct_total >= 90 ? "text-green-600" : insp.pct_total >= 50 ? "text-blue-600" : "text-orange-500") : "text-gray-300"}}`}}>{{insp ? insp.pct_total + "%" : "\u2014"}}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-[10px] text-gray-400 w-8 font-mono">Pago</span>
                                <span className={{`text-sm font-bold ${{totalPagado > 0 ? "text-violet-600" : "text-gray-300"}}`}}>{{totalPagado > 0 ? formatPeso(totalPagado) : "\u2014"}}</span>
                            </div>
                            <div className="w-32 space-y-0.5 mt-1">
                                <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden"><div className="triple-bar bg-blue-500" style={{{{width:`${{avance.porcentaje}}%`}}}} /></div>
                                <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden"><div className="triple-bar bg-emerald-500" style={{{{width:`${{insp ? insp.pct_total : 0}}%`}}}} /></div>
                                <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden"><div className="triple-bar bg-violet-500" style={{{{width:`${{Math.min(avance.porcentaje, 100)}}%`}}}} /></div>
                            </div>
                            <div className="flex gap-0.5 mt-1.5" onClick={{(e) => e.stopPropagation()}}>
                                {{ACTIVIDADES_HAB.map(act => {{
                                    const done = actividades && actividades[act];
                                    return (
                                        <button key={{act}} onClick={{() => toggleActividad(b.ID_Benef, act)}} className={{`w-6 h-6 rounded text-[7px] leading-tight font-bold border transition-all flex items-center justify-center ${{done ? "bg-green-500 text-white border-green-600 shadow-sm" : "bg-gray-100 text-gray-400 border-gray-200 hover:border-gray-400 hover:bg-gray-200"}}`}} title={{done ? `${{act}}: Terminado (${{done.fecha.replace('T', ' ')}})` : `${{act}}: Pendiente — Click para marcar`}}>
                                            {{done ? "\u2713" : act.substring(0, 2)}}
                                        </button>
                                    );
                                }})}}
                            </div>
                        </div>
                        <div className="flex flex-col items-center gap-1">
                            <EstadoBadge estado={{estadoGeneral}} />
                            {{alertasRojas.length > 0 && <span className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600 bg-red-50 border border-red-200 rounded-full px-1.5 py-0.5 pulse-soft"><IconWarning /> {{alertasRojas.length}}</span>}}
                            {{alertasRojas.length === 0 && alertasNaranjas.length > 0 && <span className="inline-flex items-center gap-1 text-[10px] font-bold text-orange-600 bg-orange-50 border border-orange-200 rounded-full px-1.5 py-0.5">{{alertasNaranjas.length}}</span>}}
                        </div>
                    </div>
                </div>
                <LineaTiempo estadoEtapas={{estadoEtapas}} fechaHPC={{b.fecha_hpc}} />
                <div className="mt-3 flex items-center justify-between text-sm">
                    <div className="text-gray-500">
                        {{ultima ? <span>Ultima: <span className="text-gray-700 font-medium">{{ultima.nombre}}</span> \u2014 {{ultima.guia ? `#${{ultima.guia}}` : ""}} \u2014 <span className={{estadoGeneral === "critico" ? "text-red-600 font-medium" : estadoGeneral === "atencion" ? "text-yellow-600" : "text-green-600"}}>{{ultima.diasTranscurridos}}d</span></span> : <span className="text-yellow-600">Sin despachos registrados</span>}}
                    </div>
                    <div className="flex items-center gap-3">
                        {{insp && <div className="flex items-center gap-1"><IconEye /><span className={{insp.pct_total >= 90 ? "text-green-600" : insp.pct_total >= 50 ? "text-blue-600" : "text-orange-500"}}>Insp: {{insp.pct_total}}%</span></div>}}
                        {{solicitadas.length > 0 && <span className="text-[10px] bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full border border-purple-200">{{solicitadas.length}} solicitada{{solicitadas.length > 1 ? "s" : ""}}</span>}}
                    </div>
                </div>
                {{alertasRojas.length > 0 && <div className="mt-3 p-2 bg-red-50 border border-red-300 rounded-lg">{{alertasRojas.map((a,i) => <div key={{i}} className="flex items-center gap-2 text-red-700 text-sm"><span className="pulse-soft"><IconWarning /></span><span><strong>{{a.etapa}}:</strong> {{a.msg}}</span></div>)}}</div>}}
                {{alertasRojas.length === 0 && alertasNaranjas.length > 0 && <div className="mt-2 p-2 bg-orange-50 border border-orange-200 rounded-lg">{{alertasNaranjas.slice(0,2).map((a,i) => <div key={{i}} className="flex items-center gap-2 text-orange-600 text-sm"><IconWarning /><span><strong>{{a.etapa}}:</strong> {{a.msg}}</span></div>)}}</div>}}
                {{estadoGeneral === "critico" && proximaCritica && alertasRojas.length === 0 && <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-lg"><div className="flex items-center gap-2 text-red-600 text-sm"><span className="pulse-soft"><IconWarning /></span><span><strong>{{proximaCritica.nombre}}</strong> atrasado {{proximaCritica.diasTranscurridos}} dias</span></div></div>}}
            </div>
            {{expanded && (
                <div className="border-t border-gray-100 p-4 bg-gray-50">
                    <h4 className="text-sm font-medium text-gray-700 mb-3">Detalle de Etapas (dias desde inicio)</h4>
                    {{(() => {{
                        const fundFecha = estadoEtapas["01_FUNDACIONES"]?.fechaDespacho;
                        const dia0Str = b.fecha_hpc || fundFecha || null;
                        const dia0 = dia0Str ? new Date(dia0Str) : null;
                        const diasAcumDet = {{}};
                        if (dia0) {{
                            SECUENCIA_PRINCIPAL.forEach(key => {{
                                const inf = estadoEtapas[key];
                                if (inf?.estado === "despachado" && inf.fechaDespacho) {{
                                    diasAcumDet[key] = Math.max(0, Math.floor((new Date(inf.fechaDespacho) - dia0) / (1000*60*60*24)));
                                }}
                            }});
                        }}
                        const getDeltaDet = (idx) => {{
                            const curr = diasAcumDet[SECUENCIA_PRINCIPAL[idx]];
                            if (curr === undefined) return null;
                            for (let j = idx - 1; j >= 0; j--) {{
                                const prev = diasAcumDet[SECUENCIA_PRINCIPAL[j]];
                                if (prev !== undefined) return curr - prev;
                            }}
                            return curr;
                        }};
                        const formatFechaDet = (iso) => {{ if (!iso) return ""; const [y,m,d] = iso.split("-"); return `${{d}}/${{m}}`; }};
                        return (
                            <div className="space-y-1.5 mb-4">
                                <div className="flex items-center gap-3 text-sm mb-2 pb-2 border-b border-gray-200">
                                    <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-bold shadow">0</div>
                                    <span className="text-gray-700 flex-1 font-medium">{{b.fecha_hpc ? "Habilitacion para Construir" : fundFecha ? "Fundacion (sin fecha HPC)" : "Sin fecha de inicio"}}</span>
                                    <span className="text-emerald-600 font-mono text-xs">{{dia0Str ? formatFechaDet(dia0Str) : "\u2014"}} \u2014 Dia 0</span>
                                </div>
                                {{SECUENCIA_PRINCIPAL.map((key, idx) => {{
                                    const info = estadoEtapas[key];
                                    const config = ETAPAS_CONFIG[key];
                                    const coloresChip = {{ despachado: "bg-blue-500", solicitado: "bg-purple-500", en_tiempo: "bg-green-500", atencion: "bg-yellow-500", critico: "bg-red-500 pulse-soft", bloqueado: "bg-gray-300" }};
                                    const acum = diasAcumDet[key];
                                    const delta = getDeltaDet(idx);
                                    const consultaTexto = CONSULTAS_ETAPA[key];
                                    const consDone = consultaTexto && consultas && consultas[key];
                                    return (
                                        <div key={{key}} className="flex items-center gap-3 text-sm">
                                            <div className={{`w-8 h-8 rounded-full ${{coloresChip[info?.estado || "bloqueado"]}} flex items-center justify-center text-white text-xs font-bold shadow`}}>{{info?.estado === "solicitado" ? "S" : config?.codigo || "?"}}</div>
                                            <span className="text-gray-700 flex-1">
                                                {{config?.nombre || key}}
                                                {{consultaTexto && info?.estado === "despachado" && (
                                                    <button onClick={{(e) => {{ e.stopPropagation(); toggleConsulta(b.ID_Benef, key); }}}} className={{`ml-2 inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full border cursor-pointer transition-all ${{consDone ? "bg-green-100 text-green-700 border-green-300" : "bg-orange-100 text-orange-700 border-orange-300 pulse-soft"}}`}} title={{consDone ? `${{consultaTexto}} Hecho (${{consDone.fecha.replace('T', ' ')}})` : `${{consultaTexto}} — Click para marcar`}}>
                                                        {{consDone ? "\u2713" : "\u26A0"}} {{consultaTexto}}
                                                    </button>
                                                )}}
                                            </span>
                                            <span className="text-gray-500 flex items-center gap-2">
                                                {{info?.estado === "despachado" && (
                                                    <span className="flex items-center gap-2">
                                                        <span className="text-[10px] text-gray-400">{{formatFechaDet(info.fechaDespacho)}}</span>
                                                        {{delta !== null && <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-200 font-mono">+{{delta}}d</span>}}
                                                        <span className="font-mono font-bold text-blue-700">d{{acum}}</span>
                                                        {{info.guia && <span className="text-[10px] text-gray-400">#{{info.guia}}</span>}}
                                                    </span>
                                                )}}
                                                {{info?.estado === "solicitado" && <span className="text-purple-600">Solicitado hace {{info.diasSolicitud}}d</span>}}
                                                {{info?.estado === "critico" && <span className="text-red-600">Esperando {{info.diasTranscurridos}}d</span>}}
                                                {{info?.estado === "atencion" && <span className="text-yellow-600">Esperando {{info.diasTranscurridos}}d</span>}}
                                                {{info?.estado === "en_tiempo" && <span className="text-green-600">Esperando {{info.diasTranscurridos}}d</span>}}
                                                {{info?.estado === "bloqueado" && "Pendiente"}}
                                            </span>
                                </div>
                            );
                        }})}}
                            </div>
                        );
                    }})()}}
                    {{/* Inspecciones */}}
                    {{insp ? (
                        <div className="mt-4 pt-4 border-t border-gray-200">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">Avance por Inspecciones</h4>
                            <div className="flex items-center gap-4 text-xs text-gray-500 mb-2">
                                <span>Viv (70%): <strong className="text-gray-700">{{insp.pct_viv}}%</strong></span>
                                <span>RC (25%): <strong className="text-gray-700">{{insp.pct_rc}}%</strong></span>
                                <span>Hab (5%): <strong className="text-gray-700">{{insp.pct_hab}}%</strong></span>
                                <span>Total: <strong className={{insp.pct_total >= 90 ? "text-green-600" : "text-blue-600"}}>{{insp.pct_total}}%</strong></span>
                            </div>
                            <div className="grid grid-cols-7 sm:grid-cols-14 gap-1">
                                {{Object.entries(insp.partidas || {{}}).map(([nombre, valor]) => (
                                    <div key={{nombre}} className={{`text-center rounded p-1 ${{valor >= 100 ? "bg-green-100 text-green-700 border border-green-200" : valor > 0 ? "bg-yellow-50 text-yellow-700 border border-yellow-200" : "bg-gray-50 text-gray-400 border border-gray-200"}}`}} title={{`${{nombre}}: ${{valor}}%`}}>
                                        <div className="font-mono text-[9px] leading-tight">{{nombre}}</div>
                                        <div className="font-bold text-[10px]">{{valor}}%</div>
                                    </div>
                                ))}}
                            </div>
                            {{insp.cierre && Object.keys(insp.cierre).length > 0 && (
                                <div className="mt-3 flex items-center gap-2 text-xs">
                                    <span className="text-gray-500 font-medium">Cierre:</span>
                                    {{Object.entries(insp.cierre).map(([label, done]) => (
                                        <span key={{label}} className={{`inline-flex items-center justify-center w-5 h-5 rounded text-[9px] font-bold ${{done ? "bg-green-500 text-white" : "bg-red-100 text-red-400 border border-red-200"}}`}}>{{label}}</span>
                                    ))}}
                                </div>
                            )}}
                        </div>
                    ) : <div className="mt-4 pt-4 border-t border-gray-200"><p className="text-xs text-gray-400">Sin registros de inspeccion</p></div>}}
                    {{/* Pagos por Familia */}}
                    {{(() => {{
                        const pagosFam = getPagosPorFamilia(b.ID_Benef);
                        const entries = Object.entries(pagosFam).filter(([,d]) => d.total > 0).sort((a,b) => b[1].total - a[1].total);
                        if (entries.length === 0) return null;
                        return (
                            <div className="mt-4 pt-3 border-t border-gray-200">
                                <h4 className="text-sm font-medium text-gray-700 mb-2">Pagos por Familia</h4>
                                <table className="w-full text-sm"><thead><tr className="text-left text-gray-500 border-b border-gray-200 bg-white"><th className="py-1.5 px-2 text-xs">Familia</th><th className="py-1.5 px-2 text-xs text-right">Total</th><th className="py-1.5 px-2 text-xs text-center">#</th><th className="py-1.5 px-2 text-xs">Maestro</th></tr></thead>
                                <tbody>{{entries.map(([fam, data]) => (
                                    <tr key={{fam}} className="border-b border-gray-100"><td className="py-1.5 px-2 font-medium text-gray-700">{{fam}}</td><td className="py-1.5 px-2 text-right font-mono font-bold text-violet-700">{{formatPeso(data.total)}}</td><td className="py-1.5 px-2 text-center text-gray-500">{{data.count}}</td><td className="py-1.5 px-2 text-gray-500 text-xs">{{[...data.maestros].join(", ")}}</td></tr>
                                ))}}</tbody></table>
                            </div>
                        );
                    }})()}}
                    {{/* 4. Observaciones Criticas */}}
                    <div className="mt-4 pt-3 border-t border-gray-200">
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-sm font-medium text-gray-700">Observaciones Criticas</h4>
                            <button onClick={{(e) => {{ e.stopPropagation(); setShowObsInput(!showObsInput); }}}} className="text-[10px] px-2 py-1 bg-amber-50 text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100 font-medium">+ Agregar</button>
                        </div>
                        {{showObsInput && (
                            <div className="flex gap-2 mb-3">
                                <input type="text" value={{obsTexto}} onChange={{(e) => setObsTexto(e.target.value)}} onKeyDown={{(e) => {{ if (e.key === 'Enter' && obsTexto.trim()) {{ addObservacion(b.ID_Benef, obsTexto.trim()); setObsTexto(""); setShowObsInput(false); }} }}}} placeholder="Escribir observacion..." className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-amber-400 focus:border-amber-400 focus:outline-none" autoFocus />
                                <button onClick={{() => {{ if (obsTexto.trim()) {{ addObservacion(b.ID_Benef, obsTexto.trim()); setObsTexto(""); setShowObsInput(false); }} }}}} className="px-3 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-medium hover:bg-amber-600">Guardar</button>
                            </div>
                        )}}
                        {{observaciones && observaciones.length > 0 ? (
                            <div className="space-y-2">
                                {{observaciones.map(obs => (
                                    <div key={{obs.id}} className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-2.5">
                                        <span className="text-amber-500 mt-0.5">&#9998;</span>
                                        <div className="flex-1">
                                            <p className="text-sm text-gray-700">{{obs.texto}}</p>
                                            <p className="text-[10px] text-gray-400 mt-1">{{obs.fecha.replace('T', ' ')}}</p>
                                        </div>
                                        <button onClick={{() => deleteObservacion(b.ID_Benef, obs.id)}} className="text-red-400 hover:text-red-600 text-xs px-1" title="Eliminar">&times;</button>
                                    </div>
                                ))}}
                            </div>
                        ) : (
                            <p className="text-xs text-gray-400">Sin observaciones registradas</p>
                        )}}
                    </div>
                </div>
            )}}
        </div>
    );
}};

// ===== HEADER PROYECTO =====
const HeaderProyecto = ({{ proy, garantiasProy, eeppResumen }}) => {{
    if (!proy) return null;
    const contratoInfo = React.useMemo(() => {{
        const fi = proy.fecha_inicio;
        const dur = proy.duracion;
        if (!fi || !dur) return null;
        const inicio = new Date(fi);
        const vencimiento = new Date(inicio);
        vencimiento.setDate(vencimiento.getDate() + dur);
        const hoy = new Date();
        const diasRestantes = Math.floor((vencimiento - hoy) / (1000*60*60*24));
        return {{ inicio: fi, duracion: dur, vencimiento: vencimiento.toISOString().substring(0,10), diasRestantes }};
    }}, [proy]);

    const formatFecha = (iso) => {{ if (!iso) return "\u2014"; const [y,m,d] = iso.split("-"); return `${{d}}/${{m}}/${{y}}`; }};
    const formatUF = (val) => {{ if (!val && val !== 0) return "\u2014"; return val.toLocaleString("es-CL", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + " UF"; }};

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            {{contratoInfo && (
                <div className={{`bg-white border rounded-lg p-3 shadow-sm ${{contratoInfo.diasRestantes < 0 ? "border-red-300 bg-red-50" : contratoInfo.diasRestantes < 30 ? "border-yellow-300 bg-yellow-50" : "border-gray-200"}}`}}>
                    <div className="flex items-center gap-2 mb-2">
                        <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Contrato</span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-xs">
                        <div><p className="text-gray-400">Inicio</p><p className="font-semibold text-gray-700">{{formatFecha(contratoInfo.inicio)}}</p></div>
                        <div><p className="text-gray-400">Plazo</p><p className="font-semibold text-gray-700">{{contratoInfo.duracion}} dias</p></div>
                        <div><p className="text-gray-400">Vencimiento</p><p className="font-semibold text-gray-700">{{formatFecha(contratoInfo.vencimiento)}}</p></div>
                        <div><p className="text-gray-400">Estado</p>
                            {{contratoInfo.diasRestantes < 0 ? <p className="font-bold text-red-600">VENCIDO ({{Math.abs(contratoInfo.diasRestantes)}}d)</p> :
                             contratoInfo.diasRestantes < 30 ? <p className="font-bold text-yellow-600">{{contratoInfo.diasRestantes}}d restantes</p> :
                             <p className="font-semibold text-green-600">{{contratoInfo.diasRestantes}}d restantes</p>}}
                        </div>
                    </div>
                </div>
            )}}
            {{garantiasProy.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                    <div className="flex items-center gap-2 mb-2">
                        <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Garantias</span>
                    </div>
                    <div className="space-y-1.5">
                        {{garantiasProy.map((g, i) => {{
                            const esV = g.diasVcmto !== null && g.diasVcmto < 0;
                            const porV = g.diasVcmto !== null && g.diasVcmto >= 0 && g.diasVcmto < 60;
                            const tipoCorto = g.tipo.includes("Fiel") ? "Fiel Cumpl." : g.tipo.includes("Buena") ? "Buena Ejec." : g.tipo;
                            return (
                                <div key={{i}} className={{`flex items-center justify-between text-xs px-2 py-1 rounded ${{esV ? "bg-red-50 text-red-700" : porV ? "bg-yellow-50 text-yellow-700" : "bg-gray-50 text-gray-600"}}`}}>
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium">{{tipoCorto}}</span>
                                        <span className="text-gray-400">{{g.tipo1}} #{{g.num_bol}}</span>
                                        {{g.monto_uf > 0 && <span className="text-gray-400">UF {{g.monto_uf.toLocaleString()}}</span>}}
                                    </div>
                                    <div className="font-semibold">
                                        {{g.diasVcmto === null ? "Sin fecha" : esV ? `VENCIDA (${{Math.abs(g.diasVcmto)}}d)` : porV ? `${{g.diasVcmto}}d` : formatFecha(g.fecha_vcmto)}}
                                    </div>
                                </div>
                            );
                        }})}}
                    </div>
                </div>
            )}}
            <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                    <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
                    <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Estados de Pago</span>
                </div>
                {{eeppResumen.total > 0 ? (
                    <div>
                        <div className="flex rounded-full h-5 overflow-hidden mb-2">
                            {{eeppResumen.pagado > 0 && <div className="bg-green-500 flex items-center justify-center text-[9px] font-bold text-white" style={{{{width:`${{(eeppResumen.pagado/eeppResumen.total*100).toFixed(0)}}%`}}}}>{{(eeppResumen.pagado/eeppResumen.total*100).toFixed(0)}}%</div>}}
                            {{eeppResumen.ingresado > 0 && <div className="bg-yellow-400" style={{{{width:`${{(eeppResumen.ingresado/eeppResumen.total*100).toFixed(0)}}%`}}}}></div>}}
                            {{eeppResumen.preparacion > 0 && <div className="bg-gray-300" style={{{{width:`${{(eeppResumen.preparacion/eeppResumen.total*100).toFixed(0)}}%`}}}}></div>}}
                        </div>
                        <div className="grid grid-cols-3 gap-1 text-[10px]">
                            <div><span className="text-green-600 font-semibold">Pagado</span><br/><span className="font-mono font-bold text-gray-700">{{formatUF(eeppResumen.pagado)}}</span></div>
                            <div><span className="text-yellow-600 font-semibold">Ingresado</span><br/><span className="font-mono font-bold text-gray-700">{{formatUF(eeppResumen.ingresado)}}</span></div>
                            <div><span className="text-gray-500 font-semibold">Total</span><br/><span className="font-mono font-bold text-gray-700">{{formatUF(eeppResumen.total)}}</span></div>
                        </div>
                    </div>
                ) : <p className="text-gray-400 text-xs">Sin EP registrados</p>}}
            </div>
        </div>
    );
}};

// ===== GRUPO HEADER =====
const GrupoHeader = ({{ grupo, colorIdx, open, onToggle }}) => {{
    if (!grupo.nombre) return null;
    const c = colorIdx >= 0 ? GRUPO_COLORS[colorIdx] : {{ bg:"bg-gray-50", border:"border-gray-200", text:"text-gray-600", accent:"bg-gray-400" }};
    const res = grupoResumen(grupo.viviendas);
    return (
        <div className={{`${{c.bg}} border ${{c.border}} rounded-xl p-3 cursor-pointer hover:shadow-sm transition-shadow`}} onClick={{onToggle}}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className={{`w-8 h-8 ${{c.accent}} rounded-lg flex items-center justify-center`}}>
                        <span className="text-white text-xs font-bold">{{grupo.nombre.replace("Grupo ","G")}}</span>
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className={{`text-sm font-bold ${{c.text}}`}}>{{grupo.nombre}}</h3>
                            {{grupo.capataz && <span className="text-xs text-gray-500">\u2014 Capataz: <strong className="text-gray-700">{{grupo.capataz}}</strong></span>}}
                        </div>
                        <div className="flex items-center gap-4 text-[10px] text-gray-500 mt-0.5">
                            <span>{{res.n}} viviendas</span>
                            <span>HPC: <strong className={{res.habiles === res.n ? "text-green-600" : "text-orange-600"}}>{{res.habiles}}/{{res.n}}</strong></span>
                            <span>Desp: <strong className="text-blue-600">{{res.avanceDesp}}%</strong></span>
                            <span>Insp: <strong className="text-emerald-600">{{res.avanceInsp}}%</strong></span>
                            {{res.criticas > 0 && <span className="text-red-600 font-semibold">{{res.criticas}} criticas</span>}}
                            {{res.terminadas > 0 && <span className="text-green-600">{{res.terminadas}} terminadas</span>}}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="w-24 space-y-0.5">
                        <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden"><div className="h-full rounded-full bg-blue-500" style={{{{width:`${{res.avanceDesp}}%`}}}} /></div>
                        <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden"><div className="h-full rounded-full bg-emerald-500" style={{{{width:`${{res.avanceInsp}}%`}}}} /></div>
                    </div>
                    <IconChevron open={{open}} />
                </div>
            </div>
        </div>
    );
}};

// ===== VIVIENDAS TAB =====
const ViviendasTab = ({{ viviendas, grupos, expandida, setExpandida, filtro, setFiltro, busqueda, setBusqueda, observaciones, addObservacion, deleteObservacion, showResumenObs, setShowResumenObs, actividades, toggleActividad, consultas, toggleConsulta }}) => {{
    const criticas = viviendas.filter(v => v.estadoGeneral === "critico").length;
    const atencion_ = viviendas.filter(v => v.estadoGeneral === "atencion").length;
    const enTiempo = viviendas.filter(v => v.estadoGeneral === "en_tiempo").length;

    const vivFiltradas = React.useMemo(() => {{
        return viviendas.filter(v => {{
            if (busqueda && !`${{v.NOMBRES}} ${{v.APELLIDOS}}`.toLowerCase().includes(busqueda.toLowerCase())) return false;
            if (filtro !== "todos" && v.estadoGeneral !== filtro) return false;
            return true;
        }});
    }}, [viviendas, busqueda, filtro]);

    const gruposData = agruparViviendas(vivFiltradas, grupos);
    const [gruposAbiertos, setGruposAbiertos] = React.useState({{}});
    const toggleGrupo = (gid) => setGruposAbiertos(prev => ({{...prev, [gid]: prev[gid] === false ? true : false}}));

    return (
        <div>
            <div className="flex items-center gap-2 mb-4 flex-wrap">
                {{[["todos","Todas",viviendas.length],["critico","Criticas",criticas],["atencion","Atencion",atencion_],["en_tiempo","En Tiempo",enTiempo]].map(([k,l,c]) =>
                    <button key={{k}} onClick={{() => setFiltro(k)}} className={{`px-3 py-1.5 rounded-lg text-xs font-medium ${{filtro===k ? "bg-violet-600 text-white shadow-sm" : "bg-white text-gray-500 border border-gray-200 hover:border-gray-300"}}`}}>{{l}} <span className="ml-1 opacity-60">{{c}}</span></button>
                )}}
                <button onClick={{() => setShowResumenObs("obs")}} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-50 text-amber-700 border border-amber-300 hover:bg-amber-100 flex items-center gap-1" title="Ver resumen general">&#9998; Resumen</button>
                <div className="relative ml-auto">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"><IconSearch /></span>
                    <input type="text" placeholder="Buscar beneficiario..." value={{busqueda}} onChange={{(e) => setBusqueda(e.target.value)}}
                        className="w-56 bg-white border border-gray-200 rounded-lg pl-10 pr-4 py-1.5 text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500 focus:outline-none" />
                </div>
            </div>
            {{/* Modal Resumen con 3 tabs */}}
            {{showResumenObs && (() => {{
                const [resTab, setResTab] = [showResumenObs, setShowResumenObs];
                const actualTab = typeof resTab === "string" ? resTab : "obs";
                const setActualTab = (t) => setResTab(t || true);
                const closeModal = () => setResTab(false);

                // IDs del proyecto actual
                const vivIds = new Set(viviendas.map(v => String(v.ID_Benef)));

                // Consultas gatilladas: recorrer viviendas y ver cuales tienen etapas despachadas con consulta
                const consultasData = viviendas.flatMap(v => {{
                    const estados = v.estadoEtapas || {{}};
                    return Object.entries(CONSULTAS_ETAPA).filter(([etKey]) => estados[etKey]?.estado === "despachado").map(([etKey, pregunta]) => {{
                        const done = consultas[v.ID_Benef] && consultas[v.ID_Benef][etKey];
                        return {{ idBenef: v.ID_Benef, nombre: `${{v.NOMBRES}} ${{v.APELLIDOS}}`, etapa: ETAPAS_CONFIG[etKey]?.nombre || etKey, pregunta, done, etKey }};
                    }});
                }});
                const consPendientes = consultasData.filter(c => !c.done);
                const consHechas = consultasData.filter(c => c.done);

                // Actividades 5%: recorrer viviendas
                const actData = viviendas.map(v => {{
                    const benActs = actividades[v.ID_Benef] || {{}};
                    const hechas = ACTIVIDADES_HAB.filter(a => benActs[a]);
                    const pendientes = ACTIVIDADES_HAB.filter(a => !benActs[a]);
                    return {{ idBenef: v.ID_Benef, nombre: `${{v.NOMBRES}} ${{v.APELLIDOS}}`, benActs, hechas, pendientes, pct: hechas.length }};
                }});
                const actConAlgo = actData.filter(a => a.hechas.length > 0);
                const actCompletas = actData.filter(a => a.hechas.length === 5);
                const actParciales = actData.filter(a => a.hechas.length > 0 && a.hechas.length < 5);

                // Observaciones filtradas por proyecto
                const obsProy = Object.entries(observaciones).filter(([id, obs]) => vivIds.has(String(id)) && obs.length > 0);

                const tabBtns = [
                    ["obs", `Observaciones (${{obsProy.length}})`],
                    ["cons", `Consultas (${{consPendientes.length}} pend.)`],
                    ["act5", `Actividades 5% (${{actCompletas.length}}/${{viviendas.length}})`]
                ];

                return (
                    <div className="fixed inset-0 bg-black/40 z-[100] flex items-center justify-center p-4" onClick={{closeModal}}>
                        <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col" onClick={{(e) => e.stopPropagation()}}>
                            <div className="sticky top-0 bg-white border-b border-gray-200 px-5 py-3 flex items-center justify-between rounded-t-xl z-10">
                                <h3 className="text-lg font-bold text-gray-800">Resumen</h3>
                                <button onClick={{closeModal}} className="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
                            </div>
                            <div className="flex border-b border-gray-200 bg-gray-50 px-5">
                                {{tabBtns.map(([k, label]) => (
                                    <button key={{k}} onClick={{() => setActualTab(k)}} className={{`px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${{actualTab === k ? "border-violet-600 text-violet-700 bg-white" : "border-transparent text-gray-500 hover:text-gray-700"}}`}}>{{label}}</button>
                                ))}}
                            </div>
                            <div className="flex-1 overflow-y-auto p-5">
                                {{/* Tab Observaciones */}}
                                {{actualTab === "obs" && (
                                    <div className="space-y-3">
                                        {{obsProy.map(([idBenef, obs]) => {{
                                            const v = viviendas.find(vv => String(vv.ID_Benef) === String(idBenef));
                                            const nombre = v ? `${{v.NOMBRES}} ${{v.APELLIDOS}}` : idBenef;
                                            return (
                                                <div key={{idBenef}} className="border border-amber-200 rounded-lg overflow-hidden">
                                                    <div className="bg-amber-50 px-4 py-2 border-b border-amber-200">
                                                        <span className="font-semibold text-gray-800 text-sm">{{nombre}}</span>
                                                        <span className="text-[10px] text-gray-400 ml-2">{{obs.length}} obs.</span>
                                                    </div>
                                                    <div className="p-3 space-y-1.5">
                                                        {{obs.map(o => (
                                                            <div key={{o.id}} className="flex items-start gap-2 text-sm">
                                                                <span className="text-amber-400 mt-0.5">&#8226;</span>
                                                                <span className="text-gray-700 flex-1">{{o.texto}}</span>
                                                                <span className="text-[10px] text-gray-400 whitespace-nowrap">{{o.fecha.replace('T', ' ')}}</span>
                                                            </div>
                                                        ))}}
                                                    </div>
                                                </div>
                                            );
                                        }})}}
                                        {{obsProy.length === 0 && <p className="text-gray-400 text-center py-8">Sin observaciones en este proyecto</p>}}
                                    </div>
                                )}}
                                {{/* Tab Consultas */}}
                                {{actualTab === "cons" && (
                                    <div className="space-y-4">
                                        {{consPendientes.length > 0 && (
                                            <div>
                                                <h4 className="text-sm font-bold text-orange-700 mb-2 flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-orange-500 pulse-soft"></span> Pendientes ({{consPendientes.length}})</h4>
                                                <div className="border border-orange-200 rounded-lg overflow-hidden">
                                                    <table className="w-full text-sm">
                                                        <thead><tr className="bg-orange-50 text-orange-800 text-xs"><th className="py-2 px-3 text-left">Beneficiario</th><th className="py-2 px-3 text-left">Etapa</th><th className="py-2 px-3 text-left">Consulta</th><th className="py-2 px-2 w-16"></th></tr></thead>
                                                        <tbody>
                                                            {{consPendientes.map((c, i) => (
                                                                <tr key={{i}} className={{i % 2 === 0 ? "bg-white" : "bg-orange-50/30"}}>
                                                                    <td className="py-1.5 px-3 text-gray-800 font-medium">{{c.nombre}}</td>
                                                                    <td className="py-1.5 px-3 text-gray-600">{{c.etapa}}</td>
                                                                    <td className="py-1.5 px-3 text-orange-700 font-medium">{{c.pregunta}}</td>
                                                                    <td className="py-1.5 px-2"><button onClick={{() => toggleConsulta(c.idBenef, c.etKey)}} className="text-[10px] bg-green-100 text-green-700 border border-green-300 rounded px-2 py-0.5 hover:bg-green-200">Hecho</button></td>
                                                                </tr>
                                                            ))}}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        )}}
                                        {{consHechas.length > 0 && (
                                            <div>
                                                <h4 className="text-sm font-bold text-green-700 mb-2 flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-green-500"></span> Respondidas ({{consHechas.length}})</h4>
                                                <div className="border border-green-200 rounded-lg overflow-hidden">
                                                    <table className="w-full text-sm">
                                                        <thead><tr className="bg-green-50 text-green-800 text-xs"><th className="py-2 px-3 text-left">Beneficiario</th><th className="py-2 px-3 text-left">Etapa</th><th className="py-2 px-3 text-left">Consulta</th><th className="py-2 px-3 text-left">Fecha</th></tr></thead>
                                                        <tbody>
                                                            {{consHechas.map((c, i) => (
                                                                <tr key={{i}} className={{i % 2 === 0 ? "bg-white" : "bg-green-50/30"}}>
                                                                    <td className="py-1.5 px-3 text-gray-800">{{c.nombre}}</td>
                                                                    <td className="py-1.5 px-3 text-gray-600">{{c.etapa}}</td>
                                                                    <td className="py-1.5 px-3 text-green-700">{{c.pregunta}}</td>
                                                                    <td className="py-1.5 px-3 text-[10px] text-gray-500">{{c.done.fecha.replace('T', ' ')}}</td>
                                                                </tr>
                                                            ))}}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        )}}
                                        {{consultasData.length === 0 && <p className="text-gray-400 text-center py-8">No hay consultas gatilladas aun (ninguna etapa con consulta ha sido despachada)</p>}}
                                    </div>
                                )}}
                                {{/* Tab Actividades 5% */}}
                                {{actualTab === "act5" && (
                                    <div className="space-y-4">
                                        <div className="flex items-center gap-4 text-sm mb-3">
                                            <span className="text-gray-600">Completas: <strong className="text-green-600">{{actCompletas.length}}</strong></span>
                                            <span className="text-gray-600">Parciales: <strong className="text-amber-600">{{actParciales.length}}</strong></span>
                                            <span className="text-gray-600">Sin iniciar: <strong className="text-gray-400">{{viviendas.length - actConAlgo.length}}</strong></span>
                                            <span className="text-gray-600">Total: <strong>{{viviendas.length}}</strong></span>
                                        </div>
                                        <div className="border border-gray-200 rounded-lg overflow-hidden">
                                            <table className="w-full text-sm">
                                                <thead><tr className="bg-gray-50 text-gray-600 text-xs">
                                                    <th className="py-2 px-3 text-left">Beneficiario</th>
                                                    {{ACTIVIDADES_HAB.map(a => <th key={{a}} className="py-2 px-2 text-center w-20">{{a}}</th>)}}
                                                    <th className="py-2 px-2 text-center w-12">%</th>
                                                </tr></thead>
                                                <tbody>
                                                    {{actData.filter(a => a.hechas.length > 0 || a.pendientes.length < 5).concat(actData.filter(a => a.hechas.length === 0 && a.pendientes.length === 5)).map((row, i) => (
                                                        <tr key={{row.idBenef}} className={{row.hechas.length === 5 ? "bg-green-50/50" : i % 2 === 0 ? "bg-white" : "bg-gray-50/30"}}>
                                                            <td className="py-1.5 px-3 text-gray-800 font-medium">{{row.nombre}}</td>
                                                            {{ACTIVIDADES_HAB.map(act => {{
                                                                const done = row.benActs[act];
                                                                return (
                                                                    <td key={{act}} className="py-1.5 px-2 text-center">
                                                                        <button onClick={{() => toggleActividad(row.idBenef, act)}} className={{`w-6 h-6 rounded text-xs font-bold border transition-all ${{done ? "bg-green-500 text-white border-green-600" : "bg-gray-100 text-gray-300 border-gray-200 hover:border-gray-400"}}`}} title={{done ? `Hecho: ${{done.fecha.replace('T', ' ')}}` : "Pendiente"}}>
                                                                            {{done ? "\u2713" : "\u00B7"}}
                                                                        </button>
                                                                    </td>
                                                                );
                                                            }})}}
                                                            <td className="py-1.5 px-2 text-center font-mono font-bold text-xs">
                                                                <span className={{row.pct === 5 ? "text-green-600" : row.pct > 0 ? "text-amber-600" : "text-gray-300"}}>{{row.pct}}%</span>
                                                            </td>
                                                        </tr>
                                                    ))}}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}}
                            </div>
                        </div>
                    </div>
                );
            }})()}}
            <div className="space-y-3">
                {{gruposData.map(grupo => (
                    <div key={{grupo.id}}>
                        <GrupoHeader grupo={{grupo}} colorIdx={{grupo.colorIdx}} open={{gruposAbiertos[grupo.id] !== false}} onToggle={{() => toggleGrupo(grupo.id)}} />
                        {{(gruposAbiertos[grupo.id] !== false) && (
                            <div className={{`space-y-2 ${{grupo.nombre ? "ml-2 pl-3 border-l-2 " + (grupo.colorIdx >= 0 ? GRUPO_COLORS[grupo.colorIdx].border : "border-gray-200") : ""}} mt-2`}}>
                                {{grupo.viviendas.map(v =>
                                    <ViviendaCard key={{v.ID_Benef}} beneficiario={{v}} estadoEtapas={{v.estadoEtapas}} expanded={{expandida === v.ID_Benef}} onToggle={{() => setExpandida(expandida === v.ID_Benef ? null : v.ID_Benef)}} grupoColor={{grupo.colorIdx}} obsCount={{(observaciones[v.ID_Benef] || []).length}} observaciones={{observaciones[v.ID_Benef] || []}} addObservacion={{addObservacion}} deleteObservacion={{deleteObservacion}} actividades={{actividades[v.ID_Benef] || {{}}}} toggleActividad={{toggleActividad}} consultas={{consultas[v.ID_Benef] || {{}}}} toggleConsulta={{toggleConsulta}} />
                                )}}
                            </div>
                        )}}
                    </div>
                ))}}
                {{vivFiltradas.length === 0 && (
                    <div className="text-center py-12 text-gray-400 bg-white rounded-lg border border-gray-200">
                        <IconUsers />
                        <p className="mt-3">No se encontraron viviendas</p>
                    </div>
                )}}
            </div>
        </div>
    );
}};

// ===== MATRIZ DE AVANCE CON GRUPOS =====
const MatrizAvance = ({{ viviendas, grupos }}) => {{
    const gruposData = agruparViviendas(viviendas, grupos);
    return (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                        <th className="py-2 px-3 sticky left-0 bg-gray-50 z-10 min-w-[180px]">Beneficiario</th>
                        {{SECUENCIA_PRINCIPAL.map(key => (
                            <th key={{key}} className="py-2 px-2 text-center text-xs">{{ETAPAS_CONFIG[key]?.nombre}}</th>
                        ))}}
                        <th className="py-2 px-2 text-center text-xs">Insp%</th>
                        <th className="py-2 px-2 text-center text-xs">Pagado</th>
                        <th className="py-2 px-2 text-center text-xs">Coher.</th>
                    </tr>
                </thead>
                <tbody>
                    {{gruposData.map(grupo => (
                        <React.Fragment key={{grupo.id}}>
                            {{grupo.nombre && (
                                <tr className={{grupo.colorIdx >= 0 ? GRUPO_COLORS[grupo.colorIdx].headerBg : "bg-gray-100"}}>
                                    <td colSpan={{SECUENCIA_PRINCIPAL.length + 4}} className="py-2 px-3">
                                        <div className="flex items-center gap-2">
                                            {{grupo.colorIdx >= 0 && <div className={{`w-3 h-3 rounded ${{GRUPO_COLORS[grupo.colorIdx].accent}}`}}/>}}
                                            <span className={{`text-xs font-bold ${{grupo.colorIdx >= 0 ? GRUPO_COLORS[grupo.colorIdx].text : "text-gray-600"}}`}}>{{grupo.nombre}}</span>
                                            {{grupo.capataz && <span className="text-[10px] text-gray-500">\u2014 {{grupo.capataz}}</span>}}
                                            <span className="text-[10px] text-gray-400 ml-2">{{grupo.viviendas.length}} viv.</span>
                                        </div>
                                    </td>
                                </tr>
                            )}}
                            {{grupo.viviendas.sort((a, b) => (a.primerDespacho || "9999").localeCompare(b.primerDespacho || "9999")).map(v => {{
                                const insp = getInspeccion(v.ID_Benef);
                                const totalPag = getTotalPagado(v.ID_Benef);
                                const alerts = calcCoherencia(v.ID_Benef, v.estadoEtapas);
                                const alertasRojas = alerts.filter(a => a.tipo === "rojo");
                                const alertasNaranjas = alerts.filter(a => a.tipo === "naranja");
                                return (
                                    <tr key={{v.ID_Benef}} className="border-b border-gray-100 hover:bg-gray-50">
                                        <td className="py-2 px-3 sticky left-0 bg-white z-10">
                                            <div className="flex items-center gap-1.5">
                                                {{grupo.colorIdx >= 0 && <div className={{`w-1 h-4 rounded-full ${{GRUPO_COLORS[grupo.colorIdx].accent}}`}}/>}}
                                                <div>
                                                    <div className="font-medium text-gray-800 text-xs">{{v.NOMBRES}} {{v.APELLIDOS}}</div>
                                                    <div className="text-[10px] text-gray-400">{{v.tipologia}}</div>
                                                </div>
                                            </div>
                                        </td>
                                        {{SECUENCIA_PRINCIPAL.map(key => {{
                                            const info = v.estadoEtapas[key];
                                            const colores = {{
                                                despachado: "bg-blue-500 text-white",
                                                solicitado: "bg-purple-500 text-white",
                                                en_tiempo: "bg-green-400 text-white",
                                                atencion: "bg-yellow-400 text-yellow-900",
                                                critico: "bg-red-500 text-white animate-pulse",
                                                bloqueado: "bg-gray-200 text-gray-400"
                                            }};
                                            const tooltipParts = [info?.nombre + ": " + (info?.estado || "bloqueado")];
                                            if (info?.estado === "despachado") {{
                                                tooltipParts.push("Despacho: " + (info.fechaDespacho || "") + " (" + (info.diasTranscurridos || 0) + "d)");
                                                if (info.fechaSolicitud) tooltipParts.push("Solicitud: " + info.fechaSolicitud);
                                            }} else if (info?.estado === "solicitado") {{
                                                tooltipParts.push("Solicitud: " + (info.fechaSolicitud || "") + " (hace " + (info.diasSolicitud || 0) + "d)");
                                            }} else if (info?.diasTranscurridos) {{
                                                tooltipParts.push(info.diasTranscurridos + " dias desde dependencia");
                                            }}
                                            return (
                                                <td key={{key}} className="py-2 px-1 text-center">
                                                    <div
                                                        className={{`matrix-cell inline-flex items-center justify-center rounded-md text-[10px] font-bold w-8 h-8 ${{colores[info?.estado || "bloqueado"]}}`}}
                                                        title={{tooltipParts.join(" | ")}}
                                                    >
                                                        {{info?.estado === "despachado" ? "D" + (info.diasTranscurridos || "") :
                                                          info?.estado === "solicitado" ? "S" + (info.diasSolicitud || "") :
                                                          info?.estado === "bloqueado" ? "\u2014" :
                                                          "+" + (info?.diasTranscurridos || 0) + "d"}}
                                                    </div>
                                                </td>
                                            );
                                        }})}}
                                        <td className="py-2 px-2 text-center">
                                            <span className={{`font-mono font-bold text-xs ${{
                                                insp ? (insp.pct_total >= 90 ? "text-green-600" : insp.pct_total >= 50 ? "text-blue-600" : "text-orange-500") : "text-gray-300"
                                            }}`}}>
                                                {{insp ? insp.pct_total + "%" : "\u2014"}}
                                            </span>
                                        </td>
                                        <td className="py-2 px-2 text-center">
                                            <span className="font-mono text-xs text-violet-700">{{totalPag > 0 ? formatPeso(totalPag) : "\u2014"}}</span>
                                        </td>
                                        <td className="py-2 px-2 text-center">
                                            {{alertasRojas.length > 0 ? (
                                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-100 text-red-600 text-[10px] font-bold coherence-pulse" title={{alertasRojas.map(a => a.msg).join("; ")}}>{{alertasRojas.length}}</span>
                                            ) : alertasNaranjas.length > 0 ? (
                                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-orange-100 text-orange-600 text-[10px] font-bold" title={{alertasNaranjas.map(a => a.msg).join("; ")}}>{{alertasNaranjas.length}}</span>
                                            ) : (
                                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-600 text-[10px] font-bold">OK</span>
                                            )}}
                                        </td>
                                    </tr>
                                );
                            }})}}
                        </React.Fragment>
                    ))}}
                </tbody>
            </table>
        </div>
    );
}};

// ===== DISTRIBUCIÓN + TIMELINE =====
const DistribucionTab = ({{ viviendas }}) => {{
    const distribucion = React.useMemo(() => {{
        return SECUENCIA_PRINCIPAL.map(etapaKey => {{
            const config = ETAPAS_CONFIG[etapaKey];
            const despachadas = viviendas.filter(v => v.estadoEtapas[etapaKey]?.estado === "despachado").length;
            const esperando = viviendas.filter(v => {{
                const st = v.estadoEtapas[etapaKey]?.estado;
                return st && st !== "despachado" && st !== "bloqueado";
            }}).length;
            const criticas = viviendas.filter(v => v.estadoEtapas[etapaKey]?.estado === "critico").length;
            return {{ key: etapaKey, nombre: config?.nombre || etapaKey, despachadas, esperando, criticas }};
        }});
    }}, [viviendas]);
    const maxBarWidth = Math.max(...distribucion.map(d => d.despachadas + d.esperando), 1);

    return (
        <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Distribución por Etapa — Cuellos de Botella</h3>
                <div className="space-y-3">
                    {{distribucion.map(d => (
                        <div key={{d.key}} className="flex items-center gap-3">
                            <span className="text-xs text-gray-600 w-28 text-right font-medium">{{d.nombre}}</span>
                            <div className="flex-1 flex items-center gap-1">
                                <div className="flex-1 bg-gray-100 rounded-full h-6 overflow-hidden flex">
                                    <div className="bg-blue-500 h-6 flex items-center justify-center text-white text-[10px] font-bold transition-all" style={{{{ width: `${{(d.despachadas / maxBarWidth) * 100}}%`, minWidth: d.despachadas > 0 ? "20px" : "0" }}}}>
                                        {{d.despachadas > 0 ? d.despachadas : ""}}
                                    </div>
                                    <div className={{`${{d.criticas > 0 ? "bg-red-400" : "bg-yellow-400"}} h-6 flex items-center justify-center text-[10px] font-bold transition-all`}} style={{{{ width: `${{(d.esperando / maxBarWidth) * 100}}%`, minWidth: d.esperando > 0 ? "20px" : "0" }}}}>
                                        {{d.esperando > 0 ? d.esperando : ""}}
                                    </div>
                                </div>
                                <span className="text-xs text-gray-500 w-20">
                                    {{d.despachadas}}D / {{d.esperando}}E
                                    {{d.criticas > 0 && <span className="text-red-600 font-bold ml-1">({{d.criticas}} crit)</span>}}
                                </span>
                            </div>
                        </div>
                    ))}}
                </div>
                <div className="flex gap-4 mt-4 text-xs text-gray-500">
                    <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-blue-500" /><span>Despachado</span></div>
                    <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-yellow-400" /><span>Esperando</span></div>
                    <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-red-400" /><span>Con Críticos</span></div>
                </div>
                {{(() => {{
                    const bottleneck = distribucion.reduce((max, d) => d.esperando > max.esperando ? d : max, distribucion[0]);
                    if (bottleneck && bottleneck.esperando >= 3) return (
                        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                            <div className="flex items-center gap-2 text-red-700 text-sm font-medium">
                                <IconWarning />
                                <span>Cuello de botella: {{bottleneck.esperando}} casas esperando <strong>{{bottleneck.nombre}}</strong></span>
                            </div>
                        </div>
                    );
                    return null;
                }})()}}
            </div>

            {{/* Timeline del Proyecto */}}
            <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Timeline de Proyecto — Avance por Casa</h3>
                <div className="space-y-1.5">
                    {{viviendas.filter(v => v.numDespachos > 0).sort((a, b) => {{
                        const fa = a.estadoEtapas["01_FUNDACIONES"]?.fechaDespacho || "Z";
                        const fb = b.estadoEtapas["01_FUNDACIONES"]?.fechaDespacho || "Z";
                        return fa.localeCompare(fb);
                    }}).map(v => {{
                        const fund = v.estadoEtapas["01_FUNDACIONES"];
                        if (!fund?.fechaDespacho) return null;
                        const inicio = new Date(fund.fechaDespacho);
                        const hoy = new Date();
                        const maxDias = Math.max(Math.floor((hoy - inicio) / (1000*60*60*24)), 1);
                        return (
                            <div key={{v.ID_Benef}} className="flex items-center gap-2">
                                <span className="text-[10px] text-gray-600 w-28 text-right truncate" title={{`${{v.NOMBRES}} ${{v.APELLIDOS}}`}}>
                                    {{v.APELLIDOS}}
                                </span>
                                <div className="flex-1 bg-gray-100 rounded h-5 relative overflow-hidden">
                                    {{SECUENCIA_PRINCIPAL.map(key => {{
                                        const info = v.estadoEtapas[key];
                                        if (info?.estado !== "despachado" || !info?.fechaDespacho) return null;
                                        const dia = Math.floor((new Date(info.fechaDespacho) - inicio) / (1000*60*60*24));
                                        const left = (dia / maxDias) * 100;
                                        return (
                                            <div
                                                key={{key}}
                                                className="absolute top-0 h-5 bg-blue-500 rounded-sm flex items-center justify-center"
                                                style={{{{ left: `${{Math.min(left, 98)}}%`, width: "12px" }}}}
                                                title={{`${{info.nombre}}: Día ${{dia + 1}}`}}
                                            >
                                                <span className="text-white text-[7px] font-bold">{{ETAPAS_CONFIG[key]?.codigo}}</span>
                                            </div>
                                        );
                                    }})}}
                                    <div className="absolute top-0 right-0 h-5 w-0.5 bg-red-400" title="Hoy" />
                                </div>
                                <span className="text-[10px] text-gray-400 w-10 font-mono">{{maxDias}}d</span>
                            </div>
                        );
                    }})}}
                </div>
                <div className="flex items-center gap-4 mt-3 text-[10px] text-gray-400">
                    <span>Cada marcador = etapa despachada</span>
                    <span className="flex items-center gap-1"><div className="w-0.5 h-3 bg-red-400" />Hoy</span>
                    <span>Ancho = días desde fundación</span>
                </div>
            </div>
        </div>
    );
}};

// ===== RESUMEN FINANCIERO =====
const FinancieroTab = ({{ viviendas }}) => {{
    const resumenFinanciero = React.useMemo(() => {{
        const porFamilia = {{}};
        let totalViaticos = 0, totalMO = 0, totalOtros = 0;
        viviendas.forEach(v => {{
            const pagos = getSolpago(v.ID_Benef);
            pagos.forEach(p => {{
                if (!porFamilia[p.Familia_pago]) porFamilia[p.Familia_pago] = {{ total: 0, count: 0 }};
                porFamilia[p.Familia_pago].total += p.monto;
                porFamilia[p.Familia_pago].count++;
                if (p.Familia_pago === "Viatico") totalViaticos += p.monto;
                else if (FAMILIAS_CRITICAS.includes(p.Familia_pago)) totalMO += p.monto;
                else totalOtros += p.monto;
            }});
        }});
        return {{ porFamilia, totalViaticos, totalMO, totalOtros }};
    }}, [viviendas]);

    const totalPagado = viviendas.reduce((s, v) => s + getTotalPagado(v.ID_Benef), 0);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-amber-200 rounded-xl p-4 shadow-sm">
                    <p className="text-amber-600 text-xs font-medium">Viáticos</p>
                    <p className="text-xl font-bold text-amber-700 mt-1 font-mono">{{formatPeso(resumenFinanciero.totalViaticos)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{viviendas.length > 0 ? formatPeso(Math.round(resumenFinanciero.totalViaticos / viviendas.length)) : "$0"}} / casa</p>
                </div>
                <div className="bg-white border border-violet-200 rounded-xl p-4 shadow-sm">
                    <p className="text-violet-600 text-xs font-medium">Mano de Obra (ruta crítica)</p>
                    <p className="text-xl font-bold text-violet-700 mt-1 font-mono">{{formatPeso(resumenFinanciero.totalMO)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{viviendas.length > 0 ? formatPeso(Math.round(resumenFinanciero.totalMO / viviendas.length)) : "$0"}} / casa</p>
                </div>
                <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                    <p className="text-gray-500 text-xs font-medium">Otros (Pintura, Elec, Ext, etc.)</p>
                    <p className="text-xl font-bold text-gray-700 mt-1 font-mono">{{formatPeso(resumenFinanciero.totalOtros)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{viviendas.length > 0 ? formatPeso(Math.round(resumenFinanciero.totalOtros / viviendas.length)) : "$0"}} / casa</p>
                </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <h3 className="text-sm font-medium text-gray-700 mb-3">Composición del Gasto</h3>
                {{(() => {{
                    const total = resumenFinanciero.totalViaticos + resumenFinanciero.totalMO + resumenFinanciero.totalOtros;
                    if (total === 0) return <p className="text-gray-400 text-sm">Sin pagos registrados</p>;
                    const pctV = (resumenFinanciero.totalViaticos / total * 100).toFixed(1);
                    const pctM = (resumenFinanciero.totalMO / total * 100).toFixed(1);
                    const pctO = (resumenFinanciero.totalOtros / total * 100).toFixed(1);
                    return (
                        <div>
                            <div className="flex rounded-full h-8 overflow-hidden mb-2">
                                <div className="bg-amber-400 flex items-center justify-center text-xs font-bold text-amber-900" style={{{{ width: `${{pctV}}%` }}}}>{{pctV}}%</div>
                                <div className="bg-violet-500 flex items-center justify-center text-xs font-bold text-white" style={{{{ width: `${{pctM}}%` }}}}>{{pctM}}%</div>
                                <div className="bg-gray-400 flex items-center justify-center text-xs font-bold text-white" style={{{{ width: `${{pctO}}%` }}}}>{{pctO}}%</div>
                            </div>
                            <div className="flex gap-4 text-xs text-gray-500">
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-amber-400" />Viáticos ({{pctV}}%)</span>
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-violet-500" />M.O. ({{pctM}}%)</span>
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-gray-400" />Otros ({{pctO}}%)</span>
                                <span className="font-medium text-gray-700">Total: {{formatPeso(total)}}</span>
                            </div>
                        </div>
                    );
                }})()}}
            </div>

            <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                            <th className="py-2 px-4">Familia de Pago</th>
                            <th className="py-2 px-4 text-right">Total Pagado</th>
                            <th className="py-2 px-4 text-center"># Pagos</th>
                            <th className="py-2 px-4 text-right">Promedio</th>
                            <th className="py-2 px-4 text-right">Por Casa</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{Object.entries(resumenFinanciero.porFamilia).sort((a, b) => b[1].total - a[1].total).map(([fam, data]) => (
                            <tr key={{fam}} className={{`border-b border-gray-100 ${{fam === "Viatico" ? "bg-amber-50/50" : ""}}`}}>
                                <td className="py-2 px-4 font-medium text-gray-700">{{fam}}</td>
                                <td className="py-2 px-4 text-right font-mono font-bold text-violet-700">{{formatPeso(data.total)}}</td>
                                <td className="py-2 px-4 text-center text-gray-500">{{data.count}}</td>
                                <td className="py-2 px-4 text-right font-mono text-gray-600">{{formatPeso(Math.round(data.total / data.count))}}</td>
                                <td className="py-2 px-4 text-right font-mono text-gray-500">{{formatPeso(Math.round(data.total / viviendas.length))}}</td>
                            </tr>
                        ))}}
                    </tbody>
                    <tfoot>
                        <tr className="border-t-2 border-gray-300 bg-gray-50 font-bold">
                            <td className="py-2 px-4 text-gray-800">TOTAL PROYECTO</td>
                            <td className="py-2 px-4 text-right font-mono text-violet-800">{{formatPeso(totalPagado)}}</td>
                            <td className="py-2 px-4 text-center text-gray-600">{{Object.values(resumenFinanciero.porFamilia).reduce((s, d) => s + d.count, 0)}}</td>
                            <td className="py-2 px-4"></td>
                            <td className="py-2 px-4 text-right font-mono text-gray-600">{{formatPeso(Math.round(totalPagado / viviendas.length))}}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}};

// ===== MANO DE OBRA =====
const ManoDeObraTab = ({{ viviendas }}) => {{
    const [expandido, setExpandido] = React.useState(null);

    const {{ maestros, casasProyArr }} = React.useMemo(() => {{
        const idsProyecto = new Set(viviendas.map(v => String(v.ID_Benef)));
        const pagosProyecto = SOLPAGO_DATA.filter(s => idsProyecto.has(String(s.ID_Benef)));
        const hoy = new Date();
        const hace30dias = new Date(hoy.getTime() - 30 * 24 * 60 * 60 * 1000);

        const maestrosMap = {{}};
        pagosProyecto.forEach(p => {{
            const mid = p.maestro;
            if (!mid || mid === 'nan' || mid === '') return;
            if (!maestrosMap[mid]) {{
                maestrosMap[mid] = {{
                    id: mid, nombre: getMaestroNombre(mid), totalPagado: 0, numPagos: 0,
                    casas: new Set(), familias: {{}}, fechas: [], casasDetalle: {{}}
                }};
            }}
            const m = maestrosMap[mid];
            m.totalPagado += p.monto;
            m.numPagos++;
            m.casas.add(String(p.ID_Benef));
            m.familias[p.Familia_pago] = (m.familias[p.Familia_pago] || 0) + p.monto;
            if (p.fecha && p.fecha !== '') m.fechas.push(new Date(p.fecha));
            const cid = String(p.ID_Benef);
            if (!m.casasDetalle[cid]) m.casasDetalle[cid] = {{ familias: {{}}, total: 0 }};
            m.casasDetalle[cid].familias[p.Familia_pago] = (m.casasDetalle[cid].familias[p.Familia_pago] || 0) + p.monto;
            m.casasDetalle[cid].total += p.monto;
        }});

        const maestrosArr = Object.values(maestrosMap).map(m => {{
            const fechasValidas = m.fechas.filter(f => !isNaN(f.getTime()));
            const ultimoPago = fechasValidas.length > 0 ? new Date(Math.max(...fechasValidas)) : null;
            const primerPago = fechasValidas.length > 0 ? new Date(Math.min(...fechasValidas)) : null;
            const diasDesdeUltimo = ultimoPago ? Math.floor((hoy - ultimoPago) / (1000*60*60*24)) : null;
            return {{
                ...m, numCasas: m.casas.size, ultimoPago, primerPago, diasDesdeUltimo,
                inactivo: diasDesdeUltimo !== null && diasDesdeUltimo > 30
            }};
        }}).sort((a, b) => b.totalPagado - a.totalPagado);

        const casasArr = viviendas.map(v => ({{
            id: String(v.ID_Benef),
            nombre: `${{v.NOMBRES}} ${{v.APELLIDOS}}`
        }}));

        return {{ maestros: maestrosArr, casasProyArr: casasArr }};
    }}, [viviendas]);

    const activos = maestros.filter(m => !m.inactivo);
    const inactivos = maestros.filter(m => m.inactivo);
    const totalPagadoMO = maestros.reduce((s, m) => s + m.totalPagado, 0);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
                    <p className="text-gray-500 text-[10px]">Maestros</p>
                    <p className="text-2xl font-bold text-gray-800">{{maestros.length}}</p>
                </div>
                <div className="bg-white border border-green-200 rounded-xl p-3 shadow-sm">
                    <p className="text-gray-500 text-[10px]">Activos (ult. 30d)</p>
                    <p className="text-2xl font-bold text-green-600">{{activos.length}}</p>
                </div>
                <div className="bg-white border border-red-200 rounded-xl p-3 shadow-sm">
                    <p className="text-gray-500 text-[10px]">Inactivos (+30d)</p>
                    <p className="text-2xl font-bold text-red-600">{{inactivos.length}}</p>
                </div>
                <div className="bg-white border border-violet-200 rounded-xl p-3 shadow-sm">
                    <p className="text-gray-500 text-[10px]">Total Pagado M.O.</p>
                    <p className="text-lg font-bold text-violet-700 font-mono">{{formatPeso(totalPagadoMO)}}</p>
                </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700">Maestros del Proyecto</h3>
                        <p className="text-[10px] text-gray-400">Click para expandir detalle</p>
                    </div>
                    <div className="flex gap-3 text-[10px]">
                        <span className="text-green-600 font-semibold">{{activos.length}} activos</span>
                        <span className="text-red-600 font-semibold">{{inactivos.length}} inactivos</span>
                    </div>
                </div>
                <table className="w-full text-[11px]">
                    <thead>
                        <tr className="bg-gray-50 border-b border-gray-200 text-gray-500">
                            <th className="text-left pl-3 pr-1 py-1.5 font-medium w-[50px]"></th>
                            <th className="text-left px-2 py-1.5 font-medium">Maestro</th>
                            <th className="text-center px-1 py-1.5 font-medium">Casas</th>
                            <th className="text-right px-2 py-1.5 font-medium">Pagado</th>
                            <th className="text-center px-1 py-1.5 font-medium">Ult. Pago</th>
                            <th className="text-center px-1 py-1.5 font-medium">Días</th>
                            <th className="text-left px-2 py-1.5 font-medium">Familias</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{maestros.map(m => (
                            <React.Fragment key={{m.id}}>
                                <tr className={{`border-b border-gray-100 hover:bg-violet-50/40 cursor-pointer transition-colors ${{m.inactivo ? 'bg-red-50/30' : ''}}`}} onClick={{() => setExpandido(expandido === m.id ? null : m.id)}}>
                                    <td className="pl-3 pr-1 py-2">
                                        <span className={{`inline-block w-[42px] text-center px-1 py-0.5 rounded-full text-[8px] font-bold ${{m.inactivo ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"}}`}}>
                                            {{m.inactivo ? "INACT" : "ACTIV"}}
                                        </span>
                                    </td>
                                    <td className="px-2 py-2">
                                        <div className="font-medium text-gray-800">{{m.nombre}}</div>
                                    </td>
                                    <td className="px-1 py-2 text-center font-mono font-bold text-gray-700">{{m.numCasas}}</td>
                                    <td className="px-2 py-2 text-right font-mono font-bold text-violet-700">{{formatPeso(m.totalPagado)}}</td>
                                    <td className={{`px-1 py-2 text-center font-mono text-[10px] ${{m.inactivo ? 'text-red-600 font-semibold' : 'text-gray-500'}}`}}>
                                        {{m.ultimoPago ? m.ultimoPago.toLocaleDateString('es-CL') : '-'}}
                                    </td>
                                    <td className={{`px-1 py-2 text-center font-mono text-[10px] ${{m.diasDesdeUltimo > 60 ? 'text-red-600 font-bold' : m.diasDesdeUltimo > 30 ? 'text-orange-500 font-semibold' : 'text-gray-400'}}`}}>
                                        {{m.diasDesdeUltimo !== null ? m.diasDesdeUltimo + "d" : '-'}}
                                    </td>
                                    <td className="px-2 py-2">
                                        <div className="flex flex-wrap gap-0.5">
                                            {{Object.keys(m.familias).map(f => (
                                                <span key={{f}} className="px-1.5 py-0 bg-violet-50 text-violet-600 rounded text-[9px]">{{FAMILIA_LABELS[f] || f}}</span>
                                            ))}}
                                        </div>
                                    </td>
                                </tr>
                                {{expandido === m.id && (
                                    <tr>
                                        <td colSpan={{7}} className="bg-gray-50 px-4 py-3 border-b border-gray-200">
                                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                                <div>
                                                    <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Casas ({{m.numCasas}})</h4>
                                                    <div className="space-y-1">
                                                        {{Array.from(m.casas).map(cid => {{
                                                            const det = m.casasDetalle[cid];
                                                            const v = viviendas.find(vv => String(vv.ID_Benef) === cid);
                                                            const nombre = v ? `${{v.NOMBRES}} ${{v.APELLIDOS}}` : cid;
                                                            return (
                                                                <div key={{cid}} className="flex items-center justify-between gap-2 text-[10px] py-1 border-b border-gray-100">
                                                                    <span className="text-gray-700 font-medium truncate">{{nombre}}</span>
                                                                    <span className="font-mono text-gray-600 text-[9px]">{{formatPeso(det?.total || 0)}}</span>
                                                                </div>
                                                            );
                                                        }})}}
                                                    </div>
                                                </div>
                                                <div>
                                                    <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Distribución por Familia</h4>
                                                    <div className="space-y-1">
                                                        {{Object.entries(m.familias).sort((a,b) => b[1]-a[1]).map(([fam, monto]) => {{
                                                            const pct = m.totalPagado > 0 ? (monto / m.totalPagado * 100) : 0;
                                                            const isV = fam === "Viatico" || fam === "10 - Viatico";
                                                            return (
                                                                <div key={{fam}} className="flex items-center gap-1.5 text-[10px]">
                                                                    <span className={{`w-[55px] truncate text-right ${{isV ? 'text-amber-600' : 'text-gray-600'}}`}}>{{FAMILIA_LABELS[fam] || fam}}</span>
                                                                    <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                                                                        <div className={{`h-1.5 rounded-full ${{isV ? 'bg-amber-400' : 'bg-violet-500'}}`}} style={{{{ width: `${{Math.min(pct, 100)}}%` }}}} />
                                                                    </div>
                                                                    <span className="font-mono text-gray-500 w-[50px] text-right text-[9px]">{{formatPeso(monto)}}</span>
                                                                </div>
                                                            );
                                                        }})}}
                                                    </div>
                                                </div>
                                                <div>
                                                    <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Actividad</h4>
                                                    <div className="space-y-2 text-[10px]">
                                                        <div className="flex justify-between"><span className="text-gray-500">Primer pago</span><span className="font-mono text-gray-700">{{m.primerPago ? m.primerPago.toLocaleDateString('es-CL') : '-'}}</span></div>
                                                        <div className="flex justify-between"><span className="text-gray-500">Último pago</span><span className={{`font-mono ${{m.inactivo ? 'text-red-600 font-semibold' : 'text-gray-700'}}`}}>{{m.ultimoPago ? m.ultimoPago.toLocaleDateString('es-CL') : '-'}}</span></div>
                                                        <div className="flex justify-between"><span className="text-gray-500">Total pagos</span><span className="font-mono text-gray-700">{{m.numPagos}}</span></div>
                                                        <div className="flex justify-between"><span className="text-gray-500">Días sin pago</span><span className={{`font-mono ${{m.diasDesdeUltimo > 60 ? 'text-red-600 font-bold' : m.diasDesdeUltimo > 30 ? 'text-orange-500' : 'text-gray-700'}}`}}>{{m.diasDesdeUltimo !== null ? m.diasDesdeUltimo : '-'}}</span></div>
                                                    </div>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                )}}
                            </React.Fragment>
                        ))}}
                    </tbody>
                </table>
            </div>

            {{/* Cobertura por Vivienda */}}
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <h3 className="text-sm font-semibold text-gray-700">Cobertura por Vivienda</h3>
                    <p className="text-[10px] text-gray-400">Por cada casa: maestros asignados y familias ejecutadas</p>
                </div>
                <div className="p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2" style={{{{ maxHeight: '600px', overflowY: 'auto' }}}}>
                    {{casasProyArr.map(casa => {{
                        const maestrosCasa = maestros.filter(m => m.casas.has(casa.id)).map(m => ({{
                            nombre: m.nombre, inactivo: m.inactivo,
                            familias: Object.entries(m.casasDetalle[casa.id]?.familias || {{}}).filter(([f]) => f !== "Viatico" && f !== "10 - Viatico"),
                            total: m.casasDetalle[casa.id]?.total || 0
                        }})).sort((a,b) => b.total - a.total);
                        const totalCasa = maestrosCasa.reduce((s, mc) => s + mc.total, 0);
                        if (maestrosCasa.length === 0) return null;
                        return (
                            <div key={{casa.id}} className="border border-gray-100 rounded-lg p-2.5 hover:border-violet-200 transition-colors">
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[11px] font-semibold text-gray-800 truncate max-w-[65%]">{{casa.nombre}}</span>
                                    <span className="text-[9px] font-mono text-violet-600 font-bold">{{formatPeso(totalCasa)}}</span>
                                </div>
                                <div className="space-y-1">
                                    {{maestrosCasa.map((mc, i) => (
                                        <div key={{i}} className="flex items-center gap-1.5">
                                            <span className={{`w-1.5 h-1.5 rounded-full flex-shrink-0 ${{mc.inactivo ? 'bg-red-400' : 'bg-green-400'}}`}} />
                                            <span className="text-[9px] text-gray-600 truncate max-w-[90px]">{{mc.nombre.split(' ').slice(0,2).join(' ')}}</span>
                                            <div className="flex gap-0.5 flex-1 flex-wrap justify-end">
                                                {{mc.familias.map(([f, monto]) => (
                                                    <span key={{f}} className="px-0.5 py-0 bg-violet-50 text-violet-600 rounded text-[7px] font-mono" title={{`${{FAMILIA_LABELS[f] || f}}: ${{formatPeso(monto)}}`}}>
                                                        {{(FAMILIA_LABELS[f] || f).substring(0,3)}}
                                                    </span>
                                                ))}}
                                            </div>
                                        </div>
                                    ))}}
                                </div>
                            </div>
                        );
                    }})}}
                </div>
            </div>
        </div>
    );
}};

// ===== ESTADOS DE PAGO =====
const EstadosPagoTab = ({{ viviendas }}) => {{
    const idsProyecto = new Set(viviendas.map(v => String(v.ID_Benef)));
    const eeppProy = EEPP_DATA.filter(ep => idsProyecto.has(String(ep.ID_Benef)));

    const eeppResumen = React.useMemo(() => {{
        const pagado = eeppProy.filter(e => e.Estado.includes("Pagado"));
        const ingresado = eeppProy.filter(e => e.Estado.includes("Ingresado"));
        const prep = eeppProy.filter(e => !e.Estado.includes("Pagado") && !e.Estado.includes("Ingresado"));
        const montoPag = pagado.reduce((s, e) => s + e.Monto, 0);
        const montoIng = ingresado.reduce((s, e) => s + e.Monto, 0);
        const montoPrep = prep.reduce((s, e) => s + e.Monto, 0);
        return {{ pagado: montoPag, ingresado: montoIng, preparacion: montoPrep, total: montoPag + montoIng + montoPrep, countPag: pagado.length, countIng: ingresado.length, countPrep: prep.length }};
    }}, [eeppProy]);

    const formatUF = (val) => {{
        if (!val && val !== 0) return '\u2014';
        return val.toLocaleString('es-CL', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + ' UF';
    }};
    const formatFecha = (iso) => {{
        if (!iso) return '\u2014';
        const [y,m,d] = iso.split('-');
        return `${{d}}/${{m}}/${{y}}`;
    }};

    // Agrupar por EP
    const epsPorNum = {{}};
    eeppProy.forEach(ep => {{
        const num = ep.Num_EP || '?';
        if (!epsPorNum[num]) epsPorNum[num] = {{ num, fecha: '', monto: 0, beneficiarios: 0, pagado: 0, ingresado: 0, prep: 0, estado: '' }};
        epsPorNum[num].monto += ep.Monto;
        epsPorNum[num].beneficiarios++;
        if (!epsPorNum[num].fecha && ep.Fecha) epsPorNum[num].fecha = ep.Fecha;
        if (ep.Estado.includes("Pagado")) epsPorNum[num].pagado++;
        else if (ep.Estado.includes("Ingresado")) epsPorNum[num].ingresado++;
        else epsPorNum[num].prep++;
    }});
    const epsArr = Object.values(epsPorNum).filter(e => e.num && String(e.num).trim()).sort((a, b) => parseInt(a.num) - parseInt(b.num));
    epsArr.forEach(ep => {{
        if (ep.pagado === ep.beneficiarios) ep.estado = "Pagado";
        else if (ep.ingresado > 0 && ep.pagado === 0 && ep.prep === 0) ep.estado = "Ingresado";
        else if (ep.prep === ep.beneficiarios) ep.estado = "En Preparación";
        else ep.estado = "Mixto";
    }});

    // Detalle por beneficiario
    const epNums = epsArr.map(e => e.num);
    const benefMap = {{}};
    eeppProy.forEach(ep => {{
        const bid = String(ep.ID_Benef);
        if (!benefMap[bid]) benefMap[bid] = {{ id: bid, eps: {{}}, total: 0, pagado: 0 }};
        benefMap[bid].eps[ep.Num_EP] = {{ monto: ep.Monto, estado: ep.Estado }};
        benefMap[bid].total += ep.Monto;
        if (ep.Estado.includes("Pagado")) benefMap[bid].pagado += ep.Monto;
    }});
    const benefArr = Object.values(benefMap).sort((a, b) => b.total - a.total);
    const getNombreBenef = (id) => {{
        const v = viviendas.find(vv => String(vv.ID_Benef) === id);
        return v ? `${{v.NOMBRES}} ${{v.APELLIDOS}}` : id;
    }};

    const montoPag = eeppResumen.pagado;
    const montoIng = eeppResumen.ingresado;
    const montoPrep = eeppResumen.preparacion;
    const montoTotal = eeppResumen.total;

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-green-200 rounded-xl p-4 shadow-sm">
                    <p className="text-green-600 text-xs font-medium">Pagado</p>
                    <p className="text-xl font-bold text-green-700 mt-1 font-mono">{{formatUF(montoPag)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{eeppResumen.countPag}} líneas EP</p>
                </div>
                <div className="bg-white border border-yellow-200 rounded-xl p-4 shadow-sm">
                    <p className="text-yellow-600 text-xs font-medium">Ingresado (esperando pago)</p>
                    <p className="text-xl font-bold text-yellow-700 mt-1 font-mono">{{formatUF(montoIng)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{eeppResumen.countIng}} líneas EP</p>
                </div>
                <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                    <p className="text-gray-500 text-xs font-medium">En Preparación</p>
                    <p className="text-xl font-bold text-gray-700 mt-1 font-mono">{{formatUF(montoPrep)}}</p>
                    <p className="text-[10px] text-gray-400 mt-1">{{eeppResumen.countPrep}} líneas EP</p>
                </div>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <h3 className="text-sm font-medium text-gray-700 mb-3">Progreso de Cobro</h3>
                {{(() => {{
                    if (montoTotal === 0) return <p className="text-gray-400 text-sm">Sin EP registrados</p>;
                    const pctP = (montoPag / montoTotal * 100).toFixed(1);
                    const pctI = (montoIng / montoTotal * 100).toFixed(1);
                    const pctR = (montoPrep / montoTotal * 100).toFixed(1);
                    return (
                        <div>
                            <div className="flex rounded-full h-8 overflow-hidden mb-2">
                                {{montoPag > 0 && <div className="bg-green-500 flex items-center justify-center text-xs font-bold text-white" style={{{{ width: `${{pctP}}%` }}}}>{{pctP}}%</div>}}
                                {{montoIng > 0 && <div className="bg-yellow-400 flex items-center justify-center text-xs font-bold text-yellow-900" style={{{{ width: `${{pctI}}%` }}}}>{{pctI}}%</div>}}
                                {{montoPrep > 0 && <div className="bg-gray-300 flex items-center justify-center text-xs font-bold text-gray-600" style={{{{ width: `${{pctR}}%` }}}}>{{pctR}}%</div>}}
                            </div>
                            <div className="flex gap-4 text-xs text-gray-500">
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-green-500" />Pagado ({{pctP}}%)</span>
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-yellow-400" />Ingresado ({{pctI}}%)</span>
                                <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-gray-300" />En Prep. ({{pctR}}%)</span>
                                <span className="font-medium text-gray-700">Total: {{formatUF(montoTotal)}}</span>
                            </div>
                        </div>
                    );
                }})()}}
            </div>

            <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                            <th className="py-2 px-4">EP #</th>
                            <th className="py-2 px-4">Fecha</th>
                            <th className="py-2 px-4 text-center">Beneficiarios</th>
                            <th className="py-2 px-4 text-right">Monto</th>
                            <th className="py-2 px-4 text-center">Estado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{epsArr.map(ep => (
                            <tr key={{ep.num}} className={{`border-b border-gray-100 ${{
                                ep.estado === "Pagado" ? "bg-green-50/50" :
                                ep.estado === "Ingresado" ? "bg-yellow-50/50" : ""
                            }}`}}>
                                <td className="py-2 px-4 font-bold text-gray-800">EP {{ep.num}}</td>
                                <td className="py-2 px-4 text-gray-600">{{formatFecha(ep.fecha)}}</td>
                                <td className="py-2 px-4 text-center text-gray-600">{{ep.beneficiarios}}</td>
                                <td className="py-2 px-4 text-right font-mono font-bold text-gray-800">{{formatUF(ep.monto)}}</td>
                                <td className="py-2 px-4 text-center">
                                    <span className={{`px-2 py-0.5 rounded-full text-xs font-semibold ${{
                                        ep.estado === "Pagado" ? "bg-green-100 text-green-700" :
                                        ep.estado === "Ingresado" ? "bg-yellow-100 text-yellow-700" :
                                        ep.estado === "Mixto" ? "bg-blue-100 text-blue-700" :
                                        "bg-gray-100 text-gray-600"
                                    }}`}}>{{ep.estado}}</span>
                                </td>
                            </tr>
                        ))}}
                    </tbody>
                    <tfoot>
                        <tr className="border-t-2 border-gray-300 bg-gray-50 font-bold">
                            <td className="py-2 px-4 text-gray-800">TOTAL</td>
                            <td className="py-2 px-4"></td>
                            <td className="py-2 px-4 text-center text-gray-600">{{viviendas.length}} benef.</td>
                            <td className="py-2 px-4 text-right font-mono text-gray-800">{{formatUF(montoTotal)}}</td>
                            <td className="py-2 px-4"></td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <h3 className="text-sm font-semibold text-gray-700">Detalle por Beneficiario</h3>
                    <p className="text-[10px] text-gray-400">Monto EP por beneficiario vs avance de obra. Diferencia positiva = obra adelante del cobro.</p>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                                <th className="py-2 px-3 sticky left-0 bg-gray-50 z-10 min-w-[160px]">Beneficiario</th>
                                {{epNums.map(n => (
                                    <th key={{n}} className="py-2 px-2 text-center text-xs min-w-[80px]">EP {{n}}</th>
                                ))}}
                                <th className="py-2 px-2 text-right text-xs">Total EP</th>
                                <th className="py-2 px-2 text-center text-xs">% Cobrado</th>
                                <th className="py-2 px-2 text-center text-xs">Avance</th>
                                <th className="py-2 px-2 text-center text-xs">Diferencia</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{benefArr.map(b => {{
                                const pctCobrado = b.total > 0 ? Math.round(b.pagado / b.total * 100) : 0;
                                const insp = getInspeccion(b.id);
                                const avance = insp ? insp.pct_total : 0;
                                const diff = avance - pctCobrado;
                                return (
                                    <tr key={{b.id}} className="border-b border-gray-100 hover:bg-gray-50">
                                        <td className="py-1.5 px-3 sticky left-0 bg-white z-10">
                                            <span className="text-xs font-medium text-gray-800">{{getNombreBenef(b.id)}}</span>
                                        </td>
                                        {{epNums.map(n => {{
                                            const ep = b.eps[n];
                                            if (!ep) return <td key={{n}} className="py-1.5 px-2 text-center text-gray-300 text-xs">\u2014</td>;
                                            return (
                                                <td key={{n}} className={{`py-1.5 px-2 text-center text-xs font-mono ${{
                                                    ep.estado.includes("Pagado") ? "bg-green-50 text-green-700 font-semibold" :
                                                    ep.estado.includes("Ingresado") ? "bg-yellow-50 text-yellow-700" :
                                                    "bg-gray-50 text-gray-500"
                                                }}`}}>
                                                    {{formatUF(ep.monto)}}
                                                </td>
                                            );
                                        }})}}
                                        <td className="py-1.5 px-2 text-right font-mono font-bold text-xs text-gray-800">{{formatUF(b.total)}}</td>
                                        <td className="py-1.5 px-2 text-center">
                                            <span className={{`font-mono font-bold text-xs ${{pctCobrado >= 80 ? "text-green-600" : pctCobrado >= 40 ? "text-yellow-600" : "text-gray-500"}}`}}>{{pctCobrado}}%</span>
                                        </td>
                                        <td className="py-1.5 px-2 text-center">
                                            <span className={{`font-mono font-bold text-xs ${{avance >= 80 ? "text-green-600" : avance >= 40 ? "text-blue-600" : "text-orange-500"}}`}}>{{avance}}%</span>
                                        </td>
                                        <td className="py-1.5 px-2 text-center">
                                            <span className={{`font-mono font-bold text-xs ${{diff > 10 ? "text-green-600" : diff < -10 ? "text-red-600" : "text-gray-500"}}`}}>
                                                {{diff > 0 ? "+" : ""}}{{diff}}%
                                            </span>
                                        </td>
                                    </tr>
                                );
                            }})}}
                        </tbody>
                    </table>
                </div>
                <div className="px-4 py-2 border-t border-gray-100 text-[9px] text-gray-400">
                    <span className="inline-block w-3 h-3 rounded-sm bg-green-50 border border-green-200 mr-1 align-middle" /> Pagado
                    <span className="inline-block w-3 h-3 rounded-sm bg-yellow-50 border border-yellow-200 mr-1 ml-3 align-middle" /> Ingresado
                    <span className="inline-block w-3 h-3 rounded-sm bg-gray-50 border border-gray-200 mr-1 ml-3 align-middle" /> En Preparación
                    <span className="ml-4">Diferencia = Avance obra - % Cobrado. Positivo (verde) = obra adelante del cobro.</span>
                </div>
            </div>
        </div>
    );
}};

// ===== CONFIGURACIÓN (Grupos + Diagrama + Editor) =====
const ConfiguracionView = ({{ grupos, setGrupos, viviendas, proyectoSel }}) => {{
    const originalConfig = ETAPAS_CONFIG_FULL;
    const [config, setConfig] = React.useState(() => JSON.parse(JSON.stringify(originalConfig)));
    const [subTab, setSubTab] = React.useState('grupos');
    const [dirty, setDirty] = React.useState(false);

    const etapas = config.etapas || {{}};
    const secuencia = config.secuencia_principal || [];
    const allKeys = Object.keys(etapas);

    const updateEtapa = (key, field, value) => {{
        setConfig(prev => {{
            const next = JSON.parse(JSON.stringify(prev));
            next.etapas[key][field] = value;
            return next;
        }});
        setDirty(true);
    }};

    const toggleSecuencia = (key) => {{
        setConfig(prev => {{
            const next = JSON.parse(JSON.stringify(prev));
            const idx = next.secuencia_principal.indexOf(key);
            if (idx >= 0) next.secuencia_principal.splice(idx, 1);
            else next.secuencia_principal.push(key);
            return next;
        }});
        setDirty(true);
    }};

    const toggleCritico = (key) => {{
        updateEtapa(key, 'critico', !etapas[key].critico);
    }};

    const restaurar = () => {{
        setConfig(JSON.parse(JSON.stringify(originalConfig)));
        setDirty(false);
    }};

    const exportarJSON = () => {{
        const exportData = JSON.parse(JSON.stringify(config));
        exportData._ultima_modificacion = new Date().toISOString().split('T')[0];
        const blob = new Blob([JSON.stringify(exportData, null, 2)], {{ type: 'application/json' }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'etapas_config.json';
        document.body.appendChild(a); a.click();
        document.body.removeChild(a); URL.revokeObjectURL(url);
    }};

    // BFS para niveles de dependencia
    const calcNiveles = () => {{
        const niveles = {{}};
        const visited = new Set();
        const queue = [];
        allKeys.forEach(k => {{
            if (!etapas[k].dependencia) {{
                niveles[k] = 0; visited.add(k); queue.push(k);
            }}
        }});
        while (queue.length > 0) {{
            const current = queue.shift();
            allKeys.forEach(k => {{
                if (!visited.has(k) && etapas[k].dependencia === current) {{
                    niveles[k] = (niveles[current] || 0) + 1;
                    visited.add(k); queue.push(k);
                }}
            }});
        }}
        const porNivel = {{}};
        Object.entries(niveles).forEach(([k, n]) => {{
            if (!porNivel[n]) porNivel[n] = [];
            porNivel[n].push(k);
        }});
        return porNivel;
    }};

    const niveles = calcNiveles();
    const maxNivel = Math.max(...Object.keys(niveles).map(Number), 0);

    // ===== Grupos editor state =====
    const [editingGrupos, setEditingGrupos] = React.useState(JSON.parse(JSON.stringify(grupos)));
    const [nuevoGrupoNombre, setNuevoGrupoNombre] = React.useState("");
    const [nuevoGrupoCapataz, setNuevoGrupoCapataz] = React.useState("");

    React.useEffect(() => {{
        setEditingGrupos(JSON.parse(JSON.stringify(grupos)));
    }}, [grupos]);

    const asignados = new Set();
    editingGrupos.forEach(g => g.beneficiarios.forEach(b => asignados.add(b)));
    const sinAsignar = viviendas.filter(v => !asignados.has(String(v.ID_Benef)));

    const agregarGrupo = () => {{
        if (!nuevoGrupoNombre.trim()) return;
        const newId = "G" + (editingGrupos.length + 1);
        setEditingGrupos([...editingGrupos, {{ id: newId, nombre: nuevoGrupoNombre.trim(), capataz: nuevoGrupoCapataz.trim(), beneficiarios: [] }}]);
        setNuevoGrupoNombre(""); setNuevoGrupoCapataz("");
    }};

    const moverAGrupo = (benefId, grupoId) => {{
        setEditingGrupos(prev => prev.map(g => ({{
            ...g,
            beneficiarios: g.id === grupoId
                ? [...g.beneficiarios, benefId]
                : g.beneficiarios.filter(b => b !== benefId)
        }})));
    }};

    const quitarDeGrupo = (benefId, grupoId) => {{
        setEditingGrupos(prev => prev.map(g =>
            g.id === grupoId ? {{...g, beneficiarios: g.beneficiarios.filter(b => b !== benefId)}} : g
        ));
    }};

    const eliminarGrupo = (grupoId) => {{
        setEditingGrupos(prev => prev.filter(g => g.id !== grupoId));
    }};

    const aplicarCambios = () => {{
        setGrupos(editingGrupos);
    }};

    // ===== DIAGRAMA SUB-TAB =====
    const DiagramaTab = () => {{
        const NODE_W = 150, NODE_H = 80, LEVEL_GAP = 60, NODE_GAP = 16;
        const maxNodesInLevel = Math.max(...Object.values(niveles).map(arr => arr.length), 1);
        const svgHeight = Math.max(maxNodesInLevel * (NODE_H + NODE_GAP) + 40, 300);
        const svgWidth = (maxNivel + 1) * (NODE_W + LEVEL_GAP) + 60;

        const positions = {{}};
        Object.entries(niveles).forEach(([nivel, keys]) => {{
            const n = Number(nivel);
            const totalH = keys.length * NODE_H + (keys.length - 1) * NODE_GAP;
            const startY = (svgHeight - totalH) / 2;
            keys.forEach((k, i) => {{
                positions[k] = {{ x: 30 + n * (NODE_W + LEVEL_GAP), y: startY + i * (NODE_H + NODE_GAP) }};
            }});
        }});

        const esCritica = (k) => secuencia.includes(k);
        const esFlexible = (k) => etapas[k].flexible || etapas[k].ventana_flexible;

        return (
            <div className="overflow-auto bg-gray-50 border border-gray-200 rounded-lg p-4">
                <svg width={{svgWidth}} height={{svgHeight}} className="block">
                    {{allKeys.map(k => {{
                        const dep = etapas[k].dependencia;
                        if (!dep || !positions[dep] || !positions[k]) return null;
                        const from = positions[dep]; const to = positions[k];
                        const x1 = from.x + NODE_W, y1 = from.y + NODE_H / 2;
                        const x2 = to.x, y2 = to.y + NODE_H / 2;
                        const midX = (x1 + x2) / 2;
                        const isCrit = esCritica(k) && esCritica(dep);
                        return (
                            <g key={{`conn-${{k}}`}}>
                                <path d={{`M${{x1}},${{y1}} C${{midX}},${{y1}} ${{midX}},${{y2}} ${{x2}},${{y2}}`}} fill="none" stroke={{isCrit ? "#8b5cf6" : "#d1d5db"}} strokeWidth={{isCrit ? 2.5 : 1.5}} strokeDasharray={{esFlexible(k) ? "6,3" : "none"}} />
                                <polygon points={{`${{x2}},${{y2}} ${{x2-8}},${{y2-4}} ${{x2-8}},${{y2+4}}`}} fill={{isCrit ? "#8b5cf6" : "#d1d5db"}} />
                            </g>
                        );
                    }})}}
                    {{allKeys.map(k => {{
                        const pos = positions[k]; if (!pos) return null;
                        const e = etapas[k];
                        const crit = esCritica(k);
                        const flex = esFlexible(k);
                        return (
                            <g key={{k}} transform={{`translate(${{pos.x}},${{pos.y}})`}}>
                                <rect width={{NODE_W}} height={{NODE_H}} rx={{8}} ry={{8}} fill={{crit ? "#faf5ff" : flex ? "#f9fafb" : "white"}} stroke={{crit ? "#8b5cf6" : flex ? "#9ca3af" : "#e5e7eb"}} strokeWidth={{crit ? 2.5 : 1.5}} strokeDasharray={{flex ? "6,3" : "none"}} />
                                <text x={{NODE_W/2}} y={{20}} textAnchor="middle" fontSize="11" fontWeight="600" fill={{crit ? "#6d28d9" : "#374151"}}>{{e.nombre}}</text>
                                <text x={{NODE_W/2}} y={{35}} textAnchor="middle" fontSize="10" fill="#9ca3af" fontFamily="IBM Plex Mono">{{e.codigo}} {{crit ? "| CRITICO" : flex ? "| flexible" : ""}}</text>
                                <text x={{NODE_W/2}} y={{52}} textAnchor="middle" fontSize="10" fill="#6b7280">Duración: {{e.duracion}}d</text>
                                {{e.tiempo_optimo !== null && (
                                    <g>
                                        <rect x={{10}} y={{60}} width={{(NODE_W-20)*0.5}} height={{6}} rx={{3}} fill="#22c55e" opacity={{0.6}} />
                                        <rect x={{10 + (NODE_W-20)*0.5}} y={{60}} width={{(NODE_W-20)*0.5}} height={{6}} rx={{3}} fill="#eab308" opacity={{0.6}} />
                                        <text x={{18}} y={{69}} fontSize="8" fill="#166534">{{e.tiempo_optimo}}d</text>
                                        <text x={{NODE_W-30}} y={{69}} fontSize="8" fill="#854d0e">{{e.tiempo_alerta}}d</text>
                                    </g>
                                )}}
                            </g>
                        );
                    }})}}
                </svg>
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500 border-t border-gray-200 pt-3">
                    <div className="flex items-center gap-2"><div className="w-8 h-4 rounded border-2 border-violet-500 bg-violet-50" /><span>Ruta crítica</span></div>
                    <div className="flex items-center gap-2"><div className="w-8 h-4 rounded border-2 border-gray-300 border-dashed bg-gray-50" /><span>Etapa flexible</span></div>
                    <div className="flex items-center gap-2"><div className="w-8 h-4 rounded border-2 border-gray-200 bg-white" /><span>Etapa estándar</span></div>
                    <div className="flex items-center gap-2"><div className="w-8 h-0.5 bg-violet-500" /><span>Dependencia crítica</span></div>
                    <div className="flex items-center gap-2"><div className="flex gap-0.5"><div className="w-4 h-2 rounded bg-green-500 opacity-60" /><div className="w-4 h-2 rounded bg-yellow-500 opacity-60" /></div><span>Tiempos: óptimo | alerta</span></div>
                </div>
            </div>
        );
    }};

    // ===== EDITOR SUB-TAB =====
    const EditorTab = () => {{
        return (
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                            <th className="py-2 px-3">Cód</th>
                            <th className="py-2 px-3">Etapa</th>
                            <th className="py-2 px-3 text-center">Duración</th>
                            <th className="py-2 px-3 text-center">T. Óptimo</th>
                            <th className="py-2 px-3 text-center">T. Alerta</th>
                            <th className="py-2 px-3">Depende de</th>
                            <th className="py-2 px-3 text-center">Crítica</th>
                            <th className="py-2 px-3 text-center">En Secuencia</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{allKeys.map((key) => {{
                            const e = etapas[key];
                            const enSeq = secuencia.includes(key);
                            return (
                                <tr key={{key}} className={{`border-b border-gray-100 ${{enSeq ? "bg-violet-50/50" : ""}}`}}>
                                    <td className="py-2 px-3 font-mono text-gray-600">{{e.codigo}}</td>
                                    <td className="py-2 px-3 text-gray-800 font-medium">{{e.nombre}}</td>
                                    <td className="py-2 px-3 text-center">
                                        <input type="number" min="1" max="60" value={{e.duracion || 0}} onChange={{(ev) => updateEtapa(key, 'duracion', parseInt(ev.target.value) || 0)}} className="w-14 text-center border border-gray-300 rounded px-1 py-0.5 text-sm focus:ring-1 focus:ring-violet-400 focus:border-violet-400" />
                                    </td>
                                    <td className="py-2 px-3 text-center">
                                        <input type="number" min="0" max="60" value={{e.tiempo_optimo ?? ''}} placeholder="-" onChange={{(ev) => {{ const v = ev.target.value === '' ? null : parseInt(ev.target.value); updateEtapa(key, 'tiempo_optimo', v); }}}} className="w-14 text-center border border-gray-300 rounded px-1 py-0.5 text-sm focus:ring-1 focus:ring-green-400 focus:border-green-400" />
                                    </td>
                                    <td className="py-2 px-3 text-center">
                                        <input type="number" min="0" max="60" value={{e.tiempo_alerta ?? ''}} placeholder="-" onChange={{(ev) => {{ const v = ev.target.value === '' ? null : parseInt(ev.target.value); updateEtapa(key, 'tiempo_alerta', v); }}}} className="w-14 text-center border border-gray-300 rounded px-1 py-0.5 text-sm focus:ring-1 focus:ring-red-400 focus:border-red-400" />
                                    </td>
                                    <td className="py-2 px-3">
                                        <select value={{e.dependencia || ''}} onChange={{(ev) => updateEtapa(key, 'dependencia', ev.target.value || null)}} className="w-full border border-gray-300 rounded px-1 py-0.5 text-sm text-gray-700 focus:ring-1 focus:ring-violet-400 bg-white">
                                            <option value="">\u2014 Ninguna \u2014</option>
                                            {{allKeys.filter(k => k !== key).map(k => (
                                                <option key={{k}} value={{k}}>{{etapas[k].nombre}} ({{etapas[k].codigo}})</option>
                                            ))}}
                                        </select>
                                    </td>
                                    <td className="py-2 px-3 text-center">
                                        <input type="checkbox" checked={{!!e.critico}} onChange={{() => toggleCritico(key)}} className="w-4 h-4 rounded border-gray-300 text-violet-600 focus:ring-violet-400" />
                                    </td>
                                    <td className="py-2 px-3 text-center">
                                        <input type="checkbox" checked={{enSeq}} onChange={{() => toggleSecuencia(key)}} className="w-4 h-4 rounded border-gray-300 text-violet-600 focus:ring-violet-400" />
                                    </td>
                                </tr>
                            );
                        }})}}
                    </tbody>
                </table>
            </div>
        );
    }};

    return (
        <div>
            {{/* Sub-tabs */}}
            <div className="flex items-center justify-between mb-4">
                <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm">
                    {{[["grupos", "Grupos de Trabajo"], ["diagrama", "Diagrama de Dependencias"], ["editor", "Editor de Tiempos"]].map(([k, l]) => (
                        <button key={{k}} onClick={{() => setSubTab(k)}} className={{`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${{subTab === k ? "bg-raices-red text-white" : "text-gray-600 hover:bg-gray-100"}}`}}>
                            {{l}}
                        </button>
                    ))}}
                </div>
                {{subTab !== 'grupos' && (
                    <div className="flex items-center gap-2">
                        {{dirty && <span className="text-xs text-orange-500 font-medium mr-2">Cambios sin guardar</span>}}
                        <button onClick={{restaurar}} className="px-3 py-1.5 text-sm border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors">Restaurar Original</button>
                        <button onClick={{exportarJSON}} className="px-3 py-1.5 text-sm bg-raices-red text-white rounded-lg hover:bg-opacity-90 transition-colors flex items-center gap-1"><IconDownload /> Exportar JSON</button>
                    </div>
                )}}
            </div>

            {{/* ========== GRUPOS ========== */}}
            {{subTab === 'grupos' && (
                <div className="space-y-4">
                    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                        <h3 className="text-sm font-semibold text-blue-800 mb-1">Grupos de Trabajo por Capataz</h3>
                        <p className="text-xs text-blue-600 leading-relaxed">
                            Agrupa beneficiarios bajo un capataz. Los grupos se reflejan en las pestañas Viviendas y Matriz.
                            Los beneficiarios sin grupo se ordenan automáticamente por fecha de primer despacho.
                            Los datos se guardan en Firebase (compartidos entre dispositivos).
                        </p>
                    </div>

                    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                        <h4 className="text-sm font-semibold text-gray-700 mb-3">Crear Nuevo Grupo</h4>
                        <div className="flex items-end gap-3">
                            <div className="flex-1">
                                <label className="text-[10px] text-gray-500 font-medium">Nombre del Grupo</label>
                                <input type="text" value={{nuevoGrupoNombre}} onChange={{e => setNuevoGrupoNombre(e.target.value)}} placeholder="Ej: Grupo 4" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 mt-0.5" />
                            </div>
                            <div className="flex-1">
                                <label className="text-[10px] text-gray-500 font-medium">Capataz</label>
                                <input type="text" value={{nuevoGrupoCapataz}} onChange={{e => setNuevoGrupoCapataz(e.target.value)}} placeholder="Ej: Roberto Figueroa" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 mt-0.5" />
                            </div>
                            <button onClick={{agregarGrupo}} className="px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 transition-colors whitespace-nowrap">+ Crear Grupo</button>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {{editingGrupos.map((grupo, gIdx) => {{
                            const c = GRUPO_COLORS[gIdx % GRUPO_COLORS.length];
                            const gVivs = grupo.beneficiarios.map(bid => viviendas.find(v => String(v.ID_Benef) === bid)).filter(Boolean);
                            const res = grupoResumen(gVivs);
                            return (
                                <div key={{grupo.id}} className={{`${{c.bg}} border ${{c.border}} rounded-xl overflow-hidden`}}>
                                    <div className="p-3 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <div className={{`w-7 h-7 ${{c.accent}} rounded-lg flex items-center justify-center`}}>
                                                <span className="text-white text-[10px] font-bold">{{grupo.id}}</span>
                                            </div>
                                            <div>
                                                <h4 className={{`text-sm font-bold ${{c.text}}`}}>{{grupo.nombre}}</h4>
                                                {{grupo.capataz && <p className="text-[10px] text-gray-500">Capataz: {{grupo.capataz}}</p>}}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-gray-500">{{res.n}} viv. — Avance: {{res.pctAvance}}%</span>
                                            <button onClick={{() => eliminarGrupo(grupo.id)}} className="text-red-400 hover:text-red-600 text-xs px-1.5 py-0.5 rounded hover:bg-red-50" title="Eliminar grupo">x</button>
                                        </div>
                                    </div>
                                    <div className="bg-white/70 p-2 space-y-1 max-h-[200px] overflow-y-auto">
                                        {{gVivs.length === 0 && <p className="text-xs text-gray-400 text-center py-3">Sin beneficiarios asignados</p>}}
                                        {{gVivs.map(v => (
                                            <div key={{v.ID_Benef}} className="flex items-center justify-between px-2 py-1 rounded hover:bg-gray-50 text-xs group">
                                                <div className="flex items-center gap-2">
                                                    <span className={{`w-2 h-2 rounded-full ${{
                                                        v.estadoGeneral === "critico" ? "bg-red-500" :
                                                        v.estadoGeneral === "atencion" ? "bg-yellow-500" :
                                                        v.estadoGeneral === "en_tiempo" ? "bg-green-500" : "bg-gray-300"
                                                    }}`}} />
                                                    <span className="text-gray-700 font-medium">{{v.NOMBRES}} {{v.APELLIDOS}}</span>
                                                    <span className="text-gray-400">{{v.tipologia}}</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-gray-400 font-mono text-[10px]">{{v.avance.porcentaje}}%</span>
                                                    <button onClick={{() => quitarDeGrupo(String(v.ID_Benef), grupo.id)}} className="text-red-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">quitar</button>
                                                </div>
                                            </div>
                                        ))}}
                                    </div>
                                    {{sinAsignar.length > 0 && (
                                        <div className="p-2 border-t border-gray-100">
                                            <select className="w-full text-xs border border-gray-200 rounded px-2 py-1.5 bg-white text-gray-500 focus:outline-none focus:ring-1 focus:ring-violet-400" defaultValue="" onChange={{e => {{ if(e.target.value) {{ moverAGrupo(e.target.value, grupo.id); e.target.value=""; }} }}}}>
                                                <option value="">+ Agregar beneficiario...</option>
                                                {{sinAsignar.map(v => <option key={{v.ID_Benef}} value={{String(v.ID_Benef)}}>{{v.NOMBRES}} {{v.APELLIDOS}} ({{v.tipologia}}) — {{v.avance.porcentaje}}%</option>)}}
                                            </select>
                                        </div>
                                    )}}
                                </div>
                            );
                        }})}}
                    </div>

                    {{sinAsignar.length > 0 && (
                        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-4">
                            <div className="flex items-center justify-between mb-3">
                                <h4 className="text-sm font-semibold text-gray-500">Sin Asignar a Grupo</h4>
                                <span className="text-xs text-gray-400">{{sinAsignar.length}} beneficiarios — se ordenan por fecha de primer despacho</span>
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                                {{sinAsignar.map(v => (
                                    <div key={{v.ID_Benef}} className="flex items-center gap-2 px-2 py-1.5 rounded border border-gray-200 text-xs bg-gray-50 hover:bg-gray-100">
                                        <span className={{`w-2 h-2 rounded-full ${{
                                            v.estadoGeneral === "critico" ? "bg-red-500" :
                                            v.estadoGeneral === "atencion" ? "bg-yellow-500" :
                                            v.estadoGeneral === "en_tiempo" ? "bg-green-500" : "bg-gray-300"
                                        }}`}} />
                                        <span className="text-gray-700 font-medium truncate">{{v.NOMBRES}} {{v.APELLIDOS}}</span>
                                        <span className="text-gray-400 font-mono text-[10px] ml-auto">{{v.avance.porcentaje}}%</span>
                                    </div>
                                ))}}
                            </div>
                        </div>
                    )}}

                    <div className="flex items-center justify-between bg-gray-50 rounded-xl border border-gray-200 p-4">
                        <p className="text-[10px] text-gray-400">Los cambios se reflejan en las pestañas Viviendas y Matriz al aplicar</p>
                        <div className="flex gap-2">
                            <button onClick={{() => setEditingGrupos(JSON.parse(JSON.stringify(grupos)))}} className="px-3 py-1.5 text-xs bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300">Descartar</button>
                            <button onClick={{aplicarCambios}} className="px-4 py-1.5 text-xs bg-violet-600 text-white rounded-lg hover:bg-violet-700 font-medium">Aplicar Grupos</button>
                        </div>
                    </div>
                </div>
            )}}

            {{/* ========== DIAGRAMA ========== */}}
            {{subTab === 'diagrama' && <DiagramaTab />}}

            {{/* ========== EDITOR ========== */}}
            {{subTab === 'editor' && <EditorTab />}}

            {{subTab !== 'grupos' && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-xs text-yellow-700">
                    <strong>Nota:</strong> Para aplicar cambios al dashboard, exporta el JSON y reemplaza <code className="bg-yellow-100 px-1 rounded">config/etapas_config.json</code>, luego regenera el dashboard.
                </div>
            )}}
        </div>
    );
}};

// ===== APP PRINCIPAL =====
const App = () => {{
    const defaultProy = [...PROYECTOS_DATA].sort((a, b) => (b.fecha_inicio || '').localeCompare(a.fecha_inicio || ''))[0]?.ID_proy || "";
    const [proyectoSel, setProyectoSel] = React.useState(defaultProy);
    const [tab, setTab] = React.useState("viviendas");
    const [expandida, setExpandida] = React.useState(null);
    const [filtro, setFiltro] = React.useState("todos");
    const [busqueda, setBusqueda] = React.useState("");

    // Grupos con persistencia en Firebase
    const [gruposConfig, setGruposConfig] = React.useState({{}});
    const [fbReady, setFbReady] = React.useState(false);
    const gruposRef = React.useRef(null);
    const obsRef = React.useRef(null);
    const actRef = React.useRef(null);
    const consultasRef = React.useRef(null);
    const skipGruposPush = React.useRef(true);
    const skipObsPush = React.useRef(true);
    const skipActPush = React.useRef(true);
    const skipConsPush = React.useRef(true);

    React.useEffect(() => {{
        // Listener Firebase para Grupos
        gruposRef.current = fbDB.ref('grupos');
        gruposRef.current.on('value', (snap) => {{
            const val = snap.val();
            skipGruposPush.current = true;
            setGruposConfig(val || {{}});
        }});
        // Listener Firebase para Observaciones
        obsRef.current = fbDB.ref('observaciones');
        obsRef.current.on('value', (snap) => {{
            const val = snap.val();
            skipObsPush.current = true;
            setObservaciones(val || {{}});
            setFbReady(true);
        }});
        // Listener Firebase para Actividades de Habilitacion
        actRef.current = fbDB.ref('actividades');
        actRef.current.on('value', (snap) => {{
            const val = snap.val();
            skipActPush.current = true;
            setActividades(val || {{}});
        }});
        // Listener Firebase para Consultas por Etapa
        consultasRef.current = fbDB.ref('consultas');
        consultasRef.current.on('value', (snap) => {{
            const val = snap.val();
            skipConsPush.current = true;
            setConsultas(val || {{}});
        }});
        return () => {{
            if (gruposRef.current) gruposRef.current.off();
            if (obsRef.current) obsRef.current.off();
            if (actRef.current) actRef.current.off();
            if (consultasRef.current) consultasRef.current.off();
        }};
    }}, []);

    // Push grupos a Firebase cuando cambia localmente
    React.useEffect(() => {{
        if (skipGruposPush.current) {{ skipGruposPush.current = false; return; }}
        if (gruposRef.current) gruposRef.current.set(gruposConfig);
    }}, [gruposConfig]);

    // Observaciones por beneficiario (Firebase)
    const [observaciones, setObservaciones] = React.useState({{}});
    const [showResumenObs, setShowResumenObs] = React.useState(false);

    // Push observaciones a Firebase cuando cambia localmente
    React.useEffect(() => {{
        if (skipObsPush.current) {{ skipObsPush.current = false; return; }}
        if (obsRef.current) obsRef.current.set(observaciones);
    }}, [observaciones]);

    // Actividades de habilitacion por beneficiario (Firebase)
    const [actividades, setActividades] = React.useState({{}});

    React.useEffect(() => {{
        if (skipActPush.current) {{ skipActPush.current = false; return; }}
        if (actRef.current) actRef.current.set(actividades);
    }}, [actividades]);

    // Consultas por etapa (Firebase)
    const [consultas, setConsultas] = React.useState({{}});

    React.useEffect(() => {{
        if (skipConsPush.current) {{ skipConsPush.current = false; return; }}
        if (consultasRef.current) consultasRef.current.set(consultas);
    }}, [consultas]);

    const toggleConsulta = (idBenef, etapaKey) => {{
        setConsultas(prev => {{
            const benCons = prev[idBenef] || {{}};
            const next = {{ ...prev }};
            if (benCons[etapaKey]) {{
                const {{ [etapaKey]: _, ...rest }} = benCons;
                if (Object.keys(rest).length === 0) delete next[idBenef];
                else next[idBenef] = rest;
            }} else {{
                next[idBenef] = {{ ...benCons, [etapaKey]: {{ done: true, fecha: fechaChile() }} }};
            }}
            fbDB.ref('consultas').set(next);
            return next;
        }});
    }};

    const toggleActividad = (idBenef, actNombre) => {{
        setActividades(prev => {{
            const benActs = prev[idBenef] || {{}};
            const next = {{ ...prev }};
            if (benActs[actNombre]) {{
                const {{ [actNombre]: _, ...rest }} = benActs;
                if (Object.keys(rest).length === 0) delete next[idBenef];
                else next[idBenef] = rest;
            }} else {{
                next[idBenef] = {{ ...benActs, [actNombre]: {{ done: true, fecha: fechaChile() }} }};
            }}
            fbDB.ref('actividades').set(next);
            return next;
        }});
    }};

    const addObservacion = (idBenef, texto) => {{
        setObservaciones(prev => {{
            const obs = prev[idBenef] || [];
            const next = {{ ...prev, [idBenef]: [...obs, {{ texto, fecha: fechaChile(), id: Date.now() }}] }};
            fbDB.ref('observaciones').set(next);
            return next;
        }});
    }};

    const deleteObservacion = (idBenef, obsId) => {{
        setObservaciones(prev => {{
            const obs = (prev[idBenef] || []).filter(o => o.id !== obsId);
            const next = {{ ...prev }};
            if (obs.length === 0) delete next[idBenef];
            else next[idBenef] = obs;
            fbDB.ref('observaciones').set(next);
            return next;
        }});
    }};

    const beneficiarios = React.useMemo(() => BENEFICIARIOS_DATA.filter(b => String(b.ID_Proy) === String(proyectoSel)), [proyectoSel]);

    const viviendas = React.useMemo(() => beneficiarios.map(b => {{
        const estados = calcularEstadoEtapas(b.ID_Benef);
        const desps = DESPACHOS_DATA.filter(d => String(d.ID_Benef) === String(b.ID_Benef));
        const numDespachos = desps.length;
        const primerDespacho = desps.length > 0 ? desps.reduce((min, d) => d.Fecha < min ? d.Fecha : min, desps[0].Fecha) : "9999";
        return {{ ...b, estadoEtapas: estados, estadoGeneral: getEstadoGeneral(estados), avance: calcularAvance(estados), numDespachos, primerDespacho }};
    }}), [beneficiarios]);

    const proy = PROYECTOS_DATA.find(p => String(p.ID_proy) === String(proyectoSel));
    const grupos = gruposConfig[proyectoSel] || [];

    const setGruposForProy = (newGrupos) => {{
        setGruposConfig(prev => ({{...prev, [proyectoSel]: newGrupos}}));
    }};

    // KPIs
    const kpis = React.useMemo(() => {{
        const avanceDesp = viviendas.length ? Math.round(viviendas.reduce((s, v) => s + v.avance.porcentaje, 0) / viviendas.length) : 0;
        const conInsp = viviendas.filter(v => getInspeccion(v.ID_Benef));
        const avanceInsp = conInsp.length ? Math.round(conInsp.reduce((s, v) => s + getInspeccion(v.ID_Benef).pct_total, 0) / conInsp.length) : 0;
        const totalPagadoProy = viviendas.reduce((s, v) => s + getTotalPagado(v.ID_Benef), 0);
        const conAlertasRojas = viviendas.filter(v => calcCoherencia(v.ID_Benef, v.estadoEtapas).some(a => a.tipo === "rojo")).length;

        const terminadas = viviendas.filter(v => {{
            const insp = getInspeccion(v.ID_Benef);
            const todasDesp = SECUENCIA_PRINCIPAL.every(k => v.estadoEtapas[k]?.estado === "despachado");
            return todasDesp && insp && insp.pct_total >= 90;
        }}).length;

        // Solicitudes pendientes
        const totalSolicitadas = viviendas.reduce((s, v) => s + Object.values(v.estadoEtapas).filter(e => e.estado === "solicitado").length, 0);

        // Dias promedio fund -> ultima etapa
        let diasTotal = 0, diasCount = 0;
        viviendas.filter(v => v.numDespachos > 0).forEach(v => {{
            const fund = v.estadoEtapas["01_FUNDACIONES"];
            if (fund?.fechaDespacho) {{
                let maxFecha = new Date(fund.fechaDespacho);
                Object.values(v.estadoEtapas).forEach(info => {{
                    if (info.estado === "despachado" && info.fechaDespacho) {{
                        const f = new Date(info.fechaDespacho);
                        if (f > maxFecha) maxFecha = f;
                    }}
                }});
                const dias = Math.floor((maxFecha - new Date(fund.fechaDespacho)) / (1000*60*60*24));
                if (dias > 0) {{ diasTotal += dias; diasCount++; }}
            }}
        }});
        const diasPromedio = diasCount > 0 ? Math.round(diasTotal / diasCount) : 0;

        return {{
            total: viviendas.length, terminadas,
            enTiempo: viviendas.filter(v => v.estadoGeneral === "en_tiempo").length,
            atencion: viviendas.filter(v => v.estadoGeneral === "atencion").length,
            criticos: viviendas.filter(v => v.estadoGeneral === "critico").length,
            avance: avanceDesp, avanceInsp, totalPagado: totalPagadoProy,
            alertasCoherencia: conAlertasRojas, totalSolicitadas, diasPromedio
        }};
    }}, [viviendas]);

    // Contrato info
    const contratoInfo = React.useMemo(() => {{
        if (!proy) return null;
        const fi = proy.fecha_inicio;
        const dur = proy.duracion;
        if (!fi || !dur) return null;
        const inicio = new Date(fi);
        const vencimiento = new Date(inicio);
        vencimiento.setDate(vencimiento.getDate() + dur);
        const hoy = new Date();
        const diasRestantes = Math.floor((vencimiento - hoy) / (1000*60*60*24));
        return {{ inicio: fi, duracion: dur, vencimiento: vencimiento.toISOString().substring(0,10), diasRestantes }};
    }}, [proy]);

    const garantiasProy = React.useMemo(() => {{
        if (!proy) return [];
        return GARANTIAS_DATA.filter(g => g.ID_Proy === proy.ID_proy).map(g => {{
            const hoy = new Date();
            const fv = g.fecha_vcmto ? new Date(g.fecha_vcmto) : null;
            const diasVcmto = fv ? Math.floor((fv - hoy) / (1000*60*60*24)) : null;
            return {{ ...g, diasVcmto }};
        }});
    }}, [proy]);

    const eeppProy = React.useMemo(() => {{
        const idsProyecto = new Set(viviendas.map(v => String(v.ID_Benef)));
        return EEPP_DATA.filter(ep => idsProyecto.has(String(ep.ID_Benef)));
    }}, [viviendas]);

    const eeppResumen = React.useMemo(() => {{
        const pagado = eeppProy.filter(e => e.Estado.includes("Pagado"));
        const ingresado = eeppProy.filter(e => e.Estado.includes("Ingresado"));
        const prep = eeppProy.filter(e => !e.Estado.includes("Pagado") && !e.Estado.includes("Ingresado"));
        const montoPag = pagado.reduce((s, e) => s + e.Monto, 0);
        const montoIng = ingresado.reduce((s, e) => s + e.Monto, 0);
        const montoPrep = prep.reduce((s, e) => s + e.Monto, 0);
        return {{ pagado: montoPag, ingresado: montoIng, preparacion: montoPrep, total: montoPag + montoIng + montoPrep }};
    }}, [eeppProy]);

    const formatUF = (val) => {{
        if (!val && val !== 0) return '\u2014';
        return val.toLocaleString('es-CL', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + ' UF';
    }};
    const formatFecha = (iso) => {{
        if (!iso) return '\u2014';
        const [y,m,d] = iso.split('-');
        return `${{d}}/${{m}}/${{y}}`;
    }};

    const tabs = [["viviendas","Viviendas"],["matriz","Matriz"],["distribucion","Distribución"],["financiero","Financiero"],["mano_obra","M.O."],["estados_pago","Estados de Pago"],["configuracion","Configuración"]];

    return (
        <div className="min-h-screen bg-gray-50">
            {{/* TOP BAR */}}
            <div className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
                <div className="max-w-[1400px] mx-auto px-4 py-3">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center text-white font-bold text-sm">SC</div>
                            <span className="text-sm font-bold text-gray-600 hidden sm:inline">SCRaices v3</span>
                        </div>
                        <select className="bg-gray-50 border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-700 flex-1 max-w-md focus:outline-none focus:ring-2 focus:ring-violet-500" value={{proyectoSel}} onChange={{e => {{ setProyectoSel(e.target.value); setExpandida(null); setTab("viviendas"); }}}}>
                            {{PROYECTOS_DATA.map(p => <option key={{p.ID_proy}} value={{p.ID_proy}}>{{p.estado === 'finalizado' ? '[F] ' : ''}}{{p.NOMBRE_PROYECTO}} — {{p.COMUNA}} ({{BENEFICIARIOS_DATA.filter(b => String(b.ID_Proy) === String(p.ID_proy)).length}} viv.)</option>)}}
                        </select>
                        {{grupos.length > 0 && <div className="flex items-center gap-1.5 text-xs text-gray-500"><IconGroup /><span>{{grupos.length}} grupos</span></div>}}
                    </div>
                </div>
            </div>

            <div className="max-w-[1400px] mx-auto px-4 py-4">
                {{/* HEADER: Contrato + Garantías + EP */}}
                <HeaderProyecto proy={{proy}} garantiasProy={{garantiasProy}} eeppResumen={{eeppResumen}} />

                {{/* KPIs */}}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-4">
                    <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm"><p className="text-[10px] text-gray-500 uppercase">Viviendas</p><p className="text-xl font-bold font-mono">{{kpis.total}}</p></div>
                    <div className="bg-white rounded-xl p-3 border border-green-200 shadow-sm"><p className="text-[10px] text-green-600">Terminadas</p><p className="text-xl font-bold font-mono text-green-700">{{kpis.terminadas}}</p><p className="text-[9px] text-gray-400">{{kpis.total > 0 ? Math.round(kpis.terminadas/kpis.total*100) : 0}}%</p></div>
                    <div className="bg-white rounded-xl p-3 border border-green-200 shadow-sm"><p className="text-[10px] text-green-600">En Tiempo</p><p className="text-xl font-bold font-mono text-green-600">{{kpis.enTiempo}}</p></div>
                    <div className="bg-white rounded-xl p-3 border border-yellow-200 shadow-sm"><p className="text-[10px] text-yellow-600">Atención</p><p className="text-xl font-bold font-mono text-yellow-600">{{kpis.atencion}}</p></div>
                    <div className="bg-white rounded-xl p-3 border border-red-200 shadow-sm"><p className="text-[10px] text-red-600">Críticas</p><p className="text-xl font-bold font-mono text-red-600">{{kpis.criticos}}</p>{{kpis.alertasCoherencia > 0 && <p className="text-[9px] text-red-400">{{kpis.alertasCoherencia}} alertas</p>}}</div>
                    <div className="bg-white rounded-xl p-3 border border-purple-200 shadow-sm"><p className="text-[10px] text-purple-600">Solicitadas</p><p className="text-xl font-bold font-mono text-purple-600">{{kpis.totalSolicitadas}}</p><p className="text-[9px] text-gray-400">esperando desp.</p></div>
                    <div className="bg-white rounded-xl p-3 border border-gray-200 shadow-sm"><p className="text-[10px] text-gray-500">Días Prom.</p><p className="text-xl font-bold font-mono">{{kpis.diasPromedio}}d</p><p className="text-[9px] text-gray-400">Fund → última</p></div>
                    <div className="bg-white rounded-xl p-3 border border-violet-200 shadow-sm"><p className="text-[10px] text-violet-600">Total Pagado</p><p className="text-lg font-bold font-mono text-violet-700">{{formatPeso(kpis.totalPagado)}}</p></div>
                </div>

                {{/* TABS */}}
                <div className="flex items-center gap-1 mb-4 overflow-x-auto hide-scrollbar border-b border-gray-200 pb-px">
                    {{tabs.map(([key, label]) => (
                        <button key={{key}} onClick={{() => setTab(key)}} className={{`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap ${{tab === key ? "bg-white text-violet-700 border border-gray-200 border-b-white shadow-sm -mb-px" : "text-gray-500 hover:text-gray-700 hover:bg-gray-100"}}`}}>
                            {{label}}
                            {{key === "viviendas" && kpis.criticos > 0 && <span className="ml-2 bg-red-500 text-white text-[10px] px-1.5 py-0.5 rounded-full">{{kpis.criticos}}</span>}}
                            {{key === "configuracion" && grupos.length > 0 && <span className="ml-1.5 bg-violet-100 text-violet-600 text-[10px] px-1.5 py-0.5 rounded-full">{{grupos.length}}G</span>}}
                        </button>
                    ))}}
                </div>

                {{/* CONTENIDO */}}
                <div className="min-h-[500px]">
                    {{tab === "viviendas" && <ViviendasTab viviendas={{viviendas}} grupos={{grupos}} expandida={{expandida}} setExpandida={{setExpandida}} filtro={{filtro}} setFiltro={{setFiltro}} busqueda={{busqueda}} setBusqueda={{setBusqueda}} observaciones={{observaciones}} addObservacion={{addObservacion}} deleteObservacion={{deleteObservacion}} showResumenObs={{showResumenObs}} setShowResumenObs={{setShowResumenObs}} actividades={{actividades}} toggleActividad={{toggleActividad}} consultas={{consultas}} toggleConsulta={{toggleConsulta}} />}}
                    {{tab === "matriz" && <MatrizAvance viviendas={{viviendas}} grupos={{grupos}} />}}
                    {{tab === "distribucion" && <DistribucionTab viviendas={{viviendas}} />}}
                    {{tab === "financiero" && <FinancieroTab viviendas={{viviendas}} />}}
                    {{tab === "mano_obra" && <ManoDeObraTab viviendas={{viviendas}} />}}
                    {{tab === "estados_pago" && <EstadosPagoTab viviendas={{viviendas}} />}}
                    {{tab === "configuracion" && <ConfiguracionView grupos={{grupos}} setGrupos={{setGruposForProy}} viviendas={{viviendas}} proyectoSel={{proyectoSel}} />}}
                </div>

                {{/* Leyenda */}}
                <div className="mt-6 flex items-center justify-center gap-6 text-[10px] text-gray-400">
                    {{[["bg-blue-500","Despachado"],["bg-purple-500","Solicitado"],["bg-green-500","En Tiempo"],["bg-yellow-500","Atención"],["bg-red-500","Crítico"],["bg-gray-300","Bloqueado"]].map(([c,l]) => (
                        <span key={{l}} className="flex items-center gap-1.5"><span className={{`w-2.5 h-2.5 rounded-full ${{c}}`}}></span>{{l}}</span>
                    ))}}
                </div>
                <p className="text-center text-[10px] text-gray-300 mt-4 mb-8">SCRaices v3 — Vista Unificada + Grupos — {{new Date().toLocaleString('es-CL')}}</p>
            </div>
        </div>
    );
}};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

    </script>
</body>
</html>'''


if __name__ == "__main__":
    output = generar_dashboard_v3_html()
    import subprocess
    subprocess.run(['powershell', '-Command', f"Start-Process '{output}'"], shell=True)

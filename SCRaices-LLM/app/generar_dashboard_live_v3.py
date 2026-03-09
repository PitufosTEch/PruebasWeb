"""
Genera la versión LIVE del dashboard v3 que carga datos en tiempo real
desde Google Apps Script (conectado a Google Sheets).

Proceso:
1. Lee el template index_v3.html generado por generar_dashboard_v3.py
2. Reemplaza los datos embebidos por arrays vacíos (const→let)
3. Inyecta el DataLoader que trae datos frescos al abrir

Uso: python generar_dashboard_live_v3.py [APPS_SCRIPT_URL]
"""
import sys
from pathlib import Path


# Las tablas que se necesitan del Apps Script
TABLES_NEEDED = "Proyectos,Beneficiario,Despacho,soldepacho,Ejecucion,Solpago,Maestros,Tabla_pago,Tipologias,controlBGB,controlEEPP"

# Mapeo columna real → {short code, peso} - mismos nombres que en Google Sheets
VIV_COLUMNS_JS = """{
    "A_Fund":          { "short": "Fundaciones", "weight": 0.02 },
    "A_Radier":        { "short": "Radier",  "weight": 0.04 },
    "A_Planta_Alc":    { "short": "Alcantarillado", "weight": 0.01 },
    "A_E_Tabiques":    { "short": "Tabiques", "weight": 0.06 },
    "A_E_Techumbre":   { "short": "Techumbre", "weight": 0.04 },
    "A_rev Ext":       { "short": "Rev. Exterior", "weight": 0.06 },
    "A_vent":          { "short": "Ventanas", "weight": 0.03 },
    "A_Cubierta":      { "short": "Cubierta",  "weight": 0.03 },
    "A_Ent_Cielo":     { "short": "Cielo", "weight": 0.02 },
    "A_ent_alero":     { "short": "Alero", "weight": 0.02 },
    "A_Red_AP":        { "short": "Red Agua Pot.", "weight": 0.03 },
    "A_Red_Elect":     { "short": "Red Eléctrica", "weight": 0.04 },
    "A_rev_ZS":        { "short": "Rev. Zona Seca", "weight": 0.04 },
    "A_rev_ZH":        { "short": "Rev. Zona Húmeda", "weight": 0.02 },
    "A_Aisl_Muro":     { "short": "Aisl. Muro", "weight": 0.04 },
    "A_Aisl_Cielo":    { "short": "Aisl. Cielo", "weight": 0.03 },
    "A_Cer_Piso":      { "short": "Cerámico Piso", "weight": 0.05 },
    "A_Cer_muro":      { "short": "Cerámico Muro", "weight": 0.03 },
    "A_pint_Ext":      { "short": "Pintura Ext.", "weight": 0.04 },
    "A_pint_int":      { "short": "Pintura Int.", "weight": 0.02 },
    "A_puertas":       { "short": "Puertas", "weight": 0.05 },
    "A_molduras":      { "short": "Molduras", "weight": 0.02 },
    "A_Art_Ba\\u00f1o":{ "short": "Art. Baño", "weight": 0.05 },
    "A_Art_cocina":    { "short": "Art. Cocina", "weight": 0.02 },
    "A_Art_Elec":      { "short": "Art. Eléctricos", "weight": 0.04 },
    "A_AP_Ext":        { "short": "Agua Pot. Ext.", "weight": 0.05 },
    "A_ALC_Ext":       { "short": "Alcant. Ext.", "weight": 0.05 },
    "A_Ins_Elec_Ext":  { "short": "Inst. Eléc. Ext.", "weight": 0.05 }
}"""

# Cierre columns
CIERRE_JS = """{
    "empalme": "E", "preF1": "P", "desarme": "D", "ret_escombro": "R", "aseo": "A"
}"""


def get_data_loader_js(apps_script_url):
    """Genera el código JavaScript del DataLoader"""
    return f"""
    // ============================================================
    // DATA LOADER - Carga datos en tiempo real desde Google Sheets
    // via Google Apps Script (v3)
    // ============================================================
    const APPS_SCRIPT_URL = "{apps_script_url}";
    const TABLES_TO_FETCH = "{TABLES_NEEDED}";

    // Mapeo columna real → short code + peso (28 partidas vivienda)
    const VIV_COLUMNS = {VIV_COLUMNS_JS};

    // Cierre columns
    const CIERRE_COLS = {CIERRE_JS};

    // Estado de carga
    let _loadingState = {{ total: 0, loaded: 0, current: '', error: null }};

    function showLoadingScreen() {{
        document.getElementById('root').innerHTML = `
            <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f3f4f6;font-family:'IBM Plex Sans',sans-serif;">
                <div style="text-align:center;max-width:400px;">
                    <div style="width:56px;height:56px;background:#7c3aed;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;">
                        <span style="color:white;font-size:18px;font-weight:700;font-family:'IBM Plex Mono',monospace;">SC</span>
                    </div>
                    <h2 style="color:#1f2937;font-size:18px;font-weight:600;margin-bottom:8px;">Cargando Dashboard v3</h2>
                    <p id="loadStatus" style="color:#6b7280;font-size:13px;margin-bottom:24px;">Conectando a base de datos...</p>
                    <div style="width:100%;height:4px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
                        <div id="loadBar" style="width:0%;height:100%;background:#7c3aed;border-radius:4px;transition:width 0.3s;"></div>
                    </div>
                    <p id="loadDetail" style="color:#9ca3af;font-size:11px;margin-top:12px;"></p>
                </div>
            </div>`;
    }}

    function updateLoading(msg, pct, detail) {{
        const s = document.getElementById('loadStatus');
        const b = document.getElementById('loadBar');
        const d = document.getElementById('loadDetail');
        if (s) s.textContent = msg;
        if (b) b.style.width = pct + '%';
        if (d) d.textContent = detail || '';
    }}

    function parseMonto(val) {{
        if (val === null || val === undefined || val === '' || val === 'nan') return 0;
        let s = String(val).trim().replace(/\\$/g, '').replace(/\\./g, '');
        s = s.replace(',', '.');
        const n = parseFloat(s);
        return isNaN(n) ? 0 : Math.round(n);
    }}

    function parseDate(val) {{
        if (!val || val === 'nan' || val === 'NaT' || val === '') return null;
        const s = String(val).trim();
        if (/^\\d{{4}}-\\d{{2}}-\\d{{2}}/.test(s)) return s.substring(0, 10);
        const m = s.match(/^(\\d{{1,2}})\\/(\\d{{1,2}})\\/(\\d{{4}})/);
        if (m) {{
            let p1 = parseInt(m[1]), p2 = parseInt(m[2]), year = m[3];
            if (p1 > 12) return `${{year}}-${{String(p2).padStart(2,'0')}}-${{String(p1).padStart(2,'0')}}`;
            if (p2 > 12) return `${{year}}-${{String(p1).padStart(2,'0')}}-${{String(p2).padStart(2,'0')}}`;
            return `${{year}}-${{String(p1).padStart(2,'0')}}-${{String(p2).padStart(2,'0')}}`;
        }}
        const m2 = s.match(/^(\\d{{1,2}})-(\\d{{1,2}})-(\\d{{4}})/);
        if (m2) {{
            return `${{m2[3]}}-${{String(m2[2]).padStart(2,'0')}}-${{String(m2[1]).padStart(2,'0')}}`;
        }}
        if (s.includes('T')) return s.substring(0, 10);
        return null;
    }}

    async function fetchBatch(tables, label) {{
        const url = APPS_SCRIPT_URL + '?tables=' + encodeURIComponent(tables);
        console.log('[LIVE] Fetching:', label, tables);
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Error ${{response.status}} al cargar ${{label}}`);
        const data = await response.json();
        if (data.error) throw new Error('Error Apps Script (' + label + '): ' + data.error);
        console.log('[LIVE] OK:', label);
        return data;
    }}

    async function fetchAllData() {{
        updateLoading('Descargando datos...', 5, 'Conectando a Google Sheets (3 lotes en paralelo)');

        // Dividir en 3 lotes paralelos para evitar timeout
        const batch1 = fetchBatch('Proyectos,Beneficiario,Tipologias,Maestros,controlBGB,controlEEPP', 'Lote 1: Proyectos+Benef');
        const batch2 = fetchBatch('Despacho,soldepacho,Tabla_pago', 'Lote 2: Despachos+Sol');
        const batch3 = fetchBatch('Ejecucion,Solpago', 'Lote 3: Insp+Pagos');

        let r1, r2, r3;
        try {{
            updateLoading('Descargando lotes en paralelo...', 10, 'Lote 1: Proyectos | Lote 2: Despachos | Lote 3: Inspecciones+Pagos');
            [r1, r2, r3] = await Promise.all([batch1, batch2, batch3]);
        }} catch (e) {{
            throw new Error('Error al descargar datos: ' + e.message);
        }}

        updateLoading('Combinando datos...', 30, 'Todos los lotes recibidos');
        return {{ ...r1, ...r2, ...r3 }};
    }}

    function processRawData(raw) {{
        updateLoading('Procesando proyectos...', 40);

        // 1. PROYECTOS (ejecucion + finalizados)
        const proyectosRaw = raw.Proyectos?.rows || [];
        PROYECTOS_DATA = proyectosRaw
            .filter(p => {{
                const est = (p.estado_general || '').toLowerCase();
                return est.includes('ejecuci') || est.includes('finalizado');
            }})
            .map(p => {{
                const est = (p.estado_general || '').toLowerCase();
                return {{
                    ID_proy: String(p.ID_proy || ''),
                    NOMBRE_PROYECTO: String(p.NOMBRE_PROYECTO || ''),
                    COMUNA: String(p.COMUNA || ''),
                    fecha_inicio: parseDate(p.fecha_inicio) || '',
                    duracion: parseInt(p.duracion) || 0,
                    estado: est.includes('finalizado') ? 'finalizado' : 'ejecucion'
                }};
            }})
            .sort((a, b) => {{
                if (a.estado !== b.estado) return a.estado === 'ejecucion' ? -1 : 1;
                return (b.fecha_inicio || '').localeCompare(a.fecha_inicio || '');
            }});

        const idsProyActivos = new Set(PROYECTOS_DATA.map(p => p.ID_proy));

        updateLoading('Procesando beneficiarios...', 45);

        // 2. BENEFICIARIOS
        const benRaw = raw.Beneficiario?.rows || [];
        const estadosValidos = ['ejecuci', 'subsidiad', 'preparaci', 'terminad'];

        // Tipologias dict
        const tipRaw = raw.Tipologias?.rows || [];
        const tipDict = {{}};
        tipRaw.forEach(t => {{
            const id = String(t.IDU_tipol || '').trim();
            if (id && id !== 'nan') {{
                const fam = String(t.Familia || '').trim();
                const dorm = String(t.dormitorios || '').trim();
                const plantas = String(t.plantas || '').trim();
                const caract = String(t.caracterizacion || '').trim();
                let label = 'Vivienda';
                if (dorm && dorm !== 'nan') label += ` ${{dorm}}D`;
                if (plantas && plantas !== 'nan') label += ` ${{plantas}}P`;
                if (caract && caract !== 'nan') label += ` ${{caract}}`;
                tipDict[id] = label;
            }}
        }});

        BENEFICIARIOS_DATA = benRaw
            .filter(b => {{
                const proy = String(b.ID_Proy || '');
                const estado = (b.Estado || '').toLowerCase();
                return idsProyActivos.has(proy) && estadosValidos.some(e => estado.includes(e));
            }})
            .map(b => {{
                const tipViv = String(b['Tipologia Vivienda'] || '');
                const tipRC = String(b['Tipologia RC'] || '');
                const tipVivId = (tipViv && tipViv.toLowerCase() !== 'nan' && tipViv !== '') ? tipViv : '';
                const tipRCId = (tipRC && tipRC.toLowerCase() !== 'nan' && tipRC !== '') ? tipRC : '';
                const habilRaw = String(b['Habil para construir'] || '').toLowerCase();
                const habil = habilRaw === 'si' || habilRaw === 'sí' || habilRaw === 'true' || habilRaw === '1';

                // Tipologia descriptiva
                let tipLabel = tipRCId ? 'Casa + RC' : 'Casa';
                const mainTipId = tipRCId || tipVivId;
                if (mainTipId && tipDict[mainTipId]) {{
                    tipLabel = tipDict[mainTipId];
                    // Agregar nombre proyecto
                    const proy = PROYECTOS_DATA.find(p => String(p.ID_proy) === String(b.ID_Proy));
                    if (proy) tipLabel += ` ${{proy.NOMBRE_PROYECTO}}`;
                }}

                return {{
                    ID_Benef: String(b.ID_Benef || b.IDU_Benef || ''),
                    ID_Proy: String(b.ID_Proy || ''),
                    NOMBRES: String(b.NOMBRES || ''),
                    APELLIDOS: String(b.APELLIDOS || ''),
                    tipologia: tipLabel,
                    tipologia_viv_id: tipVivId,
                    tipologia_rc_id: tipRCId,
                    habil: habil
                }};
            }});

        const idsBenef = new Set(BENEFICIARIOS_DATA.map(b => String(b.ID_Benef)));

        updateLoading('Procesando despachos...', 50);

        // 3. DESPACHOS
        const despRaw = raw.Despacho?.rows || [];
        DESPACHOS_DATA = despRaw
            .filter(d => idsBenef.has(String(d.ID_Benef || '')))
            .map(d => {{
                const fecha = parseDate(d.Fecha);
                return fecha ? {{
                    ID_Benef: String(d.ID_Benef || ''),
                    Tipo_despacho: String(d.Tipo_despacho || ''),
                    Fecha: fecha,
                    Guia: String(d.Guia || '')
                }} : null;
            }}).filter(Boolean);

        updateLoading('Procesando solicitudes...', 55);

        // 4. SOLICITUDES
        const solRaw = raw.soldepacho?.rows || [];
        SOLICITUDES_DATA = solRaw
            .filter(s => idsBenef.has(String(s.ID_Benef || '')))
            .map(s => ({{
                ID_Benef: String(s.ID_Benef || ''),
                Tipo_despacho: String(s.Tipo_despacho || ''),
                Fecha: parseDate(s.Fecha) || '',
                fecha_creacion: parseDate(s.fecha_creacion) || ''
            }}));

        updateLoading('Procesando inspecciones...', 60);

        // 5. INSPECCIONES (Ejecucion - sumar deltas)
        function parseInspVal(val) {{
            if (val === null || val === undefined || val === '' || val === 'nan') return 0;
            if (typeof val === 'number') return val <= 1.5 ? val : val / 100;
            let s = String(val).trim().replace('%', '').replace(',', '.');
            let n = parseFloat(s);
            if (isNaN(n)) return 0;
            return n > 1.5 ? n / 100 : n;
        }}

        const ejRaw = raw.Ejecucion?.rows || [];
        const inspMap = {{}};
        const hasBarno = ejRaw.length > 0 && 'A_Art_Bano' in ejRaw[0] && !('A_Art_Ba\u00f1o' in ejRaw[0]);
        const sampleRow = ejRaw.length > 0 ? ejRaw[0] : {{}};
        const rcCols = Object.keys(sampleRow).filter(k => k.startsWith('AB_'));
        const hasHab = 'A_Habilitacion' in sampleRow;

        ejRaw.forEach(e => {{
            const idB = String(e.ID_Benef || e.ID_benef || '');
            if (!idsBenef.has(idB)) return;
            if (!inspMap[idB]) inspMap[idB] = {{
                ID_Benef: idB, partidas: {{}}, rc_vals: {{}},
                hab_sum: 0, n_insp: 0, ultima_insp: '', cierre: {{}}
            }};
            inspMap[idB].n_insp++;

            Object.entries(VIV_COLUMNS).forEach(([col, info]) => {{
                let actualCol = col;
                if (col === 'A_Art_Ba\u00f1o' && hasBarno) actualCol = 'A_Art_Bano';
                const val = parseInspVal(e[actualCol]);
                if (val > 0) {{
                    inspMap[idB].partidas[info.short] = Math.min(1, (inspMap[idB].partidas[info.short] || 0) + val);
                }}
            }});

            rcCols.forEach(col => {{
                const val = parseInspVal(e[col]);
                if (val > 0) {{
                    inspMap[idB].rc_vals[col] = Math.min(1, (inspMap[idB].rc_vals[col] || 0) + val);
                }}
            }});

            if (hasHab) {{
                const val = parseInspVal(e['A_Habilitacion']);
                if (val > 0) inspMap[idB].hab_sum = Math.min(1, inspMap[idB].hab_sum + val);
            }}

            const fInsp = parseDate(e.Fecha_creacion || e.fecha_creacion || '');
            if (fInsp && fInsp > inspMap[idB].ultima_insp) inspMap[idB].ultima_insp = fInsp;

            Object.entries(CIERRE_COLS).forEach(([col, label]) => {{
                const val = String(e[col] || '').trim().toLowerCase();
                if (val && val !== 'nan') inspMap[idB].cierre[label] = val === 'terminado' ? 1 : 0;
            }});
        }});

        INSPECCIONES_DATA = Object.values(inspMap).map(insp => {{
            let pct_viv = 0;
            Object.entries(VIV_COLUMNS).forEach(([col, info]) => {{
                pct_viv += Math.min(1, Math.max(0, insp.partidas[info.short] || 0)) * info.weight;
            }});
            const rcValues = Object.values(insp.rc_vals);
            const pct_rc = rcValues.length > 0
                ? rcValues.reduce((s, v) => s + Math.min(1, Math.max(0, v)), 0) / rcValues.length : 0;
            const pct_hab = Math.min(1, Math.max(0, insp.hab_sum));
            const pct_total = pct_viv * 0.7 + pct_rc * 0.25 + pct_hab * 0.05;

            const partidas100 = {{}};
            Object.entries(insp.partidas).forEach(([k, v]) => {{
                partidas100[k] = Math.round(Math.min(1, Math.max(0, v)) * 100);
            }});

            return {{
                ID_Benef: insp.ID_Benef,
                pct_viv: Math.round(pct_viv * 1000) / 10,
                pct_rc: Math.round(pct_rc * 1000) / 10,
                pct_hab: Math.round(pct_hab * 1000) / 10,
                pct_total: Math.round(pct_total * 1000) / 10,
                ultima_insp: insp.ultima_insp,
                n_insp: insp.n_insp,
                partidas: partidas100,
                cierre: insp.cierre
            }};
        }});

        updateLoading('Procesando pagos...', 70);

        // 6. SOLPAGO
        const spRaw = raw.Solpago?.rows || [];
        SOLPAGO_DATA = spRaw
            .filter(s => {{
                const estado = String(s.Estado || '').toLowerCase();
                return estado.includes('aprobad') && idsBenef.has(String(s.ID_Benef || ''));
            }})
            .map(s => ({{
                ID_Benef: String(s.ID_Benef || ''),
                Familia_pago: String(s.Familia_pago || ''),
                Tipo_pago: String(s.Tipo_pago || ''),
                monto: parseMonto(s.monto),
                fecha: parseDate(s.fecha || s.Fecha) || '',
                maestro: String(s.maestro || s.IDU_maestros || ''),
                Estado: 'Aprobado'
            }}));

        updateLoading('Procesando maestros...', 80);

        // 7. MAESTROS → MAESTROS_DATA (dict en v3)
        const mRaw = raw.Maestros?.rows || [];
        MAESTROS_DATA = {{}};
        mRaw.forEach(m => {{
            const id = String(m.IDU_maestros || m.ID || '');
            const nombre = String(m.Nombres || m.Nombre || m.NOMBRES || m.NOMBRE || '');
            const apellido = String(m.Apellidos || m.Apellido || m.APELLIDOS || m.APELLIDO || '');
            if (id && id !== 'nan') {{
                MAESTROS_DATA[id] = (nombre + ' ' + apellido).trim() || id;
            }}
        }});

        updateLoading('Procesando presupuesto...', 85);

        // 8. PRESUPUESTO (Tabla_pago por tipologia)
        const tpRaw = raw.Tabla_pago?.rows || [];
        PRESUPUESTO_DATA = {{}};
        tpRaw.forEach(tp => {{
            const tipol = String(tp.IDU_Tipol || '').trim();
            const familia = String(tp.familia_pago || '').trim();
            let monto = 0;
            try {{ monto = parseFloat(tp.monto) || 0; }} catch(e) {{ monto = parseMonto(tp.monto); }}
            if (tipol && tipol !== 'nan' && familia && familia !== 'nan') {{
                if (!PRESUPUESTO_DATA[tipol]) PRESUPUESTO_DATA[tipol] = {{}};
                PRESUPUESTO_DATA[tipol][familia] = (PRESUPUESTO_DATA[tipol][familia] || 0) + monto;
            }}
        }});

        updateLoading('Procesando garantías...', 92);

        // 9. GARANTIAS (controlBGB)
        const bgbRaw = raw.controlBGB?.rows || [];
        GARANTIAS_DATA = bgbRaw
            .filter(g => idsProyActivos.has(String(g.ID_Proy || '')))
            .map(g => ({{
                ID_Proy: String(g.ID_Proy || ''),
                tipo: String(g.Tipo || ''),
                tipo1: String(g.Tipo1 || ''),
                num_bol: String(g.num_bol || ''),
                banco: String(g.Banco || ''),
                monto_uf: parseInt(g.Monto) || 0,
                fecha_inicio: parseDate(g.Fecha_inic) || '',
                fecha_vcmto: parseDate(g.Fecha_vcmto) || ''
            }}));

        updateLoading('Procesando estados de pago...', 95);

        // 10. ESTADOS DE PAGO (controlEEPP)
        const parseMontoUF = (raw) => {{
            const s = String(raw || '0').trim();
            if (!s || s === 'nan' || s === 'None') return 0;
            if (s.includes(',') && s.includes('.')) {{
                return Math.round(parseFloat(s.replace(/\\./g, '').replace(',', '.')) * 100) / 100;
            }} else if (s.includes(',')) {{
                return Math.round(parseFloat(s.replace(',', '.')) * 100) / 100;
            }} else {{
                return Math.round((parseFloat(s) || 0) * 100) / 100;
            }}
        }};
        const eeppRaw = raw.controlEEPP?.rows || [];
        EEPP_DATA = eeppRaw
            .filter(ep => idsProyActivos.has(String(ep.ID_Proy || '')))
            .map(ep => ({{
                ID_Proy: String(ep.ID_Proy || ''),
                ID_Benef: String(ep.ID_Benef || ''),
                Num_EP: String(ep.Num_EP || ''),
                Monto: parseMontoUF(ep.Monto),
                Estado: String(ep.Estado || ''),
                Fecha: parseDate(ep.Fecha) || ''
            }}));

        updateLoading('Listo!', 100, `${{PROYECTOS_DATA.length}} proyectos, ${{BENEFICIARIOS_DATA.length}} beneficiarios, ${{DESPACHOS_DATA.length}} despachos, ${{SOLPAGO_DATA.length}} pagos`);
    }}

    async function initLiveData() {{
        showLoadingScreen();
        try {{
            const raw = await fetchAllData();
            processRawData(raw);
            await new Promise(r => setTimeout(r, 500));
            renderApp();
        }} catch (err) {{
            document.getElementById('root').innerHTML = `
                <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f3f4f6;font-family:'IBM Plex Sans',sans-serif;">
                    <div style="text-align:center;max-width:450px;padding:40px;">
                        <div style="color:#ef4444;font-size:48px;margin-bottom:16px;">&#9888;</div>
                        <h2 style="color:#1f2937;font-size:18px;font-weight:600;margin-bottom:8px;">Error al cargar datos</h2>
                        <p style="color:#6b7280;font-size:13px;margin-bottom:16px;">${{err.message}}</p>
                        <button onclick="location.reload()" style="padding:10px 24px;background:#7c3aed;color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;">Reintentar</button>
                        <p style="color:#9ca3af;font-size:11px;margin-top:20px;">Si el problema persiste, verifica que el Apps Script este desplegado correctamente.</p>
                    </div>
                </div>`;
        }}
    }}
"""


def make_live_dashboard(apps_script_url):
    """Lee el v3 HTML estático y lo convierte en versión live"""

    v3_path = Path(__file__).parent.parent / 'dashboard' / 'index_v3.html'
    if not v3_path.exists():
        print("ERROR: Primero genera index_v3.html con generar_dashboard_v3.py")
        sys.exit(1)

    print(f"Leyendo template: {v3_path}")
    with open(v3_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Reemplazar datos embebidos por variables mutables vacías
    data_vars = [
        ('PROYECTOS_DATA', '[]'),
        ('BENEFICIARIOS_DATA', '[]'),
        ('DESPACHOS_DATA', '[]'),
        ('SOLICITUDES_DATA', '[]'),
        ('INSPECCIONES_DATA', '[]'),
        ('SOLPAGO_DATA', '[]'),
        ('MAESTROS_DATA', '{}'),
        ('PRESUPUESTO_DATA', '{}'),
        ('GARANTIAS_DATA', '[]'),
        ('EEPP_DATA', '[]'),
    ]

    for var_name, empty_val in data_vars:
        marker = f'const {var_name} = '
        idx = html.find(marker)
        if idx == -1:
            print(f"  WARN: No se encontró {var_name}")
            continue

        start_data = idx + len(marker)
        bracket = html[start_data]

        if bracket in '[{':
            close = ']' if bracket == '[' else '}'
            depth = 0
            end = start_data
            for i in range(start_data, len(html)):
                if html[i] == bracket:
                    depth += 1
                elif html[i] == close:
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end < len(html) and html[end] == ';':
                end += 1

            old_text = html[idx:end]
            new_text = f'let {var_name} = {empty_val};'
            html = html[:idx] + new_text + html[end:]
            size_saved = len(old_text) - len(new_text)
            print(f"  {var_name}: reemplazado ({size_saved:,} chars removidos)")
        else:
            print(f"  WARN: {var_name} formato inesperado")

    # 2. Inyectar DataLoader antes de ETAPAS CONFIG
    loader_js = get_data_loader_js(apps_script_url)

    insert_marker = '// ========== ETAPAS CONFIG =========='
    idx = html.find(insert_marker)
    if idx != -1:
        html = html[:idx] + loader_js + '\n\n' + html[idx:]
        print("  DataLoader inyectado")
    else:
        print("  WARN: No se encontró marcador para inyectar DataLoader")

    # 3. Reemplazar el render de React para que espere datos
    render_patterns = [
        "ReactDOM.createRoot(document.getElementById('root')).render(<App />);",
    ]

    new_render = """// Función de render (llamada después de cargar datos)
        function renderApp() {
            try {
                console.log('[v3 LIVE] renderApp() - PROYECTOS:', PROYECTOS_DATA.length, 'BENEF:', BENEFICIARIOS_DATA.length, 'DESP:', DESPACHOS_DATA.length, 'SOLPAGO:', SOLPAGO_DATA.length);
                ReactDOM.createRoot(document.getElementById('root')).render(<App />);
                console.log('[v3 LIVE] render() OK');
            } catch(e) {
                console.error('[v3 LIVE] Error en renderApp:', e);
                document.getElementById('root').innerHTML = '<div style="padding:40px;font-family:monospace;"><h2 style="color:red;">Error al renderizar</h2><pre style="background:#f5f5f5;padding:20px;border-radius:8px;overflow:auto;white-space:pre-wrap;">' + e.message + '\\n' + e.stack + '</pre><button onclick="location.reload()" style="margin-top:16px;padding:8px 16px;background:#7c3aed;color:white;border:none;border-radius:6px;cursor:pointer;">Reintentar</button></div>';
            }
        }

        // En modo LIVE: cargar datos primero, luego renderizar
        if (typeof APPS_SCRIPT_URL !== 'undefined' && APPS_SCRIPT_URL) {
            initLiveData();
        } else {
            renderApp();
        }"""

    render_replaced = False
    for pattern in render_patterns:
        if pattern in html:
            html = html.replace(pattern, new_render)
            print("  Render React reemplazado por versión async")
            render_replaced = True
            break

    if not render_replaced:
        print("  WARN: No se encontró bloque de render React")

    # 4. Actualizar título
    html = html.replace(
        '<title>Panel de Control v3 - SG Raices</title>',
        '<title>Panel de Control v3 - SG Raices (Live)</title>'
    )

    # 4b. Inyectar protección por contraseña
    # SHA-256 de "SCRAICES.2026"
    PASSWORD_HASH = "a0f3b1c45e6d8f9a2b4c7e0d1f3a5b8c9e2d4f6a8b0c3e5d7f9a1b4c6e8d0f2"
    login_screen = '''
<div id="loginOverlay" style="position:fixed;inset:0;z-index:9999;background:#f3f4f6;display:flex;align-items:center;justify-content:center;font-family:'IBM Plex Sans',sans-serif;">
    <div style="text-align:center;max-width:380px;width:90%;">
        <div style="width:56px;height:56px;background:#7c3aed;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;">
            <span style="color:white;font-size:18px;font-weight:700;font-family:'IBM Plex Mono',monospace;">SC</span>
        </div>
        <h2 style="color:#1f2937;font-size:20px;font-weight:600;margin-bottom:4px;">Panel de Control v3</h2>
        <p style="color:#9ca3af;font-size:13px;margin-bottom:24px;">SG Raices - Acceso protegido</p>
        <div style="display:flex;gap:8px;">
            <input type="password" id="pwdInput" placeholder="Contrasena" autocomplete="off" autofocus
                style="flex:1;padding:10px 16px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;outline:none;font-family:'IBM Plex Sans',sans-serif;"
                onkeydown="if(event.key==='Enter')checkPwd()" />
            <button onclick="checkPwd()"
                style="padding:10px 20px;background:#7c3aed;color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;">Entrar</button>
        </div>
        <p id="pwdError" style="color:#ef4444;font-size:12px;margin-top:10px;display:none;">Contrasena incorrecta</p>
    </div>
</div>
<script>
async function hashPwd(pwd) {
    const enc = new TextEncoder().encode(pwd);
    const buf = await crypto.subtle.digest('SHA-256', enc);
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}
async function checkPwd() {
    const input = document.getElementById('pwdInput').value;
    const hash = await hashPwd(input);
    if (hash === sessionStorage.getItem('_sc_hash') || input === '') { return; }
    // Hash correcto de SCRAICES.2026
    if (hash === '__PWD_HASH__') {
        sessionStorage.setItem('_sc_auth', '1');
        document.getElementById('loginOverlay').style.display = 'none';
    } else {
        document.getElementById('pwdError').style.display = 'block';
        document.getElementById('pwdInput').value = '';
        document.getElementById('pwdInput').focus();
    }
}
// Auto-check si ya autenticado en esta sesion
if (sessionStorage.getItem('_sc_auth') === '1') {
    document.getElementById('loginOverlay').style.display = 'none';
}
</script>
'''
    # Calcular hash real
    import hashlib
    real_hash = hashlib.sha256("SCRAICES.2026".encode()).hexdigest()
    login_screen = login_screen.replace('__PWD_HASH__', real_hash)

    # Inyectar después de <body...>
    body_tag = '<body class="bg-gray-50 text-gray-800 min-h-screen">'
    if body_tag in html:
        html = html.replace(body_tag, body_tag + '\n' + login_screen)
        print("  Pantalla de login inyectada")

    # 5. Agregar indicador LIVE en top bar
    html = html.replace(
        'SCRaices v3</span>',
        'SCRaices v3 <span className="ml-1.5 bg-green-500 text-white text-[9px] px-1.5 py-0.5 rounded align-middle">LIVE</span></span>',
        1
    )

    # Guardar
    output_path = Path(__file__).parent.parent / 'dashboard' / 'index_live_v3.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nDashboard LIVE v3 generado: {output_path}")
    print(f"  Tamaño: {size_kb:.0f} KB")
    print(f"  Apps Script URL: {apps_script_url}")
    print(f"\nPara usar:")
    print(f"  1. Despliega el Apps Script (ver apps_script/Code.gs)")
    print(f"  2. Abre {output_path} en el navegador")
    print(f"  3. Los datos se cargan en tiempo real al abrir")

    return str(output_path)


def main():
    DEFAULT_URL = "https://script.google.com/macros/s/AKfycbxcJowX3a3XBmSNiKOCesj1jRkQWS1VIsMbvdt-x7ckK8ZXMauI6gRgCGsoT77xYxpP/exec"
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    print("=" * 60)
    print("DASHBOARD LIVE v3 - Generador")
    print("=" * 60)

    # Verificar que v3 existe
    v3_path = Path(__file__).parent.parent / 'dashboard' / 'index_v3.html'
    if not v3_path.exists():
        print("index_v3.html no existe. Generando primero...")
        import generar_dashboard_v3
        generar_dashboard_v3.generar_dashboard_v3_html()

    make_live_dashboard(url)


if __name__ == '__main__':
    main()

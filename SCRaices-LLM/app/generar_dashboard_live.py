"""
Genera la versión LIVE del dashboard que carga datos en tiempo real
desde Google Apps Script (conectado a Google Sheets).

Proceso:
1. Primero ejecuta generar_dashboard_v2.py para obtener el template con UI
2. Reemplaza los datos embebidos por arrays vacíos
3. Inyecta el DataLoader que trae datos frescos al abrir

Uso: python generar_dashboard_live.py [APPS_SCRIPT_URL]
"""
import sys
import re
from pathlib import Path


# Las tablas que se necesitan del Apps Script
TABLES_NEEDED = "Proyectos,Beneficiario,Despacho,soldepacho,Ejecucion,Solpago,Maestros,Tabla_pago,Tipologias,controlBGB,controlEEPP"

# Mapeo columna real → {short code, peso} - mismos nombres que en Google Sheets
# Los pesos son los de PESOS_VIV en generar_dashboard_v2.py (suman ~1.0)
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
    // via Google Apps Script
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
                    <div style="width:56px;height:56px;background:#8B2332;border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;">
                        <span style="color:white;font-size:18px;font-weight:700;font-family:'IBM Plex Mono',monospace;">SG</span>
                    </div>
                    <h2 style="color:#1f2937;font-size:18px;font-weight:600;margin-bottom:8px;">Cargando Dashboard</h2>
                    <p id="loadStatus" style="color:#6b7280;font-size:13px;margin-bottom:24px;">Conectando a base de datos...</p>
                    <div style="width:100%;height:4px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
                        <div id="loadBar" style="width:0%;height:100%;background:#8B2332;border-radius:4px;transition:width 0.3s;"></div>
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

    // Parsear monto chileno "$400.000,00" → 400000
    function parseMonto(val) {{
        if (val === null || val === undefined || val === '' || val === 'nan') return 0;
        let s = String(val).trim().replace(/\\$/g, '').replace(/\\./g, '');
        s = s.replace(',', '.');
        const n = parseFloat(s);
        return isNaN(n) ? 0 : Math.round(n);
    }}

    // Parsear fecha: soporta M/D/YYYY, D/M/YYYY, DD-MM-YYYY, ISO
    function parseDate(val) {{
        if (!val || val === 'nan' || val === 'NaT' || val === '') return null;
        const s = String(val).trim();
        // Si ya es ISO (YYYY-MM-DD o con T)
        if (/^\\d{{4}}-\\d{{2}}-\\d{{2}}/.test(s)) return s.substring(0, 10);
        // Formato con slashes: M/D/YYYY o D/M/YYYY
        const m = s.match(/^(\\d{{1,2}})\\/(\\d{{1,2}})\\/(\\d{{4}})/);
        if (m) {{
            let p1 = parseInt(m[1]), p2 = parseInt(m[2]), year = m[3];
            // Si p1 > 12, es dia (DD/MM/YYYY)
            if (p1 > 12) return `${{year}}-${{String(p2).padStart(2,'0')}}-${{String(p1).padStart(2,'0')}}`;
            // Si p2 > 12, p1 es mes (MM/DD/YYYY)
            if (p2 > 12) return `${{year}}-${{String(p1).padStart(2,'0')}}-${{String(p2).padStart(2,'0')}}`;
            // Ambiguo (ambos <=12): asumir M/D/YYYY (default Google Sheets)
            return `${{year}}-${{String(p1).padStart(2,'0')}}-${{String(p2).padStart(2,'0')}}`;
        }}
        // Formato DD-MM-YYYY con guiones
        const m2 = s.match(/^(\\d{{1,2}})-(\\d{{1,2}})-(\\d{{4}})/);
        if (m2) {{
            return `${{m2[3]}}-${{String(m2[2]).padStart(2,'0')}}-${{String(m2[1]).padStart(2,'0')}}`;
        }}
        // ISO datetime from Apps Script
        if (s.includes('T')) return s.substring(0, 10);
        return null;
    }}

    async function fetchAllData() {{
        updateLoading('Descargando datos...', 10, 'Conectando a Google Sheets');

        const url = APPS_SCRIPT_URL + '?tables=' + encodeURIComponent(TABLES_TO_FETCH);
        let response;
        try {{
            response = await fetch(url);
        }} catch (e) {{
            throw new Error('No se pudo conectar al servidor de datos. Verifica tu conexion a internet.');
        }}

        if (!response.ok) {{
            throw new Error(`Error del servidor: ${{response.status}}`);
        }}

        updateLoading('Procesando respuesta...', 30, 'Datos recibidos, procesando...');
        const data = await response.json();

        if (data.error) {{
            throw new Error('Error en Apps Script: ' + data.error);
        }}

        return data;
    }}

    function processRawData(raw) {{
        updateLoading('Procesando proyectos...', 40);

        // 1. PROYECTOS - filtrar activos (en ejecucion)
        const proyectosRaw = raw.Proyectos?.rows || [];
        PROYECTOS_DATA = proyectosRaw
            .filter(p => (p.estado_general || '').toLowerCase().includes('ejecuci'))
            .map(p => {{
                const fi = parseDate(p.fecha_inicio);
                let dur = parseInt(p.duracion) || 0;
                return {{
                ID_proy: String(p.ID_proy || ''),
                NOMBRE_PROYECTO: String(p.NOMBRE_PROYECTO || ''),
                COMUNA: String(p.COMUNA || ''),
                fecha_inicio: fi || '',
                duracion: dur
            }};
            }});

        const idsProyActivos = new Set(PROYECTOS_DATA.map(p => p.ID_proy));

        updateLoading('Procesando beneficiarios...', 45);

        // 2. BENEFICIARIOS - filtrar por proyecto activo + estado valido
        const benRaw = raw.Beneficiario?.rows || [];
        const estadosValidos = ['ejecuci', 'subsidiad', 'preparaci'];
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
                return {{
                    ID_Benef: String(b.ID_Benef || b.IDU_Benef || ''),
                    ID_Proy: String(b.ID_Proy || ''),
                    NOMBRES: String(b.NOMBRES || ''),
                    APELLIDOS: String(b.APELLIDOS || ''),
                    tipologia: tipRCId ? 'Casa + RC' : 'Casa',
                    tipologia_viv_id: tipVivId,
                    tipologia_rc_id: tipRCId
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
            .map(s => {{
                const fecha = parseDate(s.Fecha);
                const fechaCreacion = parseDate(s.fecha_creacion);
                return {{
                    ID_Benef: String(s.ID_Benef || ''),
                    Tipo_despacho: String(s.Tipo_despacho || ''),
                    Fecha: fecha || '',
                    fecha_creacion: fechaCreacion || ''
                }};
            }});

        updateLoading('Procesando inspecciones...', 60);

        // 5. INSPECCIONES (de Ejecucion - sumar deltas)
        // Los valores vienen como fracciones 0-1 (si porcentaje en sheet) o como numeros
        function parseInspVal(val) {{
            if (val === null || val === undefined || val === '' || val === 'nan') return 0;
            if (typeof val === 'number') {{
                // Google Sheets porcentaje: 0.5 = 50%. Numeros > 1.5 podrían ser porcentajes directos
                return val <= 1.5 ? val : val / 100;
            }}
            // String: quitar % y comas
            let s = String(val).trim().replace('%', '').replace(',', '.');
            let n = parseFloat(s);
            if (isNaN(n)) return 0;
            // Si > 1.5, asumir que es porcentaje directo (ej: 50 = 50%)
            return n > 1.5 ? n / 100 : n;
        }}

        const ejRaw = raw.Ejecucion?.rows || [];
        const inspMap = {{}};

        // Detectar variante de columna Art_Baño vs Art_Bano
        const hasBarno = ejRaw.length > 0 && 'A_Art_Bano' in ejRaw[0] && !('A_Art_Ba\u00f1o' in ejRaw[0]);

        // Descubrir columnas RC (AB_*) y Habilitacion
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

            // Partidas vivienda (28 columnas → short codes)
            Object.entries(VIV_COLUMNS).forEach(([col, info]) => {{
                // Manejar variante Baño/Bano
                let actualCol = col;
                if (col === 'A_Art_Ba\u00f1o' && hasBarno) actualCol = 'A_Art_Bano';
                const val = parseInspVal(e[actualCol]);
                if (val > 0) {{
                    inspMap[idB].partidas[info.short] = Math.min(1, (inspMap[idB].partidas[info.short] || 0) + val);
                }}
            }});

            // RC (AB_* columns - promedio simple)
            rcCols.forEach(col => {{
                const val = parseInspVal(e[col]);
                if (val > 0) {{
                    inspMap[idB].rc_vals[col] = Math.min(1, (inspMap[idB].rc_vals[col] || 0) + val);
                }}
            }});

            // Habilitacion
            if (hasHab) {{
                const val = parseInspVal(e['A_Habilitacion']);
                if (val > 0) {{
                    inspMap[idB].hab_sum = Math.min(1, inspMap[idB].hab_sum + val);
                }}
            }}

            // Fecha de inspeccion (tomar la mas reciente)
            const fInsp = parseDate(e.Fecha_creacion || e.fecha_creacion || '');
            if (fInsp && fInsp > inspMap[idB].ultima_insp) {{
                inspMap[idB].ultima_insp = fInsp;
            }}

            // Cierre (tomar ultimo valor no vacio - overwrites, last wins)
            Object.entries(CIERRE_COLS).forEach(([col, label]) => {{
                const val = String(e[col] || '').trim().toLowerCase();
                if (val && val !== 'nan') {{
                    inspMap[idB].cierre[label] = val === 'terminado' ? 1 : 0;
                }}
            }});
        }});

        // Calcular % ponderados
        INSPECCIONES_DATA = Object.values(inspMap).map(insp => {{
            // % Vivienda (ponderado por pesos)
            let pct_viv = 0;
            Object.entries(VIV_COLUMNS).forEach(([col, info]) => {{
                pct_viv += Math.min(1, Math.max(0, insp.partidas[info.short] || 0)) * info.weight;
            }});

            // % RC (promedio simple de columnas AB_*)
            const rcValues = Object.values(insp.rc_vals);
            const pct_rc = rcValues.length > 0
                ? rcValues.reduce((s, v) => s + Math.min(1, Math.max(0, v)), 0) / rcValues.length
                : 0;

            // % Habilitacion
            const pct_hab = Math.min(1, Math.max(0, insp.hab_sum));

            // % Total = 70% Viv + 25% RC + 5% Hab
            const pct_total = pct_viv * 0.7 + pct_rc * 0.25 + pct_hab * 0.05;

            // Convertir partidas a 0-100 para el UI
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

        // 6. SOLPAGO - solo Aprobados
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

        // 7. MAESTROS
        const mRaw = raw.Maestros?.rows || [];
        MAESTROS_DICT = {{}};
        mRaw.forEach(m => {{
            const id = String(m.IDU_maestros || m.ID || '');
            const nombre = String(m.Nombres || m.Nombre || m.NOMBRES || m.NOMBRE || '');
            const apellido = String(m.Apellidos || m.Apellido || m.APELLIDOS || m.APELLIDO || '');
            if (id && id !== 'nan') {{
                MAESTROS_DICT[id] = (nombre + ' ' + apellido).trim() || id;
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

        // 9. REPORTES - no disponibles en modo live (requieren generacion Python)
        REPORTES_DATA = [];

        updateLoading('Procesando garantias...', 92);

        // 10. GARANTIAS (controlBGB)
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

        // 11. ESTADOS DE PAGO (controlEEPP)
        const parseMontoUF = (raw) => {{
            const s = String(raw || '0').trim();
            if (!s || s === 'nan' || s === 'None') return 0;
            if (s.includes(',') && s.includes('.')) {{
                // 1.234,56 -> punto miles, coma decimal
                return Math.round(parseFloat(s.replace(/\\./g, '').replace(',', '.')) * 100) / 100;
            }} else if (s.includes(',')) {{
                // 154,47 -> coma decimal
                return Math.round(parseFloat(s.replace(',', '.')) * 100) / 100;
            }} else {{
                // 1292.64 -> punto decimal
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
            // Pequena pausa para que el usuario vea el "Listo!"
            await new Promise(r => setTimeout(r, 500));
            // Renderizar React
            renderApp();
        }} catch (err) {{
            document.getElementById('root').innerHTML = `
                <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f3f4f6;font-family:'IBM Plex Sans',sans-serif;">
                    <div style="text-align:center;max-width:450px;padding:40px;">
                        <div style="color:#ef4444;font-size:48px;margin-bottom:16px;">&#9888;</div>
                        <h2 style="color:#1f2937;font-size:18px;font-weight:600;margin-bottom:8px;">Error al cargar datos</h2>
                        <p style="color:#6b7280;font-size:13px;margin-bottom:16px;">${{err.message}}</p>
                        <button onclick="location.reload()" style="padding:10px 24px;background:#8B2332;color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;">Reintentar</button>
                        <p style="color:#9ca3af;font-size:11px;margin-top:20px;">Si el problema persiste, verifica que el Apps Script este desplegado correctamente.</p>
                    </div>
                </div>`;
        }}
    }}
"""


def make_live_dashboard(apps_script_url):
    """Lee el v2 HTML estático y lo convierte en versión live"""

    v2_path = Path(__file__).parent.parent / 'dashboard' / 'index_v2.html'
    if not v2_path.exists():
        print("ERROR: Primero genera index_v2.html con generar_dashboard_v2.py")
        sys.exit(1)

    print(f"Leyendo template: {v2_path}")
    with open(v2_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Reemplazar datos embebidos por variables mutables vacías
    # Pattern: "        const XXXX_DATA = " seguido de JSON
    data_vars = [
        ('PROYECTOS_DATA', '[]'),
        ('BENEFICIARIOS_DATA', '[]'),
        ('DESPACHOS_DATA', '[]'),
        ('SOLICITUDES_DATA', '[]'),
        ('INSPECCIONES_DATA', '[]'),
        ('REPORTES_DATA', '[]'),
        ('SOLPAGO_DATA', '[]'),
        ('MAESTROS_DICT', '{}'),
        ('PRESUPUESTO_DATA', '{}'),
        ('GARANTIAS_DATA', '[]'),
        ('EEPP_DATA', '[]'),
    ]

    for var_name, empty_val in data_vars:
        # Match: const VAR_NAME = <anything until next "const " or "// ">
        # Use a more reliable approach: find the line and replace up to the semicolon
        pattern = rf'(        const {var_name} = ).*?;'

        # For large JSON blobs, we need to find start and end manually
        marker = f'        const {var_name} = '
        idx = html.find(marker)
        if idx == -1:
            print(f"  WARN: No se encontro {var_name}")
            continue

        # Find the matching semicolon - for arrays/objects, count brackets
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
            # Also skip the semicolon after
            if end < len(html) and html[end] == ';':
                end += 1

            old_text = html[idx:end]
            new_text = f'        let {var_name} = {empty_val};'
            html = html[:idx] + new_text + html[end:]
            size_saved = len(old_text) - len(new_text)
            print(f"  {var_name}: reemplazado ({size_saved:,} chars removidos)")
        else:
            print(f"  WARN: {var_name} formato inesperado")

    # 2. Inyectar DataLoader antes del primer componente React
    loader_js = get_data_loader_js(apps_script_url)

    # Insertar justo despues de los iconos SVG y antes de ETAPAS_CONFIG
    insert_marker = '        // ===== CONFIG ETAPAS ====='
    idx = html.find(insert_marker)
    if idx != -1:
        html = html[:idx] + loader_js + '\n\n' + html[idx:]
        print("  DataLoader inyectado")
    else:
        print("  WARN: No se encontro marcador para inyectar DataLoader")

    # 3. Reemplazar el render de React para que espere datos
    # Buscar cualquier variante de ReactDOM.createRoot(...).render(...)
    render_patterns = [
        "        ReactDOM.createRoot(document.getElementById('root')).render(<DashboardObras />);",
        "        const root = ReactDOM.createRoot(document.getElementById('root'));\n        root.render(<DashboardObras />);",
        "        const root = ReactDOM.createRoot(document.getElementById('root'));\n        root.render(<App />);",
    ]

    new_render = """        // Funcion de render (llamada despues de cargar datos)
        function renderApp() {
            ReactDOM.createRoot(document.getElementById('root')).render(<DashboardObras />);
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
            print("  Render React reemplazado por version async")
            render_replaced = True
            break

    if not render_replaced:
        print("  WARN: No se encontro bloque de render React")

    # 4. Actualizar titulo
    html = html.replace(
        '<title>Panel de Control de Obras v2 - SG Raices</title>',
        '<title>Panel de Control de Obras - SG Raices (Live)</title>'
    )

    # 5. Agregar indicador de "datos en vivo" en la UI
    # Agregar un badge "LIVE" junto al titulo del header
    html = html.replace(
        'Panel de Control de Obras',
        'Panel de Control de Obras <span style="background:#22c55e;color:white;font-size:9px;padding:2px 6px;border-radius:4px;margin-left:8px;vertical-align:middle;">LIVE</span>',
        1  # Solo la primera ocurrencia (en el header del dashboard)
    )

    # Guardar
    output_path = Path(__file__).parent.parent / 'dashboard' / 'index_live.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nDashboard LIVE generado: {output_path}")
    print(f"  Tamano: {size_kb:.0f} KB")
    print(f"  Apps Script URL: {apps_script_url}")
    print(f"\nPara usar:")
    print(f"  1. Despliega el Apps Script (ver apps_script/Code.gs)")
    print(f"  2. Abre {output_path} en el navegador")
    print(f"  3. Los datos se cargan en tiempo real al abrir")

    return str(output_path)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'PLACEHOLDER_URL'

    if url == 'PLACEHOLDER_URL':
        print("=" * 60)
        print("DASHBOARD LIVE - Generador")
        print("=" * 60)
        print("\nADVERTENCIA: No se proporciono URL del Apps Script.")
        print("Usa: python generar_dashboard_live.py <URL_APPS_SCRIPT>")
        print("\nSe generara con URL placeholder. Deberas editarla manualmente")
        print("en el HTML generado (buscar 'PLACEHOLDER_URL').\n")

    # Primero regenerar v2 si no existe
    v2_path = Path(__file__).parent.parent / 'dashboard' / 'index_v2.html'
    if not v2_path.exists():
        print("index_v2.html no existe. Generando primero...")
        import generar_dashboard_v2
        generar_dashboard_v2.generar_dashboard_v2_html()

    make_live_dashboard(url)


if __name__ == '__main__':
    main()

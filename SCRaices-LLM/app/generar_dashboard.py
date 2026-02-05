"""
Genera el Dashboard de Control de Obras con datos reales de Google Sheets

FORMATOS DE DATOS (no cambiarán):
- Fechas de Google Sheets: M/D/YYYY (formato americano)
  Ejemplo: 2/4/2026 = 4 de febrero de 2026
- Fechas internas del dashboard: YYYY-MM-DD (ISO 8601)
"""
import sys
sys.path.insert(0, '.')
import json
from data_manager import DataManager
from pathlib import Path

def generar_dashboard_html():
    """Genera el archivo HTML del dashboard con datos reales"""

    print("Cargando datos desde Google Sheets...")
    dm = DataManager()

    # Cargar tablas necesarias
    proyectos = dm.get_table_data('Proyectos')
    beneficiarios = dm.get_table_data('Beneficiario')
    despachos = dm.get_table_data('Despacho')
    solicitudes = dm.get_table_data('soldepacho')

    # Filtrar proyectos en ejecución
    proyectos_activos = proyectos[
        proyectos['estado_general'].str.lower().str.contains('ejecuci', na=False)
    ].copy()

    print(f"Proyectos activos: {len(proyectos_activos)}")

    # Preparar datos de proyectos
    proyectos_data = []
    for _, p in proyectos_activos.iterrows():
        proyectos_data.append({
            'ID_proy': str(p.get('ID_proy', '')),
            'NOMBRE_PROYECTO': str(p.get('NOMBRE_PROYECTO', '')),
            'COMUNA': str(p.get('COMUNA', ''))
        })

    # Filtrar beneficiarios activos de proyectos activos
    # Incluir estados: Ejecución, Subsidiado, Preparación
    ids_proyectos = set(proyectos_activos['ID_proy'].astype(str).tolist())
    estados_validos = ['ejecuci', 'subsidiad', 'preparaci']
    beneficiarios_activos = beneficiarios[
        (beneficiarios['ID_Proy'].astype(str).isin(ids_proyectos)) &
        (beneficiarios['Estado'].str.lower().str.contains('|'.join(estados_validos), na=False, regex=True))
    ].copy()

    print(f"Beneficiarios en ejecución: {len(beneficiarios_activos)}")

    # Preparar datos de beneficiarios
    beneficiarios_data = []
    for _, b in beneficiarios_activos.iterrows():
        tipologia = str(b.get('Tipologia Vivienda', ''))
        tipologia_rc = str(b.get('Tipologia RC', ''))
        tipo_display = "Casa + RC" if tipologia_rc and tipologia_rc.lower() not in ['nan', '', 'none'] else "Casa"

        beneficiarios_data.append({
            'ID_Benef': int(b['ID_Benef']) if str(b['ID_Benef']).isdigit() else str(b['ID_Benef']),
            'ID_Proy': str(b.get('ID_Proy', '')),
            'NOMBRES': str(b.get('NOMBRES', '')),
            'APELLIDOS': str(b.get('APELLIDOS', '')),
            'tipologia': tipo_display
        })

    # Preparar datos de despachos
    ids_beneficiarios = set([str(b['ID_Benef']) for b in beneficiarios_data])
    despachos_filtrados = despachos[
        despachos['ID_Benef'].astype(str).isin(ids_beneficiarios)
    ].copy()

    print(f"Despachos encontrados: {len(despachos_filtrados)}")

    despachos_data = []
    for _, d in despachos_filtrados.iterrows():
        fecha = str(d.get('Fecha', ''))
        # FORMATO DE FECHAS DE GOOGLE SHEETS: M/D/YYYY (americano)
        # Ejemplo: 2/4/2026 = 4 de febrero de 2026
        if fecha and fecha not in ['nan', 'NaT', '']:
            try:
                from datetime import datetime
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

    # Preparar solicitudes
    solicitudes_filtradas = solicitudes[
        solicitudes['ID_Benef'].astype(str).isin(ids_beneficiarios)
    ].copy()

    print(f"Solicitudes encontradas: {len(solicitudes_filtradas)}")

    solicitudes_data = []
    for _, s in solicitudes_filtradas.iterrows():
        fecha = str(s.get('Fecha', ''))
        fecha_creacion = str(s.get('fecha_creacion', ''))

        # FORMATO DE FECHAS DE GOOGLE SHEETS: M/D/YYYY (americano)
        from datetime import datetime
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

    # Generar HTML
    html_content = generate_html_template(
        proyectos_data,
        beneficiarios_data,
        despachos_data,
        solicitudes_data
    )

    # Guardar archivo
    output_path = Path(__file__).parent.parent / 'dashboard' / 'index.html'
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\nDashboard generado: {output_path}")
    print(f"  - Proyectos: {len(proyectos_data)}")
    print(f"  - Beneficiarios: {len(beneficiarios_data)}")
    print(f"  - Despachos: {len(despachos_data)}")
    print(f"  - Solicitudes: {len(solicitudes_data)}")

    return str(output_path)


def generate_html_template(proyectos, beneficiarios, despachos, solicitudes):
    """Genera el HTML con los datos embebidos"""

    proyectos_json = json.dumps(proyectos, ensure_ascii=False, indent=2)
    beneficiarios_json = json.dumps(beneficiarios, ensure_ascii=False, indent=2)
    despachos_json = json.dumps(despachos, ensure_ascii=False, indent=2)
    solicitudes_json = json.dumps(solicitudes, ensure_ascii=False, indent=2)

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Control de Obras - SG Raíces</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        'raices-red': '#8B2332',
                        'raices-dark': '#1a1a2e',
                        'sidebar': '#f5f5f5',
                        'card-border': '#e5e7eb'
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .animate-pulse {{ animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .sidebar-item:hover {{ background-color: #e8e8e8; }}
        .sidebar-item.active {{ background-color: #fff; border-left: 3px solid #8B2332; }}
    </style>
</head>
<body class="bg-gray-100">
    <div id="root"></div>
    <script type="text/babel">
        // ===== ICONOS SVG =====
        const IconHome = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>;
        const IconBuilding = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>;
        const IconAlert = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>;
        const IconCheck = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
        const IconClock = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
        const IconSearch = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>;
        const IconChevronDown = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M19 9l-7 7-7-7" /></svg>;
        const IconChevronRight = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M9 5l7 7-7 7" /></svg>;
        const IconTrending = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>;
        const IconEye = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>;
        const IconUsers = () => <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>;

        // ===== CONFIG ETAPAS =====
        const ETAPAS_CONFIG = {{
            "01_FUNDACIONES": {{ codigo: "01", nombre: "Fundaciones", duracion: 3, tiempo_optimo: null, tiempo_alerta: null, dependencia: null, es_inicio: true, critico: false }},
            "02_1ERA_ETAPA": {{ codigo: "02", nombre: "1era Etapa", duracion: 21, tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "01_FUNDACIONES", critico: true }},
            "28_VENTANAS": {{ codigo: "28", nombre: "Ventanas", duracion: 1, tiempo_optimo: 3, tiempo_alerta: 7, dependencia: "02_1ERA_ETAPA", desde_inicio_dependencia: true, critico: true }},
            "03_2DA_ETAPA": {{ codigo: "03", nombre: "2da Etapa", duracion: 10, tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA", critico: true }},
            "08_CERAMICO_MURO": {{ codigo: "08", nombre: "Cerámico Muro", duracion: 3, tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "03_2DA_ETAPA", critico: true }},
            "13_GASFITERIA": {{ codigo: "13", nombre: "Gasfitería + Artef.", duracion: 5, tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "08_CERAMICO_MURO", critico: true }}
        }};
        // Nota: 11_SOL_AC (Artefactos) está incluido en 13_GASFITERIA, no se muestra por separado
        const SECUENCIA_PRINCIPAL = ["01_FUNDACIONES", "02_1ERA_ETAPA", "28_VENTANAS", "03_2DA_ETAPA", "08_CERAMICO_MURO", "13_GASFITERIA"];

        // ===== DATOS REALES =====
        const PROYECTOS_DATA = {proyectos_json};
        const BENEFICIARIOS_DATA = {beneficiarios_json};
        const DESPACHOS_DATA = {despachos_json};
        const SOLICITUDES_DATA = {solicitudes_json};

        // ===== FUNCIONES UTILIDAD =====
        // Mapea UN segmento de tipo_despacho a su etapa correspondiente
        const mapearSegmento = (segmento) => {{
            if (!segmento) return null;
            const t = segmento.toLowerCase().trim();
            if (t.includes("fundacion") && !t.includes("eifs") && !t.includes("aislacion")) return "01_FUNDACIONES";
            if (t.includes("1era")) return "02_1ERA_ETAPA";
            if (t.includes("ventana")) return "28_VENTANAS";
            if (t.includes("2da")) return "03_2DA_ETAPA";
            if (t.includes("muro") && t.includes("ceram")) return "08_CERAMICO_MURO";
            if (t.includes("08-") && t.includes("muro")) return "08_CERAMICO_MURO";
            if (t.includes("gasfiter") || t.includes("sol. ac") || t.includes("artefact") || t.includes("cocina") || t.includes("calefont")) return "13_GASFITERIA";
            return null;
        }};

        // Mapea un tipo_despacho completo (puede contener múltiples etapas separadas por coma)
        const mapearTipoDespacho = (tipo) => {{
            if (!tipo) return [];
            // Dividir por comas y mapear cada segmento
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

        const calcularEstadoEtapas = (idBenef) => {{
            const despachos = DESPACHOS_DATA.filter(d => String(d.ID_Benef) === String(idBenef));
            const etapasCompletadas = {{}};
            despachos.forEach(d => {{
                // mapearTipoDespacho ahora retorna un ARRAY de etapas
                const keys = mapearTipoDespacho(d.Tipo_despacho);
                keys.forEach(key => {{
                    // Solo guardar si no existe o si esta fecha es más reciente
                    if (!etapasCompletadas[key] || new Date(d.Fecha) > new Date(etapasCompletadas[key].fecha)) {{
                        etapasCompletadas[key] = {{ fecha: d.Fecha, guia: d.Guia, dias: calcularDias(d.Fecha) }};
                    }}
                }});
            }});

            const resultado = {{}};
            Object.entries(ETAPAS_CONFIG).forEach(([etapaKey, config]) => {{
                const info = {{ key: etapaKey, nombre: config.nombre, codigo: config.codigo, estado: "bloqueado", fechaDespacho: null, guia: null, diasTranscurridos: null, diasRestantes: null }};

                if (etapasCompletadas[etapaKey]) {{
                    info.estado = "despachado";
                    info.fechaDespacho = etapasCompletadas[etapaKey].fecha;
                    info.guia = etapasCompletadas[etapaKey].guia;
                    info.diasTranscurridos = etapasCompletadas[etapaKey].dias;
                }} else {{
                    const dep = config.dependencia;
                    let puedeIniciar = config.es_inicio || false;
                    let fechaRef = null;

                    if (dep && etapasCompletadas[dep]) {{
                        puedeIniciar = true;
                        fechaRef = etapasCompletadas[dep].fecha;
                    }}

                    if (puedeIniciar && fechaRef) {{
                        const diasBrutos = calcularDias(fechaRef);
                        // Si desde_inicio_dependencia=true, contar desde el despacho (no restar duración)
                        // Si no, contar desde el término (restar duración de etapa anterior)
                        const duracionPrevia = config.desde_inicio_dependencia ? 0 : (ETAPAS_CONFIG[dep]?.duracion || 0);
                        const diasEfectivos = Math.max(0, diasBrutos - duracionPrevia);
                        info.diasTranscurridos = diasEfectivos;

                        if (config.tiempo_optimo !== null && config.tiempo_alerta !== null) {{
                            info.diasRestantes = config.tiempo_alerta - diasEfectivos;
                            // Verde: antes de óptimo, Amarillo: entre óptimo y alerta, Rojo: al llegar a alerta
                            if (diasEfectivos < config.tiempo_optimo) info.estado = "en_tiempo";
                            else if (diasEfectivos < config.tiempo_alerta) info.estado = "atencion";
                            else info.estado = "critico";
                        }} else {{
                            info.estado = "en_tiempo";
                        }}
                    }} else if (config.es_inicio) {{
                        info.estado = "en_tiempo";
                    }}
                }}
                resultado[etapaKey] = info;
            }});
            return resultado;
        }};

        const getUltimaEtapa = (estados) => {{
            let ultima = null, maxFecha = null;
            Object.values(estados).forEach(info => {{
                if (info.estado === "despachado" && info.fechaDespacho) {{
                    const f = new Date(info.fechaDespacho);
                    if (!maxFecha || f > maxFecha) {{ maxFecha = f; ultima = info; }}
                }}
            }});
            return ultima;
        }};

        const getProximaCritica = (estados) => {{
            for (const k of SECUENCIA_PRINCIPAL) {{
                if (estados[k] && estados[k].estado !== "despachado") return estados[k];
            }}
            return null;
        }};

        const calcularAvance = (estados) => {{
            const comp = SECUENCIA_PRINCIPAL.filter(k => estados[k]?.estado === "despachado").length;
            return {{ completadas: comp, total: SECUENCIA_PRINCIPAL.length, porcentaje: Math.round((comp / SECUENCIA_PRINCIPAL.length) * 100) }};
        }};

        const getEstadoGeneral = (estados) => {{
            let critico = false, atencion = false;
            Object.values(estados).forEach(i => {{
                if (i.estado === "critico") critico = true;
                if (i.estado === "atencion") atencion = true;
            }});
            return critico ? "critico" : atencion ? "atencion" : "en_tiempo";
        }};

        // ===== COMPONENTES =====
        const EstadoBadge = ({{ estado }}) => {{
            const estilos = {{
                despachado: "bg-blue-100 text-blue-700 border-blue-200",
                en_tiempo: "bg-green-100 text-green-700 border-green-200",
                atencion: "bg-yellow-100 text-yellow-700 border-yellow-200",
                critico: "bg-red-100 text-red-700 border-red-200",
                bloqueado: "bg-gray-100 text-gray-500 border-gray-200"
            }};
            const labels = {{ despachado: "Despachado", en_tiempo: "En tiempo", atencion: "Atención", critico: "Crítico", bloqueado: "Bloqueado" }};
            return <span className={{`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${{estilos[estado]}}`}}>{{labels[estado]}}</span>;
        }};

        const EtapaChip = ({{ info }}) => {{
            const colores = {{ despachado: "bg-blue-500", en_tiempo: "bg-green-500", atencion: "bg-yellow-500", critico: "bg-red-500 animate-pulse", bloqueado: "bg-gray-300" }};
            return <div className={{`w-8 h-8 rounded-full ${{colores[info.estado]}} flex items-center justify-center text-white text-xs font-bold shadow`}}>{{info.codigo}}</div>;
        }};

        // Componente de Línea de Tiempo
        const LineaTiempo = ({{ estadoEtapas }}) => {{
            // Obtener fecha de Fundaciones como Día 1
            const fundaciones = estadoEtapas["01_FUNDACIONES"];
            const fechaInicio = fundaciones?.fechaDespacho ? new Date(fundaciones.fechaDespacho) : null;

            const calcularDiaRelativo = (fechaDespacho) => {{
                if (!fechaInicio || !fechaDespacho) return null;
                const fecha = new Date(fechaDespacho);
                const diff = Math.floor((fecha - fechaInicio) / (1000 * 60 * 60 * 24));
                return diff + 1; // Día 1 es el despacho de fundaciones
            }};

            const colores = {{
                despachado: "bg-blue-500 text-white",
                en_tiempo: "bg-green-100 text-green-700 border border-green-300",
                atencion: "bg-yellow-100 text-yellow-700 border border-yellow-300",
                critico: "bg-red-100 text-red-700 border border-red-300 animate-pulse",
                bloqueado: "bg-gray-100 text-gray-400 border border-gray-200"
            }};

            return (
                <div className="mt-4 overflow-x-auto">
                    <div className="flex items-stretch gap-1 min-w-max">
                        {{SECUENCIA_PRINCIPAL.map((etapaKey, idx) => {{
                            const info = estadoEtapas[etapaKey];
                            const diaRelativo = info?.estado === "despachado" ? calcularDiaRelativo(info.fechaDespacho) : null;
                            const esperaDias = info?.diasTranscurridos;

                            return (
                                <React.Fragment key={{etapaKey}}>
                                    <div className={{`flex flex-col items-center rounded-lg px-2 py-1.5 ${{colores[info?.estado || "bloqueado"]}}`}} style={{{{ minWidth: "70px" }}}}>
                                        <span className="text-xs font-bold">
                                            {{info?.estado === "despachado" ? (
                                                `Día ${{diaRelativo}}`
                                            ) : info?.estado === "bloqueado" ? (
                                                "—"
                                            ) : (
                                                `+${{esperaDias || 0}}d`
                                            )}}
                                        </span>
                                        <span className="text-[10px] leading-tight text-center mt-0.5">{{info?.nombre}}</span>
                                        {{info?.estado === "despachado" && info?.guia && (
                                            <span className="text-[9px] opacity-75">#{{info.guia}}</span>
                                        )}}
                                    </div>
                                    {{idx < SECUENCIA_PRINCIPAL.length - 1 && (
                                        <div className="flex items-center">
                                            <div className={{`w-4 h-0.5 ${{info?.estado === "despachado" ? "bg-blue-400" : "bg-gray-200"}}`}} />
                                            <span className="text-gray-300 text-xs">→</span>
                                            <div className={{`w-4 h-0.5 ${{estadoEtapas[SECUENCIA_PRINCIPAL[idx + 1]]?.estado === "despachado" ? "bg-blue-400" : "bg-gray-200"}}`}} />
                                        </div>
                                    )}}
                                </React.Fragment>
                            );
                        }})}}
                    </div>
                </div>
            );
        }};

        const BarraProgreso = ({{ porcentaje }}) => {{
            let color = "bg-green-500";
            if (porcentaje < 30) color = "bg-red-400";
            else if (porcentaje < 60) color = "bg-yellow-400";
            else if (porcentaje < 90) color = "bg-blue-400";
            return <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden"><div className={{`h-2 ${{color}} rounded-full transition-all`}} style={{{{ width: `${{porcentaje}}%` }}}} /></div>;
        }};

        const KPICard = ({{ titulo, valor, icono, color, subtitulo }}) => {{
            const colores = {{
                green: "border-green-200 text-green-600",
                yellow: "border-yellow-200 text-yellow-600",
                red: "border-red-200 text-red-600",
                blue: "border-blue-200 text-blue-600"
            }};
            const bgColores = {{
                green: "bg-green-50",
                yellow: "bg-yellow-50",
                red: "bg-red-50",
                blue: "bg-blue-50"
            }};
            return (
                <div className={{`bg-white border ${{colores[color]}} rounded-xl p-4 shadow-sm`}}>
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-gray-500 text-sm">{{titulo}}</p>
                            <p className="text-2xl font-bold text-gray-800 mt-1">{{valor}}</p>
                            {{subtitulo && <p className="text-xs text-gray-400 mt-1">{{subtitulo}}</p>}}
                        </div>
                        <div className={{`p-3 rounded-lg ${{bgColores[color]}}`}}>{{icono}}</div>
                    </div>
                </div>
            );
        }};

        const ViviendaCard = ({{ beneficiario, estadoEtapas, expanded, onToggle }}) => {{
            const avance = calcularAvance(estadoEtapas);
            const estadoGeneral = getEstadoGeneral(estadoEtapas);
            const ultimaEtapa = getUltimaEtapa(estadoEtapas);
            const proximaEtapa = getProximaCritica(estadoEtapas);

            const borderColor = {{ critico: "border-l-4 border-l-red-500 border-red-100", atencion: "border-l-4 border-l-yellow-500 border-yellow-100", en_tiempo: "border border-gray-200" }};

            return (
                <div className={{`bg-white ${{borderColor[estadoGeneral]}} rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow`}}>
                    <div className="p-4 cursor-pointer hover:bg-gray-50 transition-colors" onClick={{onToggle}}>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <span className="text-gray-400">{{expanded ? <IconChevronDown /> : <IconChevronRight />}}</span>
                                <div className="flex items-center gap-2">
                                    <span className={{beneficiario.tipologia.includes("RC") ? "text-blue-600" : "text-gray-500"}}>{{beneficiario.tipologia.includes("RC") ? <IconBuilding /> : <IconHome />}}</span>
                                    <div>
                                        <h3 className="font-semibold text-gray-800">{{beneficiario.NOMBRES}} {{beneficiario.APELLIDOS}}</h3>
                                        <p className="text-xs text-gray-500">{{beneficiario.tipologia}}</p>
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                <div className="text-right">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm text-gray-500">{{avance.completadas}}/{{avance.total}}</span>
                                        <span className="text-lg font-bold text-gray-700">{{avance.porcentaje}}%</span>
                                    </div>
                                    <div className="w-24"><BarraProgreso porcentaje={{avance.porcentaje}} /></div>
                                </div>
                                <EstadoBadge estado={{estadoGeneral}} />
                            </div>
                        </div>

                        {{/* Línea de Tiempo */}}
                        <LineaTiempo estadoEtapas={{estadoEtapas}} />

                        <div className="mt-3 flex items-center justify-between text-sm">
                            <div className="text-gray-500">
                                {{ultimaEtapa ? (
                                    <span>Última: <span className="text-gray-700 font-medium">{{ultimaEtapa.nombre}}</span> — Guía #{{ultimaEtapa.guia}} — <span className={{estadoGeneral === "critico" ? "text-red-600 font-medium" : estadoGeneral === "atencion" ? "text-yellow-600" : "text-green-600"}}>hace {{ultimaEtapa.diasTranscurridos}} días</span></span>
                                ) : <span className="text-yellow-600">Sin despachos registrados</span>}}
                            </div>
                            <div className="flex items-center gap-1 text-gray-400"><IconEye /><span>Insp: 0%</span></div>
                        </div>

                        {{estadoGeneral === "critico" && proximaEtapa && (
                            <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded-lg">
                                <div className="flex items-center gap-2 text-red-600 text-sm">
                                    <span className="animate-pulse"><IconAlert /></span>
                                    <span><strong>{{proximaEtapa.nombre}}</strong> atrasado {{proximaEtapa.diasTranscurridos - 14}} días — ¿Por qué no se ha solicitado?</span>
                                </div>
                            </div>
                        )}}
                    </div>

                    {{expanded && (
                        <div className="border-t border-gray-100 p-4 bg-gray-50">
                            <h4 className="text-sm font-medium text-gray-700 mb-3">Detalle de Etapas</h4>
                            <div className="space-y-2">
                                {{Object.entries(estadoEtapas).map(([key, info]) => (
                                    <div key={{key}} className="flex items-center gap-3 text-sm">
                                        <EtapaChip info={{info}} />
                                        <span className="text-gray-700 flex-1">{{info.nombre}}</span>
                                        <span className="text-gray-500">
                                            {{info.estado === "despachado" && `Guía #${{info.guia}} — ${{info.diasTranscurridos}}d`}}
                                            {{info.estado === "critico" && <span className="text-red-600">🔴 {{info.diasTranscurridos}}d</span>}}
                                            {{info.estado === "atencion" && <span className="text-yellow-600">⚠️ {{info.diasTranscurridos}}d</span>}}
                                            {{info.estado === "en_tiempo" && info.diasTranscurridos && <span className="text-green-600">✓ {{info.diasTranscurridos}}d</span>}}
                                            {{info.estado === "bloqueado" && "Bloqueado"}}
                                        </span>
                                    </div>
                                ))}}
                            </div>
                        </div>
                    )}}
                </div>
            );
        }};

        // ===== COMPONENTE CONFIGURACIÓN DE ETAPAS =====
        const ConfiguracionEtapas = () => {{
            const [expanded, setExpanded] = React.useState(false);

            const etapasArray = Object.entries(ETAPAS_CONFIG).map(([key, config]) => ({{
                key,
                ...config,
                enRutaCritica: SECUENCIA_PRINCIPAL.includes(key)
            }}));

            return (
                <div className="mt-6 bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
                    <div
                        className="p-4 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
                        onClick={{() => setExpanded(!expanded)}}
                    >
                        <div className="flex items-center gap-3">
                            <span className="text-gray-400">{{expanded ? <IconChevronDown /> : <IconChevronRight />}}</span>
                            <h4 className="text-sm font-medium text-gray-700">⚙️ Configuración de Etapas y Ruta Crítica</h4>
                        </div>
                        <span className="text-xs text-gray-500">{{expanded ? "Ocultar" : "Ver configuración"}}</span>
                    </div>

                    {{expanded && (
                        <div className="border-t border-gray-100 p-4 space-y-6">
                            {{/* Ruta Crítica */}}
                            <div>
                                <h5 className="text-sm font-medium text-gray-800 mb-3">🔴 Ruta Crítica (Secuencia Obligatoria)</h5>
                                <div className="flex items-center gap-2 flex-wrap">
                                    {{SECUENCIA_PRINCIPAL.map((key, idx) => (
                                        <React.Fragment key={{key}}>
                                            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-center">
                                                <div className="text-red-600 font-bold text-sm">{{ETAPAS_CONFIG[key]?.codigo}}</div>
                                                <div className="text-xs text-gray-600">{{ETAPAS_CONFIG[key]?.nombre}}</div>
                                            </div>
                                            {{idx < SECUENCIA_PRINCIPAL.length - 1 && (
                                                <span className="text-gray-400">→</span>
                                            )}}
                                        </React.Fragment>
                                    ))}}
                                </div>
                                <p className="text-xs text-gray-500 mt-2">
                                    Si una etapa de la ruta crítica se atrasa más de 14 días, se genera alerta roja.
                                </p>
                            </div>

                            {{/* Tabla de Configuración */}}
                            <div>
                                <h5 className="text-sm font-medium text-gray-800 mb-3">📋 Configuración de Tiempos por Etapa</h5>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50">
                                                <th className="py-2 px-3">Cód</th>
                                                <th className="py-2 px-3">Etapa</th>
                                                <th className="py-2 px-3 text-center">Duración</th>
                                                <th className="py-2 px-3 text-center">🟢 Óptimo</th>
                                                <th className="py-2 px-3 text-center">🔴 Alerta</th>
                                                <th className="py-2 px-3">Dependencia</th>
                                                <th className="py-2 px-3 text-center">Crítica</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {{etapasArray.map((etapa) => (
                                                <tr key={{etapa.key}} className={{`border-b border-gray-100 ${{etapa.enRutaCritica ? "bg-red-50/50" : ""}}`}}>
                                                    <td className="py-2 px-3 font-mono text-gray-600">{{etapa.codigo}}</td>
                                                    <td className="py-2 px-3 text-gray-800">{{etapa.nombre}}</td>
                                                    <td className="py-2 px-3 text-center text-gray-500">{{etapa.duracion}}d</td>
                                                    <td className="py-2 px-3 text-center">
                                                        {{etapa.tiempo_optimo !== null ? (
                                                            <span className="text-green-600">{{etapa.tiempo_optimo}}d</span>
                                                        ) : <span className="text-gray-300">-</span>}}
                                                    </td>
                                                    <td className="py-2 px-3 text-center">
                                                        {{etapa.tiempo_alerta !== null ? (
                                                            <span className="text-red-600">{{etapa.tiempo_alerta}}d</span>
                                                        ) : <span className="text-gray-300">-</span>}}
                                                    </td>
                                                    <td className="py-2 px-3 text-gray-500 text-xs">
                                                        {{etapa.dependencia ? ETAPAS_CONFIG[etapa.dependencia]?.nombre || etapa.dependencia : (etapa.es_inicio ? "🏁 Inicio" : "-")}}
                                                    </td>
                                                    <td className="py-2 px-3 text-center">
                                                        {{etapa.enRutaCritica ? (
                                                            <span className="text-red-500">●</span>
                                                        ) : (
                                                            <span className="text-gray-300">○</span>
                                                        )}}
                                                    </td>
                                                </tr>
                                            ))}}
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            {{/* Reglas */}}
                            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                                <h5 className="text-sm font-medium text-gray-800 mb-2">📐 Reglas de Cálculo</h5>
                                <ul className="text-xs text-gray-600 space-y-1">
                                    <li>• <span className="text-green-600 font-medium">Verde (En tiempo)</span>: días_efectivos &lt; tiempo_óptimo (antes del óptimo)</li>
                                    <li>• <span className="text-yellow-600 font-medium">Amarillo (Atención)</span>: tiempo_óptimo ≤ días_efectivos &lt; tiempo_alerta (entre óptimo y alerta)</li>
                                    <li>• <span className="text-red-600 font-medium">Rojo (Crítico)</span>: días_efectivos ≥ tiempo_alerta (al llegar o pasar alerta)</li>
                                    <li>• <strong>días_efectivos</strong> = días_desde_despacho_anterior - duración_etapa_anterior</li>
                                    <li>• Una etapa está <span className="text-gray-500 font-medium">Bloqueada</span> si su dependencia no ha sido despachada</li>
                                    <li>• <strong>Ventanas</strong> tiene tiempos especiales: óptimo 3d, alerta 7d</li>
                                </ul>
                            </div>
                        </div>
                    )}}
                </div>
            );
        }};

        // ===== SIDEBAR =====
        const Sidebar = ({{ menuActivo, onMenuClick }}) => {{
            const menuItems = [
                {{ id: "inicio", icon: <IconHome />, label: "Inicio" }},
                {{ id: "proyectos", icon: <IconBuilding />, label: "Proyectos" }},
                {{ id: "obras", icon: <IconBuilding />, label: "Obras", active: true }},
                {{ id: "reportes", icon: <IconTrending />, label: "Reportes" }}
            ];

            return (
                <aside className="w-56 bg-sidebar border-r border-gray-200 min-h-screen flex-shrink-0">
                    {{/* Logo */}}
                    <div className="p-4 border-b border-gray-200">
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 bg-raices-dark rounded flex items-center justify-center">
                                <span className="text-white text-xs font-bold">SG</span>
                            </div>
                            <div>
                                <div className="font-semibold text-gray-800 text-sm">SG Raíces</div>
                            </div>
                        </div>
                    </div>

                    {{/* Menu */}}
                    <nav className="p-2">
                        {{menuItems.map(item => (
                            <div
                                key={{item.id}}
                                onClick={{() => onMenuClick(item.id)}}
                                className={{`sidebar-item flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-sm mb-1 ${{item.active ? 'active font-medium text-gray-800' : 'text-gray-600 hover:text-gray-800'}}`}}
                            >
                                <span className={{item.active ? 'text-raices-red' : 'text-gray-400'}}>{{item.icon}}</span>
                                {{item.label}}
                            </div>
                        ))}}
                    </nav>
                </aside>
            );
        }};

        // ===== HEADER =====
        const Header = ({{ proyectoSel, onProyectoChange, busqueda, onBusquedaChange }}) => (
            <header className="bg-white border-b border-gray-200 sticky top-0 z-50 px-6 py-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <h1 className="text-lg font-semibold text-gray-800">Control de Obras</h1>
                        <select
                            value={{proyectoSel}}
                            onChange={{(e) => onProyectoChange(e.target.value)}}
                            className="bg-white border border-gray-300 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:ring-2 focus:ring-raices-red focus:border-raices-red focus:outline-none"
                        >
                            {{PROYECTOS_DATA.map(p => <option key={{p.ID_proy}} value={{p.ID_proy}}>{{p.NOMBRE_PROYECTO}}</option>)}}
                        </select>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="relative">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"><IconSearch /></span>
                            <input
                                type="text"
                                placeholder="Buscar beneficiario..."
                                value={{busqueda}}
                                onChange={{(e) => onBusquedaChange(e.target.value)}}
                                className="w-64 bg-gray-100 border border-gray-200 rounded-lg pl-10 pr-4 py-2 text-sm focus:ring-2 focus:ring-raices-red focus:border-raices-red focus:outline-none focus:bg-white"
                            />
                        </div>
                        <div className="flex items-center gap-2 text-sm text-gray-500">
                            <span>Syncing...</span>
                            <div className="w-6 h-6 rounded-full bg-gray-200"></div>
                        </div>
                    </div>
                </div>
            </header>
        );

        // ===== DASHBOARD PRINCIPAL =====
        const DashboardObras = () => {{
            // Default: Ñuke Mapu (P119)
            const defaultProy = PROYECTOS_DATA.find(p => p.ID_proy === "P119")?.ID_proy || PROYECTOS_DATA[0]?.ID_proy || "";
            const [proyectoSel, setProyectoSel] = React.useState(defaultProy);
            const [busqueda, setBusqueda] = React.useState("");
            const [filtro, setFiltro] = React.useState("todos");
            const [expandida, setExpandida] = React.useState(null);
            const [menuActivo, setMenuActivo] = React.useState("obras");

            const beneficiarios = React.useMemo(() => BENEFICIARIOS_DATA.filter(b => String(b.ID_Proy) === String(proyectoSel)), [proyectoSel]);

            const viviendas = React.useMemo(() => beneficiarios.map(b => {{
                const estados = calcularEstadoEtapas(b.ID_Benef);
                const numDespachos = DESPACHOS_DATA.filter(d => String(d.ID_Benef) === String(b.ID_Benef)).length;
                return {{ ...b, estadoEtapas: estados, estadoGeneral: getEstadoGeneral(estados), avance: calcularAvance(estados), numDespachos }};
            }}), [beneficiarios]);

            const filtradas = React.useMemo(() => viviendas.filter(v => {{
                if (busqueda && !`${{v.NOMBRES}} ${{v.APELLIDOS}}`.toLowerCase().includes(busqueda.toLowerCase())) return false;
                if (filtro !== "todos" && v.estadoGeneral !== filtro) return false;
                return true;
            }}), [viviendas, busqueda, filtro]);

            const kpis = React.useMemo(() => ({{
                total: viviendas.length,
                enTiempo: viviendas.filter(v => v.estadoGeneral === "en_tiempo").length,
                atencion: viviendas.filter(v => v.estadoGeneral === "atencion").length,
                criticos: viviendas.filter(v => v.estadoGeneral === "critico").length,
                avance: viviendas.length ? Math.round(viviendas.reduce((s, v) => s + v.avance.porcentaje, 0) / viviendas.length) : 0
            }}), [viviendas]);

            const proy = PROYECTOS_DATA.find(p => String(p.ID_proy) === String(proyectoSel));

            return (
                <div className="min-h-screen bg-gray-100 flex">
                    {{/* Sidebar */}}
                    <Sidebar menuActivo={{menuActivo}} onMenuClick={{setMenuActivo}} />

                    {{/* Main Content */}}
                    <div className="flex-1 flex flex-col">
                        {{/* Header */}}
                        <Header
                            proyectoSel={{proyectoSel}}
                            onProyectoChange={{setProyectoSel}}
                            busqueda={{busqueda}}
                            onBusquedaChange={{setBusqueda}}
                        />

                        {{/* Content */}}
                        <main className="flex-1 p-6 overflow-auto">
                            {{/* Titulo Proyecto */}}
                            <div className="mb-6">
                                <p className="text-gray-500 text-sm mb-1">📍 Grupo: {{proy?.COMUNA}} • Código: {{proy?.ID_proy}}</p>
                                <h2 className="text-2xl font-bold text-gray-800">{{proy?.NOMBRE_PROYECTO}}</h2>
                            </div>

                            {{/* KPIs */}}
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                                <KPICard titulo="Total Viviendas" valor={{kpis.total}} icono={{<IconHome />}} color="blue" subtitulo="en ejecución" />
                                <KPICard titulo="En Tiempo" valor={{kpis.enTiempo}} icono={{<IconCheck />}} color="green" subtitulo="sin alertas" />
                                <KPICard titulo="Atención" valor={{kpis.atencion}} icono={{<IconClock />}} color="yellow" subtitulo="próximos a vencer" />
                                <KPICard titulo="Críticos" valor={{kpis.criticos}} icono={{<IconAlert />}} color="red" subtitulo="requieren acción" />
                                <div className="col-span-2 md:col-span-1 bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                                    <p className="text-gray-500 text-sm mb-2">Avance del Grupo</p>
                                    <div className="flex items-end gap-2">
                                        <span className="text-3xl font-bold text-gray-800">{{kpis.avance}}%</span>
                                        <span className="text-green-500 mb-1"><IconTrending /></span>
                                    </div>
                                    <div className="mt-2"><BarraProgreso porcentaje={{kpis.avance}} /></div>
                                </div>
                            </div>

                            {{/* Filtros */}}
                            <div className="flex gap-2 mb-6">
                                <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm">
                                    {{[["todos", "Todos"], ["critico", "Críticos"], ["atencion", "Atención"], ["en_tiempo", "En tiempo"]].map(([k, l]) => (
                                        <button
                                            key={{k}}
                                            onClick={{() => setFiltro(k)}}
                                            className={{`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${{
                                                filtro === k
                                                    ? "bg-raices-red text-white"
                                                    : "text-gray-600 hover:bg-gray-100"
                                            }}`}}
                                        >
                                            {{l}}
                                        </button>
                                    ))}}
                                </div>
                            </div>

                            {{/* Lista de Viviendas */}}
                            <div className="space-y-3">
                                {{filtradas.length === 0 ? (
                                    <div className="text-center py-12 text-gray-400 bg-white rounded-lg border border-gray-200">
                                        <IconUsers />
                                        <p className="mt-3">No se encontraron viviendas</p>
                                    </div>
                                ) : (
                                    filtradas.sort((a, b) => b.numDespachos - a.numDespachos)
                                        .map(v => <ViviendaCard key={{v.ID_Benef}} beneficiario={{v}} estadoEtapas={{v.estadoEtapas}} expanded={{expandida === v.ID_Benef}} onToggle={{() => setExpandida(expandida === v.ID_Benef ? null : v.ID_Benef)}} />)
                                )}}
                            </div>

                            {{/* Leyenda */}}
                            <div className="mt-6 p-4 bg-white border border-gray-200 rounded-lg shadow-sm">
                                <h4 className="text-sm font-medium text-gray-700 mb-3">Leyenda de Estados</h4>
                                <div className="flex flex-wrap gap-6 text-sm">
                                    <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-blue-500" /><span className="text-gray-600">Despachado</span></div>
                                    <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-green-500" /><span className="text-gray-600">En tiempo (&lt;7d)</span></div>
                                    <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-yellow-500" /><span className="text-gray-600">Atención (7-14d)</span></div>
                                    <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-red-500" /><span className="text-gray-600">Crítico (&gt;14d)</span></div>
                                    <div className="flex items-center gap-2"><div className="w-4 h-4 rounded-full bg-gray-300" /><span className="text-gray-600">Bloqueado</span></div>
                                </div>
                            </div>

                            {{/* Configuración de Etapas */}}
                            <ConfiguracionEtapas />

                            {{/* Footer */}}
                            <footer className="mt-6 text-center text-gray-400 text-sm">
                                <p>SG Raíces — Panel de Control de Obras v1.0</p>
                                <p className="text-xs mt-1">Generado: {{new Date().toLocaleString('es-CL')}}</p>
                            </footer>
                        </main>
                    </div>
                </div>
            );
        }};

        ReactDOM.createRoot(document.getElementById('root')).render(<DashboardObras />);
    </script>
</body>
</html>'''


if __name__ == "__main__":
    output = generar_dashboard_html()

    # Abrir en navegador
    import subprocess
    subprocess.run(['powershell', '-Command', f"Start-Process '{output}'"], shell=True)

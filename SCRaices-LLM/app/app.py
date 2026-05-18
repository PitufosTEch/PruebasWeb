import streamlit as st
import pandas as pd
import plotly.express as px
from query_engine import QueryEngine, PRESET_QUERIES
from data_manager import DataManager
from claude_query import ClaudeQueryEngine
from tabla_docs import TABLA_DOCS, EJEMPLOS_CONSULTAS, get_columnas_descripcion
from etapas_engine import EtapasEngine

st.set_page_config(
    page_title="SCRaices - Analisis de Datos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === SIDEBAR: DOCUMENTACIÓN DE DATOS ===
with st.sidebar:
    st.markdown("## 📚 Guía de Datos")
    st.caption("Usa esta referencia para escribir consultas precisas")

    # Selector de tabla
    tabla_seleccionada = st.selectbox(
        "Selecciona una tabla:",
        options=list(TABLA_DOCS.keys()),
        key="sidebar_tabla"
    )

    if tabla_seleccionada:
        doc = TABLA_DOCS[tabla_seleccionada]
        st.markdown(f"**{tabla_seleccionada}**")
        st.caption(doc.get("descripcion", ""))

        st.markdown("**Columnas:**")
        for col, desc in doc.get("columnas", {}).items():
            st.markdown(f"- `{col}`: {desc}")

    st.divider()

    # Ejemplos de consultas
    st.markdown("### 💡 Ejemplos")
    for ej in EJEMPLOS_CONSULTAS[:5]:
        with st.expander(ej["pregunta"], expanded=False):
            st.caption(f"Tablas: {', '.join(ej['tablas'])}")
            if 'columnas' in ej:
                st.caption(f"Columnas: {', '.join(ej['columnas'])}")

    st.divider()

    # Link para editar documentación
    st.markdown("### ⚙️ Configuración")
    st.caption("Para agregar más columnas o tablas, edita el archivo:")
    st.code("app/tabla_docs.py", language=None)


@st.cache_resource
def get_query_engine():
    return QueryEngine()


@st.cache_resource
def get_data_manager():
    return DataManager()


@st.cache_resource
def get_claude_engine():
    try:
        return ClaudeQueryEngine()
    except Exception as e:
        st.error(f"Error inicializando Claude: {e}")
        return None


@st.cache_resource
def get_etapas_engine(_dm):
    return EtapasEngine(_dm)


def render_estado_cell_html(cell_value: str, etapa_nombre: str, etapas_config: dict) -> str:
    """Renderiza celda con color y días según estado.
    cell_value viene como 'estado|dias' desde la matriz.
    """
    parts = str(cell_value).split("|")
    estado = parts[0] if len(parts) > 0 else "bloqueado"
    dias = parts[1] if len(parts) > 1 and parts[1] else ""

    emojis = {
        "despachado": "✅",
        "en_tiempo": "🟢",
        "atencion": "🟡",
        "critico": "🔴",
        "bloqueado": "⚪"
    }

    emoji = emojis.get(estado, "⚪")

    if estado == "despachado" and dias:
        dias_int = int(dias)
        # Los días representan tiempo entre despacho de dependencia y esta etapa.
        # Comparar contra los tiempos de ESTA etapa (tiempo_optimo/tiempo_alerta).
        tiempo_optimo = None
        tiempo_alerta = None
        for key, cfg in etapas_config.items():
            if cfg.get("nombre") == etapa_nombre:
                tiempo_optimo = cfg.get("tiempo_optimo")
                tiempo_alerta = cfg.get("tiempo_alerta")
                break

        color = "#888"
        if tiempo_alerta and dias_int > tiempo_alerta:
            color = "#ef4444"  # Rojo
        elif tiempo_optimo and dias_int > tiempo_optimo:
            color = "#eab308"  # Amarillo

        return f'<span style="color:{color};font-weight:bold">{dias_int}d</span> {emoji}'

    elif estado in ("en_tiempo", "atencion", "critico") and dias:
        colores_texto = {
            "en_tiempo": "#22c55e",
            "atencion": "#eab308",
            "critico": "#ef4444"
        }
        color = colores_texto.get(estado, "#888")

        # Línea de programación ideal: mostrar dias / optimo
        tiempo_optimo = None
        tiempo_alerta = None
        for key, cfg in etapas_config.items():
            if cfg.get("nombre") == etapa_nombre:
                tiempo_optimo = cfg.get("tiempo_optimo")
                tiempo_alerta = cfg.get("tiempo_alerta")
                break

        ref = tiempo_optimo if tiempo_optimo else tiempo_alerta
        if ref:
            return f'{emoji} <span style="color:{color};font-weight:bold">{dias}d</span><span style="color:#aaa;font-size:10px;">/{ref}d</span>'
        return f'{emoji} <span style="color:{color};font-weight:bold">{dias}d</span>'

    return emoji


def main():
    st.title("📊 SCRaices - Análisis de Datos")

    qe = get_query_engine()
    dm = get_data_manager()
    claude = get_claude_engine()

    # Motor de etapas
    etapas_engine = get_etapas_engine(dm)

    # Tabs principales
    tab5, tab1, tab2, tab3, tab4 = st.tabs(["🎯 Control de Etapas", "💬 Chat Inteligente", "📋 Explorar Tablas", "🔗 Relaciones", "📈 Reportes"])

    # TAB 1: Chat Inteligente con Claude - Layout de 3 paneles
    with tab1:
        # Inicializar estado
        if "current_result" not in st.session_state:
            st.session_state.current_result = None
        if "query_history" not in st.session_state:
            st.session_state.query_history = []

        # === LAYOUT DE 3 COLUMNAS ===
        col_input, col_reasoning, col_results = st.columns([1, 1, 2])

        # === COLUMNA 1: INPUT Y CONSULTA ===
        with col_input:
            st.markdown("### 💬 Consulta")

            # Input de texto
            user_query = st.text_area(
                "Escribe tu pregunta:",
                height=100,
                placeholder="Ej: ¿Cuántos proyectos hay en Temuco?",
                key="query_input"
            )

            # Botones de acción
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit_btn = st.button("🔍 Consultar", type="primary", use_container_width=True)
            with col_btn2:
                clear_btn = st.button("🗑️ Limpiar", use_container_width=True)

            if clear_btn:
                st.session_state.current_result = None
                st.session_state.query_history = []
                if claude:
                    claude.clear_history()
                st.rerun()

            # Ejemplos rápidos
            st.markdown("---")
            st.markdown("**Ejemplos:**")
            example_queries = [
                "¿Cuántos proyectos hay?",
                "Beneficiarios por comuna",
                "Proyectos en ejecución",
                "Top 10 proyectos con más beneficiarios"
            ]
            for ex in example_queries:
                if st.button(f"→ {ex}", key=f"ex_{ex}", use_container_width=True):
                    st.session_state.pending_query = ex
                    st.rerun()

            # Historial
            if st.session_state.query_history:
                st.markdown("---")
                st.markdown("**Historial:**")
                for i, h in enumerate(st.session_state.query_history[-5:]):
                    with st.expander(f"📝 {h['query'][:30]}...", expanded=False):
                        st.caption(h['query'])

            # Info de contexto
            if claude and len(claude.conversation_history) > 0:
                st.caption(f"💭 {len(claude.conversation_history)//2} consultas en contexto")

        # === COLUMNA 2: RAZONAMIENTO ===
        with col_reasoning:
            st.markdown("### 🧠 Razonamiento")

            result = st.session_state.current_result

            if result:
                # Estado de la consulta
                exito = result.get("exito", False)
                if exito:
                    st.success("✅ Consulta exitosa")
                else:
                    st.warning("⚠️ Consulta con problemas")

                # Tablas utilizadas
                tablas = result.get("tablas_usadas", [])
                if tablas:
                    st.markdown("**Tablas consultadas:**")
                    for t in tablas:
                        st.markdown(f"- `{t}`")

                # Razonamiento
                razonamiento = result.get("razonamiento", "")
                if razonamiento:
                    st.markdown("**Análisis:**")
                    st.info(razonamiento)

                # Código generado
                codigo = result.get("codigo", "")
                if codigo:
                    with st.expander("🔧 Código ejecutado", expanded=True):
                        st.code(codigo, language="python")

                # Error si hay
                if "error_ejecucion" in result:
                    st.error(f"❌ Error: {result['error_ejecucion']}")

                # Explicación
                explicacion = result.get("explicacion", "")
                if explicacion:
                    st.markdown("**Respuesta:**")
                    st.markdown(explicacion)
            else:
                st.caption("Realiza una consulta para ver el razonamiento de cómo se procesan los datos.")

                # Mostrar estructura de tablas principales
                with st.expander("📋 Estructura de datos", expanded=True):
                    st.markdown("""
                    **Tablas principales:**
                    - `Proyectos` - Información de proyectos
                    - `Beneficiario` - Datos de beneficiarios
                    - `Ejecucion` - Estado de ejecución
                    - `Levantamiento` - Datos de levantamiento
                    - `Despacho` - Información de despachos
                    - `usuarios` - Usuarios del sistema
                    """)

        # === COLUMNA 3: RESULTADOS ===
        with col_results:
            st.markdown("### 📊 Resultados")

            if result and "datos" in result:
                df = result["datos"]

                if len(df) > 0:
                    # Métricas
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Filas", len(df))
                    m2.metric("Columnas", len(df.columns))

                    # Detectar si hay columnas numéricas para mostrar suma/promedio
                    num_cols = df.select_dtypes(include=['number']).columns
                    if len(num_cols) > 0:
                        m3.metric(f"Total {num_cols[0]}", f"{df[num_cols[0]].sum():,.0f}")
                    else:
                        m3.metric("Celdas", len(df) * len(df.columns))

                    # Tabs para datos y gráfico
                    tab_data, tab_chart = st.tabs(["📋 Datos", "📈 Gráfico"])

                    with tab_data:
                        # Convertir TODAS las columnas a string para evitar errores de Arrow
                        df_display = df.head(100).copy()
                        for col in df_display.columns:
                            df_display[col] = df_display[col].fillna('').astype(str)

                        st.dataframe(df_display, height=400)

                        # Descargar
                        st.download_button(
                            "📥 Descargar CSV",
                            df.to_csv(index=False).encode('utf-8'),
                            "resultado.csv",
                            use_container_width=True
                        )

                    with tab_chart:
                        if len(df.columns) >= 2 and len(num_cols) > 0:
                            # Selector de tipo de gráfico
                            chart_type = st.selectbox(
                                "Tipo de gráfico:",
                                ["Barras", "Línea", "Pie", "Dispersión"]
                            )

                            df_chart = df.head(20)
                            x_col = df_chart.columns[0]
                            y_col = num_cols[0]

                            if chart_type == "Barras":
                                fig = px.bar(df_chart, x=x_col, y=y_col)
                            elif chart_type == "Línea":
                                fig = px.line(df_chart, x=x_col, y=y_col)
                            elif chart_type == "Pie":
                                fig = px.pie(df_chart, values=y_col, names=x_col)
                            else:
                                fig = px.scatter(df_chart, x=x_col, y=y_col)

                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No hay datos numéricos suficientes para graficar.")
                else:
                    st.warning("La consulta no retornó resultados.")
            else:
                st.caption("Los resultados de tu consulta aparecerán aquí.")

                # Placeholder visual
                st.markdown("""
                <div style="border: 2px dashed #ccc; border-radius: 10px; padding: 40px; text-align: center; color: #888;">
                    <h3>📊</h3>
                    <p>Escribe una consulta para ver los datos</p>
                </div>
                """, unsafe_allow_html=True)

        # === PROCESAR CONSULTA ===
        # Verificar si hay una consulta pendiente de los ejemplos
        pending = st.session_state.get("pending_query", None)
        if pending:
            user_query = pending
            st.session_state.pending_query = None
            submit_btn = True

        if submit_btn and user_query and claude:
            with st.spinner("🔄 Procesando consulta..."):
                result = claude.query(user_query)
                st.session_state.current_result = result
                st.session_state.query_history.append({
                    "query": user_query,
                    "result": result
                })
            st.rerun()
        elif submit_btn and not claude:
            st.error("Claude no está disponible. Verifica la API key en el archivo .env")

    # TAB 2: Explorar Tablas
    with tab2:
        st.subheader("Explorar Tablas")

        col1, col2 = st.columns([1, 3])

        with col1:
            st.markdown("### Hojas Disponibles")
            sheets = dm.available_sheets
            selected_sheet = st.selectbox(
                f"Selecciona ({len(sheets)} disponibles):",
                options=sheets
            )

        with col2:
            if selected_sheet:
                with st.spinner("Cargando..."):
                    try:
                        df = dm.get_table_data(selected_sheet)

                        m1, m2, m3 = st.columns(3)
                        m1.metric("Filas", len(df))
                        m2.metric("Columnas", len(df.columns))
                        m3.metric("Celdas", len(df) * len(df.columns))

                        # Relaciones
                        relations = dm.get_relationships_for_table(selected_sheet)
                        if relations:
                            with st.expander("🔗 Relaciones"):
                                for rel in relations:
                                    if rel["type"] == "outgoing":
                                        st.write(f"➡️ `{rel['column']}` → **{rel['references']}**")
                                    else:
                                        st.write(f"⬅️ Desde **{rel['from_table']}**")

                        # Filtros
                        with st.expander("🔧 Filtrar"):
                            filter_col = st.selectbox("Columna:", [""] + list(df.columns))
                            if filter_col:
                                unique_vals = df[filter_col].dropna().unique()[:100]
                                filter_val = st.selectbox("Valor:", [""] + list(unique_vals))
                                if filter_val:
                                    df = df[df[filter_col] == filter_val]

                        st.dataframe(df, use_container_width=True)

                        st.download_button(
                            "📥 Descargar CSV",
                            df.to_csv(index=False).encode('utf-8'),
                            f"{selected_sheet}.csv"
                        )

                    except Exception as e:
                        st.error(f"Error: {e}")

    # TAB 3: Relaciones
    with tab3:
        st.subheader("Combinar Tablas")

        col1, col2 = st.columns(2)
        with col1:
            table1 = st.selectbox("Primera tabla:", dm.available_sheets, key="t1")
        with col2:
            table2 = st.selectbox("Segunda tabla:", dm.available_sheets, key="t2")

        if st.button("🔗 Unir Tablas"):
            if table1 != table2:
                with st.spinner("Uniendo..."):
                    try:
                        joined = dm.join_tables(table1, table2)
                        st.success(f"✅ {len(joined)} filas, {len(joined.columns)} columnas")
                        st.dataframe(joined, use_container_width=True)
                        st.download_button(
                            "📥 Descargar",
                            joined.to_csv(index=False).encode('utf-8'),
                            f"{table1}_{table2}.csv"
                        )
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.divider()
        st.markdown("### Relaciones Principales")
        st.markdown(dm.get_schema_summary())

    # TAB 4: Reportes
    with tab4:
        st.subheader("Reportes")

        report = st.selectbox(
            "Tipo:",
            ["Resumen General", "Por Comuna", "Por Proyecto", "Usuarios"]
        )

        if report == "Resumen General":
            c1, c2, c3, c4 = st.columns(4)
            try:
                c1.metric("Proyectos", len(dm.get_table_data("Proyectos")))
            except Exception:
                c1.metric("Proyectos", "N/A")
            try:
                c2.metric("Beneficiarios", len(dm.get_table_data("Beneficiario")))
            except Exception:
                c2.metric("Beneficiarios", "N/A")
            try:
                c3.metric("Usuarios", len(dm.get_table_data("usuarios")))
            except Exception:
                c3.metric("Usuarios", "N/A")
            c4.metric("Hojas", len(dm.available_sheets))

        elif report == "Por Comuna":
            try:
                result = qe.group_and_count("Proyectos", "COMUNA")
                c1, c2 = st.columns(2)
                with c1:
                    st.dataframe(result)
                with c2:
                    fig = px.pie(result.head(10), values='Cantidad', names='COMUNA')
                    st.plotly_chart(fig)
            except Exception as e:
                st.error(str(e))

        elif report == "Por Proyecto":
            try:
                result = qe.group_and_count("Beneficiario", "ID_Proy")
                c1, c2 = st.columns(2)
                with c1:
                    st.dataframe(result.head(20))
                with c2:
                    fig = px.bar(result.head(15), x='ID_Proy', y='Cantidad')
                    st.plotly_chart(fig)
            except Exception as e:
                st.error(str(e))

        elif report == "Usuarios":
            try:
                usuarios = dm.get_table_data("usuarios")
                if "Rol" in usuarios.columns:
                    roles = usuarios.groupby("Rol").size().reset_index(name='Cantidad')
                    c1, c2 = st.columns(2)
                    with c1:
                        st.dataframe(usuarios)
                    with c2:
                        fig = px.pie(roles, values='Cantidad', names='Rol')
                        st.plotly_chart(fig)
                else:
                    st.dataframe(usuarios)
            except Exception as e:
                st.error(str(e))

    # TAB 5: Control de Etapas
    with tab5:
        st.subheader("Control de Etapas de Construcción")

        # Selector de proyecto y botón actualizar
        col_selector, col_btn = st.columns([3, 1])
        with col_selector:
            try:
                proyectos_df = dm.get_table_data("Proyectos")
                proyectos_options = proyectos_df[["ID_proy", "NOMBRE_PROYECTO"]].dropna()
                proyectos_options["display"] = proyectos_options["ID_proy"].astype(str) + " - " + proyectos_options["NOMBRE_PROYECTO"].astype(str)
                opciones_ids = proyectos_options["ID_proy"].tolist()
                # Default: Ñuke Mapu
                default_idx = 0
                for i, nombre in enumerate(proyectos_options["NOMBRE_PROYECTO"].tolist()):
                    if "uke" in str(nombre).lower():
                        default_idx = i
                        break
                proyecto_selected = st.selectbox(
                    "Selecciona un proyecto:",
                    options=opciones_ids,
                    index=default_idx,
                    format_func=lambda x: proyectos_options[proyectos_options["ID_proy"] == x]["display"].values[0] if x in proyectos_options["ID_proy"].values else x,
                    key="etapas_proyecto"
                )
            except Exception as e:
                st.error(f"Error cargando proyectos: {e}")
                proyecto_selected = None

        with col_btn:
            st.write("")  # Espaciador
            if st.button("🔄 Actualizar", key="refresh_etapas"):
                etapas_engine.clear_cache()
                st.rerun()

        if proyecto_selected:
            try:
                # MÉTRICAS GENERALES
                st.markdown("---")
                resumen = etapas_engine.get_resumen_proyecto(proyecto_selected)

                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total Beneficiarios", resumen["total_beneficiarios"])
                col2.metric("🟢 En Tiempo", resumen["en_tiempo"])
                col3.metric("🟡 Atención", resumen["atencion"])
                col4.metric("🔴 Críticos", resumen["criticos"])
                col5.metric("📈 Avance", f"{resumen['porcentaje_avance']:.1f}%")
                # Nota: "completados" en resumen = "despachados" (todas las etapas)

                # PANEL KANBAN DE ACCIONES
                st.markdown("---")
                st.markdown("### 📋 Panel de Acciones")

                kanban = etapas_engine.get_kanban_acciones(proyecto_selected)

                # 4 columnas Kanban
                col_ya, col_pronto, col_obra, col_ok = st.columns(4)

                def render_kanban_card(tarjeta, color_bg, color_border, columna=""):
                    """Genera HTML de una tarjeta Kanban"""
                    # Sección: etapas ya despachadas (hechas)
                    hechas_html = ""
                    etapas_desp = tarjeta.get("etapas_despachadas", [])
                    if etapas_desp:
                        items = ""
                        for ed in etapas_desp:
                            if ed["en_obra"]:
                                icono = "\U0001f528"
                                label = f'despachado ({ed["duracion"] - ed["dias"]}d rest.)'
                            else:
                                # Siempre con ? porque logística debe confirmar con obra
                                icono = "\u2753"
                                label = "confirmar"
                            items += f'<div style="font-size:11px;color:#555;">{icono} {ed["nombre"]} <span style="color:#888;">({ed["dias"]}d) \u2014 {label}</span></div>'
                        hechas_html = f'<div style="margin-top:6px;padding-top:5px;border-top:1px solid #e2e8f0;">{items}</div>'
                    # Sección: acción requerida
                    accion_html = ""
                    if tarjeta["etapa"]:
                        accion_html = (
                            f'<div style="margin-top:6px;padding:5px 8px;background:{color_border}18;border-radius:4px;">'
                            f'<span style="font-size:12px;font-weight:bold;color:{color_border};">\u27a1 SOLICITAR: {tarjeta["etapa"]}</span>'
                            f'</div>'
                        )
                    # Mensaje
                    mensaje_html = f'<div style="font-size:11px;color:#666;margin-top:4px;">{tarjeta["mensaje"]}</div>'
                    return (
                        f'<div style="background:{color_bg};border-left:4px solid {color_border};border-radius:6px;padding:10px;margin-bottom:8px;">'
                        f'<div style="font-weight:bold;font-size:14px;">{tarjeta["nombre"]}</div>'
                        f'{accion_html}'
                        f'{mensaje_html}'
                        f'{hechas_html}'
                        f'</div>'
                    )

                with col_ya:
                    st.markdown(f'<div style="background:#fef2f2;padding:8px;border-radius:8px;text-align:center;margin-bottom:10px;">'
                               f'<b>🔴 SOLICITAR YA ({len(kanban["solicitar_ya"])})</b></div>',
                               unsafe_allow_html=True)
                    if kanban["solicitar_ya"]:
                        html = ""
                        for t in kanban["solicitar_ya"]:
                            html += render_kanban_card(t, "#fef2f2", "#ef4444", "solicitar_ya")
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color:#999;text-align:center;padding:20px;">Sin urgencias</div>',
                                   unsafe_allow_html=True)

                with col_pronto:
                    st.markdown(f'<div style="background:#fefce8;padding:8px;border-radius:8px;text-align:center;margin-bottom:10px;">'
                               f'<b>🟡 SOLICITAR PRONTO ({len(kanban["solicitar_pronto"])})</b></div>',
                               unsafe_allow_html=True)
                    if kanban["solicitar_pronto"]:
                        html = ""
                        for t in kanban["solicitar_pronto"]:
                            html += render_kanban_card(t, "#fefce8", "#eab308", "solicitar_pronto")
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color:#999;text-align:center;padding:20px;">Sin pendientes</div>',
                                   unsafe_allow_html=True)

                with col_obra:
                    st.markdown(f'<div style="background:#f0f9ff;padding:8px;border-radius:8px;text-align:center;margin-bottom:10px;">'
                               f'<b>🔨 DESPACHADO ({len(kanban["en_obra"])})</b></div>',
                               unsafe_allow_html=True)
                    if kanban["en_obra"]:
                        html = ""
                        for t in kanban["en_obra"]:
                            html += render_kanban_card(t, "#f0f9ff", "#3b82f6", "en_obra")
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color:#999;text-align:center;padding:20px;">Sin obras activas</div>',
                                   unsafe_allow_html=True)

                with col_ok:
                    st.markdown(f'<div style="background:#f0fdf4;padding:8px;border-radius:8px;text-align:center;margin-bottom:10px;">'
                               f'<b>✅ TERMINADO ({len(kanban["terminado"])})</b></div>',
                               unsafe_allow_html=True)
                    if kanban["terminado"]:
                        html = ""
                        for t in kanban["terminado"]:
                            html += render_kanban_card(t, "#f0fdf4", "#22c55e", "terminado")
                        st.markdown(html, unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="color:#999;text-align:center;padding:20px;">—</div>',
                                   unsafe_allow_html=True)

                # ESTADO POR BENEFICIARIO (Matriz)
                st.markdown("---")
                st.markdown("### Estado por Beneficiario")
                st.caption("Los días en etapas despachadas indican cuántos días pasaron entre el despacho de la etapa anterior y esta. En etapas pendientes, los días efectivos esperando.")

                matriz = etapas_engine.get_matriz_estado(proyecto_selected)
                etapas_config = etapas_engine.config.get("etapas", {})
                secuencia = etapas_engine.get_secuencia_completa()

                if len(matriz) > 0:
                    # Filtro por estado
                    filtro_col1, filtro_col2 = st.columns([2, 4])
                    with filtro_col1:
                        filtro_estado = st.selectbox(
                            "Filtrar viviendas:",
                            ["Todas", "Solo atrasadas (rojo/amarillo)", "Solo críticas (rojo)"],
                            key="filtro_estado_matriz"
                        )

                    if filtro_estado != "Todas":
                        cols_etapas_temp = [c for c in matriz.columns if c not in ["ID_Benef", "Nombre"]]
                        if filtro_estado == "Solo atrasadas (rojo/amarillo)":
                            estados_filtro = {"critico", "atencion"}
                        else:
                            estados_filtro = {"critico"}
                        mask = matriz[cols_etapas_temp].apply(
                            lambda row: any(str(v).split("|")[0] in estados_filtro for v in row), axis=1
                        )
                        matriz = matriz[mask].reset_index(drop=True)
                    cols_etapas = [c for c in matriz.columns if c not in ["ID_Benef", "Nombre"]]

                    # Construir info de agrupación por dependencia
                    dep_grupos = {}  # dep_key -> [col_indices]
                    col_dep_map = {}  # col_name -> dep_key
                    for ek in secuencia:
                        cfg = etapas_config.get(ek, {})
                        nombre_col = cfg.get("nombre", ek)
                        dep = cfg.get("dependencia") or ",".join(cfg.get("dependencia_multiple", [])) or ""
                        col_dep_map[nombre_col] = dep
                        if dep not in dep_grupos:
                            dep_grupos[dep] = []
                        dep_grupos[dep].append(nombre_col)

                    # Colores de grupo para header (alternados)
                    grupo_colores = ["#1e293b", "#334155", "#1e3a5f", "#3b1e4a", "#1e3b2f", "#4a3b1e", "#1e293b"]
                    dep_color = {}
                    ci = 0
                    for dep_key, cols in dep_grupos.items():
                        if len(cols) > 1:
                            dep_color[dep_key] = grupo_colores[ci % len(grupo_colores)]
                            ci += 1

                    # Construir tabla HTML con colores y agrupación
                    html = '<table style="width:100%; border-collapse:collapse; font-size:13px;">'

                    # Fila de agrupación (spans para etapas con misma dependencia)
                    html += '<tr style="background:#0f172a; color:#94a3b8; font-size:11px;">'
                    html += '<th style="padding:4px 8px; border:1px solid #334155;"></th>'
                    already = set()
                    for col in cols_etapas:
                        dep = col_dep_map.get(col, "")
                        grupo = dep_grupos.get(dep, [col])
                        if dep and len(grupo) > 1 and dep not in already:
                            # Encontrar nombre de la dependencia
                            dep_nombre = ""
                            for ek, cfg in etapas_config.items():
                                if ek == dep:
                                    dep_nombre = cfg.get("nombre", dep)
                                    break
                            html += f'<th colspan="{len(grupo)}" style="padding:4px; border:1px solid #334155; text-align:center; background:#1e3a5f;">↳ Dependen de: {dep_nombre}</th>'
                            already.add(dep)
                        elif dep not in already or len(grupo) <= 1:
                            if dep in already:
                                continue
                            html += '<th style="padding:4px; border:1px solid #334155;"></th>'
                            already.add(dep)
                    html += '</tr>'

                    # Header con nombres de etapas
                    html += '<tr style="background:#1e293b; color:white;">'
                    html += '<th style="padding:8px; text-align:left; border:1px solid #334155; min-width:160px;">Nombre</th>'
                    for col in cols_etapas:
                        dep = col_dep_map.get(col, "")
                        grupo = dep_grupos.get(dep, [])
                        border_color = "#1e3a5f" if len(grupo) > 1 else "#334155"
                        left_border = f"3px solid {border_color}" if len(grupo) > 1 and col == grupo[0] else f"1px solid #334155"
                        right_border = f"3px solid {border_color}" if len(grupo) > 1 and col == grupo[-1] else f"1px solid #334155"
                        html += f'<th style="padding:6px 4px; text-align:center; border:1px solid #334155; border-left:{left_border}; border-right:{right_border}; font-size:11px;">{col}</th>'
                    html += '</tr>'

                    # Rows
                    for idx, row in matriz.iterrows():
                        bg = "#f8fafc" if idx % 2 == 0 else "#f1f5f9"
                        html += f'<tr style="background:{bg};">'
                        html += f'<td style="padding:6px 8px; border:1px solid #e2e8f0; font-weight:bold; white-space:nowrap;">{row["Nombre"]}</td>'
                        for col in cols_etapas:
                            dep = col_dep_map.get(col, "")
                            grupo = dep_grupos.get(dep, [])
                            cell_html = render_estado_cell_html(row[col], col, etapas_config)
                            left_border = "3px solid #cbd5e1" if len(grupo) > 1 and col == grupo[0] else "1px solid #e2e8f0"
                            right_border = "3px solid #cbd5e1" if len(grupo) > 1 and col == grupo[-1] else "1px solid #e2e8f0"
                            bg_group = "#f0f7ff" if len(grupo) > 1 and idx % 2 == 0 else ("#e8f0fe" if len(grupo) > 1 else "")
                            bg_style = f"background:{bg_group};" if bg_group else ""
                            html += f'<td style="padding:6px 4px; border:1px solid #e2e8f0; border-left:{left_border}; border-right:{right_border}; text-align:center; {bg_style}">{cell_html}</td>'
                        html += '</tr>'
                    # Fila resumen por etapa
                    html += '<tr style="background:#1e293b; color:white; font-weight:bold;">'
                    html += '<td style="padding:8px; border:1px solid #334155;">RESUMEN</td>'
                    for col in cols_etapas:
                        conteo = {"despachado": 0, "en_tiempo": 0, "atencion": 0, "critico": 0, "bloqueado": 0}
                        for _, row in matriz.iterrows():
                            estado_cell = str(row[col]).split("|")[0]
                            if estado_cell in conteo:
                                conteo[estado_cell] += 1
                        partes_resumen = []
                        if conteo["despachado"]:
                            partes_resumen.append(f'<span style="color:#3b82f6;">✅{conteo["despachado"]}</span>')
                        if conteo["en_tiempo"]:
                            partes_resumen.append(f'<span style="color:#22c55e;">🟢{conteo["en_tiempo"]}</span>')
                        if conteo["atencion"]:
                            partes_resumen.append(f'<span style="color:#eab308;">🟡{conteo["atencion"]}</span>')
                        if conteo["critico"]:
                            partes_resumen.append(f'<span style="color:#ef4444;">🔴{conteo["critico"]}</span>')
                        if conteo["bloqueado"]:
                            partes_resumen.append(f'<span style="color:#9ca3af;">⚪{conteo["bloqueado"]}</span>')
                        cell_resumen = " ".join(partes_resumen) if partes_resumen else "—"
                        html += f'<td style="padding:6px 4px; border:1px solid #334155; text-align:center; font-size:11px;">{cell_resumen}</td>'
                    html += '</tr>'

                    html += '</table>'

                    st.markdown(html, unsafe_allow_html=True)

                    # Leyenda
                    st.markdown("""
                    **Leyenda:** ✅ Despachado (días entre despachos) | 🟢 En Tiempo | 🟡 Atención | 🔴 Crítico | ⚪ Bloqueado
                    &nbsp;&nbsp;&nbsp; Los días en <span style="color:#eab308;font-weight:bold">amarillo</span> superan el tiempo óptimo · En <span style="color:#ef4444;font-weight:bold">rojo</span> superan el tiempo máximo
                    """, unsafe_allow_html=True)

                    # Detalle de despachos por beneficiario (click en nombre)
                    st.markdown("---")
                    nombres_lista = matriz["Nombre"].tolist()
                    ids_lista = matriz["ID_Benef"].tolist()

                    benef_seleccionado = st.selectbox(
                        "📋 Ver despachos de:",
                        options=range(len(nombres_lista)),
                        format_func=lambda i: nombres_lista[i],
                        key="detalle_benef"
                    )

                    if benef_seleccionado is not None:
                        id_benef_sel = ids_lista[benef_seleccionado]
                        nombre_sel = nombres_lista[benef_seleccionado]

                        despachos_benef = etapas_engine.get_despachos_beneficiario(id_benef_sel)

                        if len(despachos_benef) > 0:
                            st.markdown(f"#### Despachos de {nombre_sel}")

                            # Seleccionar columnas relevantes
                            cols_despacho = []
                            for c in ["Fecha", "Tipo_despacho", "Guia", "Observaciones", "Camion", "Chofer"]:
                                if c in despachos_benef.columns:
                                    cols_despacho.append(c)

                            df_mostrar = despachos_benef[cols_despacho].copy()

                            # Formatear fecha
                            if "Fecha" in df_mostrar.columns:
                                df_mostrar["Fecha"] = pd.to_datetime(df_mostrar["Fecha"], errors="coerce").dt.strftime("%d/%m/%Y")

                            st.dataframe(
                                df_mostrar,
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.info(f"No hay despachos registrados para {nombre_sel}")
                else:
                    st.info("No hay beneficiarios activos en este proyecto")

                # PRÓXIMOS DESPACHOS SUGERIDOS
                st.markdown("---")
                st.markdown("### 📅 Próximos Despachos Sugeridos")

                predicciones = etapas_engine.get_prediccion_despachos(proyecto_selected)

                if len(predicciones) > 0:
                    # Ocultar ID_Benef
                    cols_pred = [c for c in predicciones.columns if c != "ID_Benef"]
                    pred_display = predicciones[cols_pred].head(15)

                    # Estilizar según urgencia
                    def highlight_urgencia(row):
                        if row["Urgencia"] == "URGENTE":
                            return ["background-color: #fee2e2"] * len(row)
                        elif row["Urgencia"] == "Pronto":
                            return ["background-color: #fef9c3"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        pred_display.style.apply(highlight_urgencia, axis=1),
                        use_container_width=True,
                        hide_index=True
                    )

                    # Exportar
                    csv = predicciones.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Descargar Predicciones CSV",
                        csv,
                        f"prediccion_despachos_{proyecto_selected}.csv",
                        "text/csv"
                    )
                else:
                    st.info("No hay despachos pendientes para este proyecto")

                # REGLAS DE ETAPAS
                st.markdown("---")
                with st.expander("📐 Reglas de Etapas y Tiempos Configurados", expanded=False):
                    reglas = etapas_engine.get_reglas_etapas()

                    # Tabla de reglas
                    html_reglas = '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
                    html_reglas += '<tr style="background:#1e293b; color:white;">'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155;">Etapa</th>'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155; text-align:center;">Duración obra</th>'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155; text-align:center;">🟢→🟡 Óptimo</th>'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155; text-align:center;">🟡→🔴 Alerta</th>'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155;">Depende de</th>'
                    html_reglas += '<th style="padding:6px 8px; border:1px solid #334155; text-align:center;">Crítico</th>'
                    html_reglas += '</tr>'

                    for r in reglas:
                        critico_html = '<span style="color:#ef4444;font-weight:bold;">SÍ</span>' if r["critico"] else "No"
                        inicio_tag = ' <span style="color:#3b82f6;">(INICIO)</span>' if r["es_inicio"] else ""
                        dep = r["dependencia"] or r["dependencias_multiples"] or "—"
                        optimo = f'{r["tiempo_optimo"]} días' if r["tiempo_optimo"] else "—"
                        alerta = f'{r["tiempo_alerta"]} días' if r["tiempo_alerta"] else "—"
                        duracion = f'{r["duracion"]} días' if r["duracion"] else "—"

                        html_reglas += '<tr>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0; font-weight:bold;">{r["nombre"]}{inicio_tag}</td>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0; text-align:center;">{duracion}</td>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0; text-align:center; color:#22c55e;">{optimo}</td>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0; text-align:center; color:#ef4444;">{alerta}</td>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0;">{dep}</td>'
                        html_reglas += f'<td style="padding:5px 8px; border:1px solid #e2e8f0; text-align:center;">{critico_html}</td>'
                        html_reglas += '</tr>'

                    html_reglas += '</table>'
                    st.markdown(html_reglas, unsafe_allow_html=True)

                    st.markdown("""
                    ---
                    **¿Cómo leer esta tabla?**
                    - **Duración obra**: Tiempo estimado para ejecutar la etapa en terreno
                    - **Óptimo (🟢→🟡)**: Días máximos desde la etapa anterior para que siga en verde. Si se supera, pasa a amarillo
                    - **Alerta (🟡→🔴)**: Días máximos antes de ser crítico. Si se supera, pasa a rojo
                    - **Depende de**: La etapa que debe estar despachada antes de poder iniciar esta
                    - **Crítico**: Etapas que requieren acción inmediata si se atrasan

                    *Los tiempos se configuran en `config/etapas_config.json`*
                    """)

            except Exception as e:
                st.error(f"Error procesando datos: {e}")
                import traceback
                st.code(traceback.format_exc())


if __name__ == "__main__":
    main()

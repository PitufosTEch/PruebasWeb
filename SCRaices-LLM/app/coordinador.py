"""
Panel de Coordinador de Obras
Página independiente con vista ampliada del control de etapas
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Importar módulos locales
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_manager import DataManager
from etapas_engine import EtapasEngine

st.set_page_config(
    page_title="Coordinador de Obras - SCRaices",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def get_data_manager():
    return DataManager()


@st.cache_resource
def get_etapas_engine(_dm):
    return EtapasEngine(_dm)


def render_semaforo(estado: str) -> str:
    """Convierte estado a emoji"""
    emojis = {
        "despachado": "✅",
        "en_tiempo": "🟢",
        "atencion": "🟡",
        "critico": "🔴",
        "bloqueado": "⚪"
    }
    return emojis.get(estado, "⚪")


def get_color_estado(estado: str) -> str:
    """Obtiene color hex para un estado"""
    colores = {
        "despachado": "#3b82f6",
        "en_tiempo": "#22c55e",
        "atencion": "#eab308",
        "critico": "#ef4444",
        "bloqueado": "#9ca3af"
    }
    return colores.get(estado, "#9ca3af")


def render_alertas_view(engine: EtapasEngine, proyectos_df: pd.DataFrame, filtros: dict):
    """Vista de alertas priorizadas"""
    st.header("🔴 Alertas Críticas")

    todas_alertas = []

    # Recolectar alertas de todos los proyectos o del filtrado
    if filtros.get("proyecto"):
        proyectos_iter = [filtros["proyecto"]]
    else:
        proyectos_iter = proyectos_df["ID_proy"].tolist()

    with st.spinner("Analizando proyectos..."):
        for id_proy in proyectos_iter:
            try:
                alertas = engine.get_alertas_proyecto(id_proy)
                nombre_proy = proyectos_df[proyectos_df["ID_proy"] == id_proy]["NOMBRE_PROYECTO"].values
                nombre_proy = nombre_proy[0] if len(nombre_proy) > 0 else id_proy

                for alerta in alertas:
                    alerta["proyecto"] = nombre_proy
                    alerta["id_proy"] = id_proy
                    todas_alertas.append(alerta)
            except Exception:
                continue

    if not todas_alertas:
        st.success("✅ No hay alertas críticas en ningún proyecto")
        return

    # Ordenar por prioridad
    todas_alertas.sort(key=lambda x: (x["prioridad"], -x.get("dias_atraso", 0)))

    # Filtrar por estado si es necesario
    if filtros.get("estado") and filtros["estado"] != "Todos":
        estado_map = {"Crítico": 1, "Urgente": 2, "Atención": [3, 4]}
        prioridad_filtro = estado_map.get(filtros["estado"])
        if isinstance(prioridad_filtro, list):
            todas_alertas = [a for a in todas_alertas if a["prioridad"] in prioridad_filtro]
        elif prioridad_filtro:
            todas_alertas = [a for a in todas_alertas if a["prioridad"] == prioridad_filtro]

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    criticos = len([a for a in todas_alertas if a["prioridad"] == 1])
    urgentes = len([a for a in todas_alertas if a["prioridad"] == 2])
    atencion = len([a for a in todas_alertas if a["prioridad"] >= 3])

    col1.metric("Total Alertas", len(todas_alertas))
    col2.metric("🚨 Críticos", criticos)
    col3.metric("⚠️ Urgentes", urgentes)
    col4.metric("ℹ️ Atención", atencion)

    st.markdown("---")

    # Lista de alertas
    for alerta in todas_alertas[:50]:  # Limitar a 50
        prioridad_color = {
            1: "#ef4444",
            2: "#f97316",
            3: "#eab308",
            4: "#3b82f6"
        }.get(alerta["prioridad"], "#9ca3af")

        prioridad_emoji = {
            1: "🚨",
            2: "⚠️",
            3: "⚠️",
            4: "ℹ️"
        }.get(alerta["prioridad"], "ℹ️")

        with st.container():
            col_pri, col_info = st.columns([1, 10])
            with col_pri:
                st.markdown(f"<div style='font-size: 24px; text-align: center;'>{prioridad_emoji}</div>",
                          unsafe_allow_html=True)
            with col_info:
                st.markdown(f"**{alerta['nombre']}** - {alerta['proyecto']}")
                st.caption(f"{alerta['etapa']}: {alerta['mensaje']}")

    # Exportar
    if todas_alertas:
        df_alertas = pd.DataFrame(todas_alertas)
        csv = df_alertas.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exportar Alertas CSV",
            csv,
            f"alertas_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )


def render_proyecto_view(engine: EtapasEngine, id_proy: str, nombre_proy: str):
    """Vista detallada de un proyecto"""
    st.header(f"📊 {nombre_proy}")

    # Resumen
    resumen = engine.get_resumen_proyecto(id_proy)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total", resumen["total_beneficiarios"])
    col2.metric("🟢 En Tiempo", resumen["en_tiempo"])
    col3.metric("🟡 Atención", resumen["atencion"])
    col4.metric("🔴 Críticos", resumen["criticos"])
    col5.metric("✅ Despachados", resumen["completados"])
    col6.metric("Avance", f"{resumen['porcentaje_avance']:.1f}%")

    # Gráfico de distribución
    st.markdown("---")
    col_chart, col_progress = st.columns([1, 1])

    with col_chart:
        st.subheader("Distribución de Estados")
        datos_pie = {
            "Estado": ["En Tiempo", "Atención", "Crítico", "Despachado", "Bloqueado"],
            "Cantidad": [resumen["en_tiempo"], resumen["atencion"], resumen["criticos"],
                        resumen["completados"], resumen["bloqueados"]],
            "Color": ["#22c55e", "#eab308", "#ef4444", "#3b82f6", "#9ca3af"]
        }
        df_pie = pd.DataFrame(datos_pie)
        df_pie = df_pie[df_pie["Cantidad"] > 0]

        if len(df_pie) > 0:
            fig = px.pie(df_pie, values="Cantidad", names="Estado",
                        color="Estado",
                        color_discrete_map={
                            "En Tiempo": "#22c55e",
                            "Atención": "#eab308",
                            "Crítico": "#ef4444",
                            "Despachado": "#3b82f6",
                            "Bloqueado": "#9ca3af"
                        })
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

    with col_progress:
        st.subheader("Avance General")
        st.progress(min(1.0, resumen["porcentaje_avance"] / 100))
        st.caption(f"{resumen['porcentaje_avance']:.1f}% despachado")

        # Beneficiarios terminados vs total
        st.metric("Viviendas Terminadas",
                 f"{resumen['completados']} / {resumen['total_beneficiarios']}")

    # Matriz de estados
    st.markdown("---")
    st.subheader("Estado por Beneficiario")

    matriz = engine.get_matriz_estado(id_proy)

    if len(matriz) > 0:
        # Crear versión con emojis
        matriz_display = matriz.copy()
        cols_etapas = [c for c in matriz_display.columns if c not in ["ID_Benef", "Nombre"]]

        for col in cols_etapas:
            matriz_display[col] = matriz_display[col].apply(render_semaforo)

        # Mostrar con estilo
        st.dataframe(
            matriz_display,
            use_container_width=True,
            hide_index=True,
            height=min(600, len(matriz_display) * 35 + 50)
        )

        st.markdown("""
        **Leyenda:** ✅ Despachado | 🟢 En Tiempo | 🟡 Atención | 🔴 Crítico | ⚪ Bloqueado
        """)

        # Exportar matriz
        csv = matriz.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exportar Matriz CSV",
            csv,
            f"matriz_estado_{id_proy}.csv",
            "text/csv"
        )
    else:
        st.info("No hay beneficiarios activos en este proyecto")


def render_prediccion_view(engine: EtapasEngine, proyectos_df: pd.DataFrame, filtros: dict):
    """Vista de predicción de despachos"""
    st.header("📅 Predicción de Despachos")

    todas_predicciones = []

    # Recolectar predicciones
    if filtros.get("proyecto"):
        proyectos_iter = [filtros["proyecto"]]
    else:
        proyectos_iter = proyectos_df["ID_proy"].tolist()

    with st.spinner("Calculando predicciones..."):
        for id_proy in proyectos_iter:
            try:
                predicciones = engine.get_prediccion_despachos(id_proy)
                if len(predicciones) > 0:
                    nombre_proy = proyectos_df[proyectos_df["ID_proy"] == id_proy]["NOMBRE_PROYECTO"].values
                    nombre_proy = nombre_proy[0] if len(nombre_proy) > 0 else id_proy
                    predicciones["Proyecto"] = nombre_proy
                    predicciones["ID_Proy"] = id_proy
                    todas_predicciones.append(predicciones)
            except Exception:
                continue

    if not todas_predicciones:
        st.info("No hay despachos pendientes")
        return

    df_pred = pd.concat(todas_predicciones, ignore_index=True)

    # Filtrar por urgencia si es necesario
    if filtros.get("estado") and filtros["estado"] != "Todos":
        df_pred = df_pred[df_pred["Urgencia"] == filtros["estado"]]

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Pendientes", len(df_pred))
    col2.metric("🔴 Urgentes", len(df_pred[df_pred["Urgencia"] == "URGENTE"]))
    col3.metric("🟡 Pronto", len(df_pred[df_pred["Urgencia"] == "Pronto"]))
    col4.metric("🟢 Normal", len(df_pred[df_pred["Urgencia"] == "Normal"]))

    st.markdown("---")

    # Tabs para diferentes vistas
    tab_lista, tab_calendario = st.tabs(["📋 Lista", "📅 Calendario"])

    with tab_lista:
        # Tabla con estilos
        def highlight_urgencia(row):
            if row["Urgencia"] == "URGENTE":
                return ["background-color: #fee2e2"] * len(row)
            elif row["Urgencia"] == "Pronto":
                return ["background-color: #fef9c3"] * len(row)
            return [""] * len(row)

        cols_mostrar = ["Proyecto", "Nombre", "Etapa_Siguiente", "Fecha_Sugerida", "Urgencia"]
        if "ID_Benef" in df_pred.columns:
            cols_mostrar = ["ID_Benef"] + cols_mostrar

        st.dataframe(
            df_pred[cols_mostrar].head(100).style.apply(highlight_urgencia, axis=1),
            use_container_width=True,
            hide_index=True
        )

    with tab_calendario:
        # Vista de calendario (timeline)
        if len(df_pred) > 0:
            # Crear datos para timeline
            df_timeline = df_pred.copy()
            df_timeline["Fecha"] = pd.to_datetime(df_timeline["Fecha_Sugerida"], format="%d/%m/%Y", errors="coerce")
            df_timeline = df_timeline.dropna(subset=["Fecha"])

            if len(df_timeline) > 0:
                # Agrupar por fecha
                por_fecha = df_timeline.groupby("Fecha").agg({
                    "Nombre": "count",
                    "Urgencia": lambda x: "URGENTE" if "URGENTE" in x.values else ("Pronto" if "Pronto" in x.values else "Normal")
                }).reset_index()
                por_fecha.columns = ["Fecha", "Cantidad", "Urgencia"]

                # Gráfico de barras por fecha
                color_map = {"URGENTE": "#ef4444", "Pronto": "#eab308", "Normal": "#22c55e"}
                fig = px.bar(por_fecha.head(30), x="Fecha", y="Cantidad",
                            color="Urgencia",
                            color_discrete_map=color_map,
                            title="Despachos por Fecha Sugerida")
                fig.update_layout(xaxis_title="Fecha", yaxis_title="Cantidad de Despachos")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay fechas válidas para mostrar")

    # Exportar
    csv = df_pred.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Exportar Predicciones CSV",
        csv,
        f"predicciones_despachos_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv"
    )


def render_historico_view(engine: EtapasEngine, dm: DataManager, filtros: dict):
    """Vista de histórico de despachos"""
    st.header("📈 Histórico de Despachos")

    try:
        despachos = dm.get_table_data("Despacho")

        if "Fecha" in despachos.columns:
            despachos["Fecha"] = pd.to_datetime(despachos["Fecha"], errors="coerce")
            despachos = despachos.dropna(subset=["Fecha"])

            # Filtrar por proyecto si es necesario
            if filtros.get("proyecto"):
                despachos = despachos[despachos["ID_proy"] == filtros["proyecto"]]

            # Filtrar por fecha
            if filtros.get("fecha_desde"):
                fecha_desde = pd.to_datetime(filtros["fecha_desde"])
                despachos = despachos[despachos["Fecha"] >= fecha_desde]

            if len(despachos) == 0:
                st.info("No hay despachos en el período seleccionado")
                return

            # Métricas
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Despachos", len(despachos))

            if "Tipo_despacho" in despachos.columns:
                tipos_unicos = despachos["Tipo_despacho"].nunique()
                col2.metric("Tipos de Despacho", tipos_unicos)

            if "ID_Benef" in despachos.columns:
                benef_unicos = despachos["ID_Benef"].nunique()
                col3.metric("Beneficiarios Atendidos", benef_unicos)

            st.markdown("---")

            # Gráficos
            col_chart1, col_chart2 = st.columns(2)

            with col_chart1:
                st.subheader("Despachos por Mes")
                despachos["Mes"] = despachos["Fecha"].dt.to_period("M").astype(str)
                por_mes = despachos.groupby("Mes").size().reset_index(name="Cantidad")
                por_mes = por_mes.tail(12)  # Últimos 12 meses

                fig = px.bar(por_mes, x="Mes", y="Cantidad", title="")
                fig.update_layout(xaxis_title="Mes", yaxis_title="Despachos")
                st.plotly_chart(fig, use_container_width=True)

            with col_chart2:
                if "Tipo_despacho" in despachos.columns:
                    st.subheader("Por Tipo de Despacho")
                    por_tipo = despachos.groupby("Tipo_despacho").size().reset_index(name="Cantidad")
                    por_tipo = por_tipo.nlargest(10, "Cantidad")

                    fig = px.pie(por_tipo, values="Cantidad", names="Tipo_despacho", title="")
                    st.plotly_chart(fig, use_container_width=True)

            # Tabla de despachos recientes
            st.markdown("---")
            st.subheader("Despachos Recientes")

            cols_mostrar = ["Fecha", "ID_Benef", "ID_proy", "Tipo_despacho"]
            if "Observaciones" in despachos.columns:
                cols_mostrar.append("Observaciones")

            cols_disponibles = [c for c in cols_mostrar if c in despachos.columns]
            despachos_recientes = despachos.sort_values("Fecha", ascending=False).head(50)

            st.dataframe(
                despachos_recientes[cols_disponibles],
                use_container_width=True,
                hide_index=True
            )

    except Exception as e:
        st.error(f"Error cargando histórico: {e}")


def main():
    # Título principal
    st.title("🏗️ Panel de Coordinador de Obras")

    # Inicializar
    dm = get_data_manager()
    engine = get_etapas_engine(dm)

    # Cargar proyectos
    try:
        proyectos_df = dm.get_table_data("Proyectos")
    except Exception as e:
        st.error(f"Error cargando proyectos: {e}")
        return

    # === SIDEBAR ===
    with st.sidebar:
        st.header("⚙️ Filtros")

        # Selector de proyecto
        proyecto_options = ["Todos"] + proyectos_df["ID_proy"].tolist()
        proyecto_sel = st.selectbox(
            "Proyecto:",
            options=proyecto_options,
            format_func=lambda x: x if x == "Todos" else f"{x} - {proyectos_df[proyectos_df['ID_proy'] == x]['NOMBRE_PROYECTO'].values[0]}" if x in proyectos_df["ID_proy"].values else x
        )

        # Filtro de estado
        estado_options = ["Todos", "Crítico", "URGENTE", "Pronto", "Normal"]
        estado_sel = st.selectbox("Estado:", options=estado_options)

        # Filtro de fecha
        fecha_desde = st.date_input(
            "Desde:",
            value=datetime.now() - timedelta(days=90),
            key="fecha_desde"
        )

        st.markdown("---")

        # Navegación
        st.header("📍 Vistas")
        vista = st.radio(
            "Selecciona vista:",
            options=["🔴 Alertas", "📊 Por Proyecto", "📅 Predicción", "📈 Histórico"],
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Botón actualizar
        if st.button("🔄 Actualizar Datos", use_container_width=True):
            engine.clear_cache()
            st.cache_resource.clear()
            st.rerun()

        # Info
        st.markdown("---")
        st.caption(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")

    # Preparar filtros
    filtros = {
        "proyecto": proyecto_sel if proyecto_sel != "Todos" else None,
        "estado": estado_sel if estado_sel != "Todos" else None,
        "fecha_desde": fecha_desde
    }

    # === CONTENIDO PRINCIPAL ===
    if vista == "🔴 Alertas":
        render_alertas_view(engine, proyectos_df, filtros)

    elif vista == "📊 Por Proyecto":
        if filtros["proyecto"]:
            nombre = proyectos_df[proyectos_df["ID_proy"] == filtros["proyecto"]]["NOMBRE_PROYECTO"].values
            nombre = nombre[0] if len(nombre) > 0 else filtros["proyecto"]
            render_proyecto_view(engine, filtros["proyecto"], nombre)
        else:
            st.info("Selecciona un proyecto en el sidebar para ver el detalle")

            # Mostrar resumen de todos los proyectos
            st.subheader("Resumen General")

            resumenes = []
            for _, row in proyectos_df.iterrows():
                try:
                    res = engine.get_resumen_proyecto(row["ID_proy"])
                    res["Proyecto"] = row["NOMBRE_PROYECTO"]
                    res["ID_Proy"] = row["ID_proy"]
                    resumenes.append(res)
                except Exception:
                    continue

            if resumenes:
                df_res = pd.DataFrame(resumenes)
                cols_mostrar = ["Proyecto", "total_beneficiarios", "en_tiempo", "atencion", "criticos", "porcentaje_avance"]
                cols_rename = {
                    "total_beneficiarios": "Total",
                    "en_tiempo": "🟢",
                    "atencion": "🟡",
                    "criticos": "🔴",
                    "porcentaje_avance": "Avance %"
                }

                df_mostrar = df_res[cols_mostrar].rename(columns=cols_rename)
                df_mostrar["Avance %"] = df_mostrar["Avance %"].round(1)

                st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    elif vista == "📅 Predicción":
        render_prediccion_view(engine, proyectos_df, filtros)

    elif vista == "📈 Histórico":
        render_historico_view(engine, dm, filtros)


if __name__ == "__main__":
    main()

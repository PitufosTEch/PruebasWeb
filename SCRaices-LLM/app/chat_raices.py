"""
SCRaices Chat - Aplicación de chat con estética Raíces AppCenter

Aplicación Streamlit para consultas de datos y generación de reportes
con interfaz estilo Raíces (header oscuro, logo rojo, diseño minimalista).
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from chat_assistant import ChatAssistant, IntentType

# Configuración de página
st.set_page_config(
    page_title="SCRaices Chat",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CSS PERSONALIZADO - Estética Raíces
# ============================================================================

RAICES_CSS = """
<style>
/* ============ VARIABLES DE COLORES ============ */
:root {
    --raices-primary: #C41E3A;      /* Rojo Raíces */
    --raices-dark: #2C2C2C;         /* Header oscuro */
    --raices-sidebar: #F5F5F5;      /* Sidebar gris claro */
    --raices-white: #FFFFFF;        /* Fondo principal */
    --raices-text: #333333;         /* Texto principal */
    --raices-text-light: #666666;   /* Texto secundario */
    --raices-border: #E0E0E0;       /* Bordes */
    --raices-success: #28A745;      /* Verde éxito */
    --raices-warning: #FFC107;      /* Amarillo advertencia */
}

/* ============ HEADER PERSONALIZADO ============ */
.main-header {
    background-color: var(--raices-dark);
    padding: 1rem 1.5rem;
    margin: -1rem -1rem 1.5rem -1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    border-radius: 0;
}

.header-logo {
    color: var(--raices-primary);
    font-size: 2rem;
}

.header-title {
    color: white;
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

.header-subtitle {
    color: #AAAAAA;
    font-size: 0.85rem;
    margin: 0;
}

/* ============ OCULTAR ELEMENTOS DEFAULT ============ */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background-color: var(--raices-dark);
}

/* ============ SIDEBAR ============ */
section[data-testid="stSidebar"] {
    background-color: var(--raices-sidebar);
    border-right: 1px solid var(--raices-border);
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--raices-text);
    font-family: 'Segoe UI', system-ui, sans-serif;
}

/* ============ CHAT MESSAGES ============ */
.chat-message {
    padding: 1rem 1.25rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    max-width: 85%;
    font-family: 'Segoe UI', system-ui, sans-serif;
    line-height: 1.5;
}

.chat-message-user {
    background-color: #E3F2FD;
    border: 1px solid #BBDEFB;
    margin-left: auto;
    text-align: left;
}

.chat-message-assistant {
    background-color: white;
    border: 1px solid var(--raices-border);
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.chat-message-user::before {
    content: "👤 ";
}

.chat-message-assistant::before {
    content: "🤖 ";
}

.chat-message-error {
    background-color: #FFEBEE;
    border: 1px solid #FFCDD2;
}

/* ============ CHAT INPUT ============ */
.stTextInput > div > div > input {
    border-radius: 24px;
    border: 2px solid var(--raices-border);
    padding: 0.75rem 1.25rem;
    font-size: 1rem;
}

.stTextInput > div > div > input:focus {
    border-color: var(--raices-primary);
    box-shadow: 0 0 0 2px rgba(196, 30, 58, 0.1);
}

/* ============ BOTONES ============ */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

/* Botón primario (rojo) */
.stButton > button[kind="primary"] {
    background-color: var(--raices-primary);
    border-color: var(--raices-primary);
}

/* ============ DOWNLOAD BUTTONS ============ */
.stDownloadButton > button {
    background-color: var(--raices-success);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-weight: 500;
}

.stDownloadButton > button:hover {
    background-color: #218838;
}

/* ============ EXPANDERS ============ */
.streamlit-expanderHeader {
    background-color: var(--raices-sidebar);
    border-radius: 8px;
    font-weight: 500;
}

/* ============ DATAFRAMES ============ */
.stDataFrame {
    border-radius: 8px;
    overflow: hidden;
}

/* ============ DIVIDERS ============ */
hr {
    border: none;
    border-top: 1px solid var(--raices-border);
    margin: 1.5rem 0;
}

/* ============ INFO BOXES ============ */
.info-box {
    background-color: #E3F2FD;
    border-left: 4px solid #2196F3;
    padding: 1rem;
    border-radius: 0 8px 8px 0;
    margin: 1rem 0;
}

.success-box {
    background-color: #E8F5E9;
    border-left: 4px solid var(--raices-success);
    padding: 1rem;
    border-radius: 0 8px 8px 0;
    margin: 1rem 0;
}

/* ============ REPORT CARDS ============ */
.report-card {
    background-color: white;
    border: 1px solid var(--raices-border);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    transition: all 0.2s ease;
}

.report-card:hover {
    border-color: var(--raices-primary);
    box-shadow: 0 2px 8px rgba(196, 30, 58, 0.1);
}

.report-card-title {
    font-weight: 600;
    color: var(--raices-text);
    margin-bottom: 0.25rem;
}

.report-card-desc {
    font-size: 0.85rem;
    color: var(--raices-text-light);
}

/* ============ SPINNER ============ */
.stSpinner > div {
    border-color: var(--raices-primary) transparent transparent transparent;
}

/* ============ SCROLL AREA ============ */
.chat-container {
    max-height: 60vh;
    overflow-y: auto;
    padding-right: 0.5rem;
}

/* Custom scrollbar */
.chat-container::-webkit-scrollbar {
    width: 6px;
}

.chat-container::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
}

.chat-container::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 3px;
}

.chat-container::-webkit-scrollbar-thumb:hover {
    background: #a1a1a1;
}
</style>
"""


# ============================================================================
# INICIALIZACIÓN
# ============================================================================

@st.cache_resource
def get_assistant():
    """Singleton del asistente de chat"""
    return ChatAssistant()


def init_session_state():
    """Inicializa el estado de la sesión"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    if 'downloads' not in st.session_state:
        st.session_state.downloads = []

    if 'assistant' not in st.session_state:
        st.session_state.assistant = get_assistant()


# ============================================================================
# COMPONENTES UI
# ============================================================================

def render_header():
    """Renderiza el header personalizado"""
    st.markdown(RAICES_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="main-header">
        <span class="header-logo">🏠</span>
        <div>
            <h1 class="header-title">SCRaices Chat</h1>
            <p class="header-subtitle">Asistente inteligente para consultas y reportes</p>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    """Renderiza el sidebar con reportes disponibles y descargas"""
    with st.sidebar:
        st.markdown("### 📊 Reportes Disponibles")

        # Reportes disponibles como cards
        reportes = st.session_state.assistant.get_reportes_disponibles()

        for r in reportes:
            with st.expander(f"📋 {r['nombre']}", expanded=False):
                st.markdown(f"_{r['descripcion']}_")
                st.markdown(f"**Ejemplo:**")
                st.code(r['ejemplo'], language=None)

        st.markdown("---")

        # Sección de descargas
        st.markdown("### 📁 Descargas")

        if st.session_state.downloads:
            for download in st.session_state.downloads[-5:]:  # Últimas 5 descargas
                nombre = download['nombre']
                ruta = download['ruta']

                try:
                    with open(ruta, 'rb') as f:
                        data = f.read()

                    # Determinar tipo MIME
                    if nombre.endswith('.pdf'):
                        mime = 'application/pdf'
                        icon = "📄"
                    elif nombre.endswith('.xlsx'):
                        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        icon = "📊"
                    else:
                        mime = 'application/octet-stream'
                        icon = "📎"

                    st.download_button(
                        label=f"{icon} {nombre[:30]}...",
                        data=data,
                        file_name=nombre,
                        mime=mime,
                        key=f"dl_{nombre}_{download.get('timestamp', '')}"
                    )
                except FileNotFoundError:
                    st.warning(f"Archivo no disponible: {nombre}")
        else:
            st.info("Los reportes generados aparecerán aquí.")

        st.markdown("---")

        # Botón para limpiar conversación
        if st.button("🔄 Nueva conversación", use_container_width=True):
            st.session_state.messages = []
            st.session_state.downloads = []
            st.session_state.assistant.limpiar_historial()
            st.rerun()

        # Info de última actualización
        st.markdown("---")
        st.markdown(f"_Última actualización: {datetime.now().strftime('%H:%M')}_")


def render_chat_message(role: str, content: str, error: bool = False):
    """Renderiza un mensaje de chat"""
    if role == "user":
        css_class = "chat-message chat-message-user"
    else:
        css_class = "chat-message chat-message-assistant"
        if error:
            css_class += " chat-message-error"

    # Reemplazar saltos de línea y formatear markdown
    content_html = content.replace('\n', '<br>')

    st.markdown(f'<div class="{css_class}">{content}</div>', unsafe_allow_html=True)


def render_chat_history():
    """Renderiza el historial de chat"""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

            # Si hay datos, mostrarlos
            if msg.get("data") is not None:
                df = msg["data"]
                if isinstance(df, pd.DataFrame) and not df.empty:
                    # Mostrar todos los datos (con scroll si son muchos)
                    # Para tablas grandes, usar height para habilitar scroll
                    if len(df) > 20:
                        st.dataframe(df, use_container_width=True, height=500)
                        st.caption(f"_{len(df)} registros en total_")
                    else:
                        st.dataframe(df, use_container_width=True)


def render_welcome_message():
    """Renderiza mensaje de bienvenida si no hay historial"""
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; color: #666;">
            <h3>¡Bienvenido a SCRaices Chat!</h3>
            <p>Soy tu asistente inteligente para consultas de datos y generación de reportes.</p>
            <p><strong>Ejemplos de lo que puedo hacer:</strong></p>
        </div>
        """, unsafe_allow_html=True)

        # Ejemplos como botones
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📊 Consultar proyectos", use_container_width=True):
                process_user_input("¿Cuántos proyectos hay activos?")

        with col2:
            if st.button("📋 Generar reporte", use_container_width=True):
                st.session_state.show_report_help = True
                st.rerun()

        with col3:
            if st.button("❓ Ver ayuda", use_container_width=True):
                process_user_input("ayuda")


def process_user_input(user_input: str):
    """Procesa la entrada del usuario"""
    if not user_input.strip():
        return

    # Agregar mensaje del usuario al historial
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    # Procesar con el asistente
    with st.spinner("Pensando..."):
        response = st.session_state.assistant.procesar_mensaje(user_input)

    # Agregar respuesta al historial
    message_data = {
        "role": "assistant",
        "content": response.mensaje,
        "error": response.error
    }

    # Si hay datos, agregarlos
    if response.datos is not None:
        if isinstance(response.datos, pd.DataFrame):
            message_data["data"] = response.datos
        elif isinstance(response.datos, dict) and 'datos' in response.datos:
            message_data["data"] = response.datos['datos']

    st.session_state.messages.append(message_data)

    # Si se generó un archivo, agregarlo a descargas
    if response.archivo_generado:
        st.session_state.downloads.append({
            "nombre": response.nombre_archivo,
            "ruta": response.archivo_generado,
            "timestamp": datetime.now().strftime("%H%M%S")
        })

    st.rerun()


# ============================================================================
# APLICACIÓN PRINCIPAL
# ============================================================================

def main():
    """Función principal de la aplicación"""
    init_session_state()

    # Header
    render_header()

    # Sidebar
    render_sidebar()

    # Área principal de chat
    st.markdown("### 💬 Chat")

    # Mostrar historial o mensaje de bienvenida
    if st.session_state.messages:
        render_chat_history()
    else:
        render_welcome_message()

    # Input de chat
    st.markdown("---")

    # Usar chat_input de Streamlit
    if prompt := st.chat_input("Escribe tu consulta aquí..."):
        process_user_input(prompt)

    # Mostrar ayuda para reportes si se solicitó
    if st.session_state.get('show_report_help'):
        st.info("""
        **Para generar un reporte, usa frases como:**

        - "Resumen de beneficiario María Matus de Campesinos Esforzados"
        - "Análisis comparativo de M.O para Ñuke Mapu"
        - "Resumen de pagos M.O para Mi Nuevo Hogar"
        """)
        st.session_state.show_report_help = False


if __name__ == "__main__":
    main()

import streamlit as st
import os
import sys
from datetime import datetime

# Agregar el directorio de la aplicación al path para importaciones relativas
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

from app.agents.jira_agent import JiraAgent
from app.utils.logger import get_logger

# Configurar logger
logger = get_logger("streamlit_app")

# Título de la aplicación
st.set_page_config(
    page_title="Jira Agent",
    page_icon="🤖",
    layout="wide"
)

# Inicializar el estado de la sesión
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Mensaje de bienvenida
    st.session_state.messages.append({"role": "assistant", "content": "¡Hola! Soy tu asistente para Jira. ¿En qué puedo ayudarte hoy?"})

if "agent" not in st.session_state:
    try:
        logger.info("Inicializando agente de Jira")
        st.session_state.agent = JiraAgent()
        logger.info("Agente de Jira inicializado correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar el agente de Jira: {e}")
        st.error(f"Error al inicializar el agente: {str(e)}")
        st.stop()

# Sidebar con información
with st.sidebar:
    st.title("Jira Agent 🤖")
    st.markdown("### Asistente para gestión de issues en Jira")
    
    st.markdown("#### Ejemplos de preguntas:")
    st.markdown("- ¿Qué historias tengo asignadas?")
    st.markdown("- Agregar 2h de trabajo a PSIMDESASW-111")
    st.markdown("- ¿Cuál es el estado de PSIMDESASW-222?")
    st.markdown("- Cambiar el estado de mi historia PSIMDESASW-333")
    st.markdown("- ¿Cumplí con mis horas de ayer?")
    
    st.markdown("---")
    st.markdown(f"Fecha actual: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Botón para reiniciar la conversación
    if st.button("Nueva Conversación"):
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": "¡Hola! Soy tu asistente para Jira. ¿En qué puedo ayudarte hoy?"})
        st.success("Conversación reiniciada")
        st.rerun()

# Título principal
st.title("Agente de Jira 🤖")
st.markdown("Pregúntame sobre tus issues de Jira. Puedo ayudarte a gestionar tus tareas, registrar tiempo y cambiar estados.")

# Mostrar mensajes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Función para procesar mensajes
def process_message(message):
    # Agregar mensaje del usuario al estado
    st.session_state.messages.append({"role": "user", "content": message})
    
    # Mostrar inmediatamente el mensaje del usuario
    with st.chat_message("user"):
        st.markdown(message)
    
    # Mostrar indicador de espera
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                # Obtener respuesta del agente
                logger.info(f"Procesando mensaje: {message}")
                response = st.session_state.agent.process_message_sync(message)
                logger.info("Mensaje procesado correctamente")
                
                # Agregar respuesta del agente al estado
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Mostrar la respuesta
                st.markdown(response)
            except Exception as e:
                logger.error(f"Error al procesar mensaje: {e}")
                error_msg = f"Lo siento, ha ocurrido un error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.markdown(error_msg)

# Input para mensaje del usuario
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    process_message(prompt) 
import streamlit as st
import os
import sys
import atexit
import signal
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el directorio de la aplicación al path para importaciones relativas
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app.agents import OrchestratorAgent
from app.utils.logger import get_logger

# Configurar logger
logger = get_logger("orchestrator_app")

# Función para liberar recursos cuando se cierra la aplicación
def cleanup_resources():
    logger.info("Limpiando recursos de la aplicación...")
    try:
        if "agent" in st.session_state:
            logger.info("Cerrando el orquestador...")
            # Si el agente tiene algún método de cierre, llamarlo aquí
            agent = st.session_state.agent
            # Algunas veces es útil enviar un mensaje de despedida
            agent.process_message_sync("$__cleanup_signal__")
    except Exception as e:
        logger.error(f"Error al limpiar recursos: {e}")
    logger.info("Recursos limpiados correctamente")

# Registrar la función de limpieza para ejecutarse al salir
atexit.register(cleanup_resources)

# Manejo de señales
def signal_handler(sig, frame):
    logger.info(f"Señal recibida: {sig}. Limpiando recursos...")
    cleanup_resources()
    # Al ser un servidor web, dejamos que Streamlit maneje la salida por sí mismo

# Configurar manejadores de señales
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except (ValueError, AttributeError):
    # Ignorar errores en entornos donde no se pueden configurar señales (ej. hilos)
    logger.warning("No se pudieron configurar los manejadores de señales")

# Título de la aplicación
st.set_page_config(
    page_title="Asistente Atlassian",
    page_icon="🤖",
    layout="wide"
)

# Inicializar el estado de la sesión
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Mensaje de bienvenida
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "¡Hola! Soy tu asistente para Jira y Confluence. ¿En qué puedo ayudarte hoy?"
    })

if "agent" not in st.session_state:
    try:
        logger.info("Inicializando orquestador")
        st.session_state.agent = OrchestratorAgent()
        logger.info("Orquestador inicializado correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar el orquestador: {e}")
        st.error(f"Error al inicializar el asistente: {str(e)}")
        st.stop()

# Sidebar con información
with st.sidebar:
    st.title("Asistente Atlassian 🤖")
    st.markdown("### Asistente inteligente para Jira y Confluence")
    
    # Tabs para ejemplos de Jira y Confluence
    jira_tab, confluence_tab = st.tabs(["Ejemplos Jira", "Ejemplos Confluence"])
    
    with jira_tab:
        st.markdown("#### Ejemplos para Jira:")
        st.markdown("- ¿Qué historias tengo asignadas?")
        st.markdown("- Agregar 2h de trabajo a PSIMDESASW-111")
        st.markdown("- ¿Cuál es el estado de PSIMDESASW-222?")
        st.markdown("- Cambiar el estado de mi historia PSIMDESASW-333")
        st.markdown("- ¿Cumplí con mis horas de ayer?")
    
    with confluence_tab:
        st.markdown("#### Ejemplos para Confluence:")
        st.markdown("- Buscar páginas sobre microservicios")
        st.markdown("- ¿Qué documentación tenemos sobre AWS?")
        st.markdown("- Muestra la documentación del proyecto XYZ")
        st.markdown("- ¿Dónde encuentro información sobre el proceso de deploy?")
        st.markdown("- Crear una página nueva sobre arquitectura")
    
    st.markdown("---")
    st.markdown(f"Fecha actual: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Botón para reiniciar la conversación
    if st.button("Nueva Conversación"):
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "¡Hola! Soy tu asistente para Jira y Confluence. ¿En qué puedo ayudarte hoy?"
        })
        # También reiniciar el contexto del orquestador
        if "agent" in st.session_state:
            st.session_state.agent.context.conversation_history = []
            st.session_state.agent.context.active_agent = None
        
        st.success("Conversación reiniciada")
        st.rerun()

# Título principal
st.title("Asistente Atlassian 🤖")
st.markdown("Pregúntame sobre tus issues de Jira o tu documentación en Confluence. Puedo ayudarte con ambas plataformas.")

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
                # Obtener respuesta del orquestador
                logger.info(f"Procesando mensaje: {message}")
                response = st.session_state.agent.process_message_sync(message)
                logger.info("Mensaje procesado correctamente")
                
                # Agregar respuesta del agente al estado
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Mostrar la respuesta
                st.markdown(response)
            except KeyboardInterrupt:
                logger.warning("Procesamiento interrumpido por el usuario")
                error_msg = "El procesamiento fue interrumpido. Por favor, intenta nuevamente."
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.markdown(error_msg)
            except Exception as e:
                logger.error(f"Error al procesar mensaje: {e}")
                error_msg = f"Lo siento, ha ocurrido un error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.markdown(error_msg)

# Input para mensaje del usuario
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    process_message(prompt) 
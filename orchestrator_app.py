import streamlit as st
import os
import sys
import atexit
import signal
import locale
from datetime import datetime
from dotenv import load_dotenv

# Configurar locale para fechas en español
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Spanish')
        except locale.Error:
            print("No se pudo configurar el locale para español, usando el predeterminado.")

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
    st.title("Asistente Atlassian")
    
        
    # Utilizar el formato de fecha manual para mayor consistencia
    now = datetime.now()
    month_names = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    weekday_names = {
        0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
        4: "viernes", 5: "sábado", 6: "domingo"
    }
    
    date_human = f"{now.day} de {month_names[now.month]} de {now.year}"
    weekday = weekday_names[now.weekday()]
    st.markdown(f"Fecha actual: {weekday.capitalize()}, {date_human}")
    
    # Botón para reiniciar la conversación
    if st.button("Nueva Conversación"):
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "¡Hola! Soy tu asistente. ¿En qué puedo ayudarte hoy?"
        })
        # También reiniciar el contexto del orquestador
        if "agent" in st.session_state:
            st.session_state.agent.context.conversation_history = []
            st.session_state.agent.context.active_agent = None
        
        st.success("Conversación reiniciada")
        st.rerun()

# Título principal
st.title("Asistente Atlassian")

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
        message_placeholder = st.empty()
        with st.spinner("Pensando..."):
            try:
                # Obtener respuesta del orquestador
                logger.info(f"Procesando mensaje: {message}")
                response = st.session_state.agent.process_message_sync(message)
                logger.info("Mensaje procesado correctamente")
                
                # Agregar respuesta del agente al estado
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Mostrar la respuesta dentro del placeholder
                message_placeholder.markdown(response)
            except KeyboardInterrupt:
                logger.warning("Procesamiento interrumpido por el usuario")
                error_msg = "El procesamiento fue interrumpido. Por favor, intenta nuevamente."
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                message_placeholder.markdown(error_msg)
            except Exception as e:
                logger.error(f"Error al procesar mensaje: {e}")
                error_msg = f"Lo siento, ha ocurrido un error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                message_placeholder.markdown(error_msg)

# Input para mensaje del usuario
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    process_message(prompt) 
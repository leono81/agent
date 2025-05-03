import streamlit as st
import os
import sys
import atexit
import signal
import locale
from datetime import datetime
from dotenv import load_dotenv
import logfire
# Importar constantes de configuración
from app.config.config import KNOWLEDGE_COMMAND_PREFIX, MAX_KNOWLEDGE_LENGTH
# Importar el manejador de conocimiento
from app.utils.knowledge_manager import handle_add_knowledge

# --- Configuración de Página (Debe ser el primer comando de Streamlit) ---
st.set_page_config(
    page_title="Asistente Atlassian",
    layout="wide"
)
# ------------------------------------------------------------------------

# --- Debug Prints ---
# print(f"DEBUG: sys.executable = {sys.executable}")
# print("DEBUG: sys.path = [")
# for p in sys.path:
#     print(f"  '{p}',")
# print("]")
# --- End Debug Prints ---

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

# Añadir el directorio raíz del proyecto al sys.path
# Esto permite importaciones como 'from app.agents...' independientemente de cómo se ejecute
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..')) # Asume que orchestrator_app está en una subcarpeta (como 'app') o en la raíz
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Importar OrchestratorAgent y SharedContext desde orchestrator_agent.py
from app.agents.orchestrator_agent import OrchestratorAgent, SharedContext
# from app.agents.models import SharedContext # <-- Corrección: Ya no se importa de models.py
from app.utils.indexing import update_vector_store # <-- Importar la función de indexación
from app.utils.logger import get_logger

# Configurar logger
logger = get_logger("orchestrator_app")

# Configurar Logfire
try:
    logfire.configure()
    logfire.info("Logfire configurado para orchestrator_app.")
except Exception as e:
    st.warning(f"No se pudo configurar Logfire: {e}") # ¡Ojo! Esto es un comando st.
    logfire.info(f"Logfire no configurado: {e}") # Log localmente si falla

# --- Indexación de la Base de Conocimientos (se ejecuta solo una vez por sesión de Streamlit) ---
@st.cache_resource(show_spinner="Actualizando base de conocimientos si es necesario...")
def run_initial_indexing():
    """Ejecuta la indexación al inicio, cacheado por sesión."""
    try:
        update_vector_store() # Llama a la función que comprueba y actualiza si hay cambios
        return True # Indicar éxito
    except Exception as e:
        # No usar st.error aquí directamente para evitar el problema de set_page_config
        logger.error(f"Error en run_initial_indexing: {e}", exc_info=True)
        # Devolver el error para mostrarlo después de set_page_config
        return e

indexing_result = run_initial_indexing()

# --- Manejo de Errores de Indexación (Mostrar después de set_page_config) ---
if isinstance(indexing_result, Exception):
    st.error(f"Error durante la indexación inicial de la base de conocimientos: {indexing_result}")
    # Opcionalmente, detener la app si la indexación es crítica
    # st.stop()
elif not indexing_result:
     # Podría haber otros casos donde devuelva False o None si la lógica cambia
     st.warning("La indexación inicial no se completó o fue omitida.")

# Función para liberar recursos cuando se cierra la aplicación
def cleanup_resources():
    logger.info("Limpiando recursos de la aplicación...")
    try:
        if 'orchestrator' in st.session_state:
            logger.info("Cerrando el orquestador...")
            # Si el agente tiene algún método de cierre, llamarlo aquí
            agent = st.session_state.orchestrator
            # Algunas veces es útil enviar un mensaje de despedida
            # agent.process_message_sync("$__cleanup_signal__") # Descomentar si es necesario
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


# Inicializar el estado de la sesión para mensajes
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Mensaje de bienvenida inicial
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "¡Hola! Soy tu asistente para Jira y Confluence. ¿En qué puedo ayudarte hoy?"
    })

# --- Inicialización del Agente Orquestador ---
# Usar st.session_state para mantener la instancia del agente entre recargas de la UI
if 'orchestrator' not in st.session_state:
    try:
        # Crear el contexto compartido primero (NO SE PASA AL CONSTRUCTOR)
        # shared_context = SharedContext() # El agente lo crea internamente
        st.session_state.orchestrator = OrchestratorAgent() # No pasar 'context'
        logfire.info("Nueva instancia de OrchestratorAgent creada y guardada en session_state.")
        # No reiniciar mensajes aquí si ya existe la clave 'messages'
        if "messages" not in st.session_state or not st.session_state.messages:
             st.session_state.messages = [] # Inicializar historial de chat si es necesario
             st.session_state.messages.append({ # Añadir bienvenida si se reinicia
                 "role": "assistant",
                 "content": "¡Hola! Bienvenido de nuevo."
             })
        st.info("Agente Orquestador inicializado.") # Mensaje para el usuario
    except Exception as e:
        logger.error(f"Error CRÍTICO al inicializar el orquestador: {e}", exc_info=True)
        st.error(f"Error CRÍTICO al inicializar el asistente: {e}. La aplicación no puede continuar.")
        st.stop() # Detener la app si el agente no se puede crear

orchestrator: OrchestratorAgent = st.session_state.orchestrator


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
        # Limpiar mensajes
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "¡Hola! Soy tu asistente. ¿En qué puedo ayudarte hoy?"
        })
        
        # Recrear el orquestador para asegurar un estado limpio del contexto interno
        try:
            # shared_context = SharedContext() # No es necesario crearla aquí
            st.session_state.orchestrator = OrchestratorAgent() # Recrear sin pasar contexto
            st.success("Conversación reiniciada")
        except Exception as e:
             logger.error(f"Error al reiniciar el orquestador: {e}", exc_info=True)
             st.error(f"Error al reiniciar el asistente: {e}")
        
        st.rerun()

# Título principal
st.title("🤖 Asistente Atlassian con RAG")

# Mostrar mensajes
# Asegurarse de que messages existe antes de iterar
if "messages" in st.session_state:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
else:
    st.warning("Historial de mensajes no inicializado.")

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
                # Usar el agente persistido en session_state
                response = orchestrator.process_message_sync(message) 
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
if prompt := st.chat_input("¿En qué puedo ayudarte hoy? (Jira, Confluence, Incidentes...)"):
    # Limpiar espacios en blanco al inicio/final
    user_input = prompt.strip()

    # Comprobar si es un comando para añadir conocimiento
    if user_input.startswith(KNOWLEDGE_COMMAND_PREFIX):
        knowledge_to_add = user_input[len(KNOWLEDGE_COMMAND_PREFIX):].strip()

        # Validar que el texto no esté vacío
        if not knowledge_to_add:
            st.chat_message("assistant").error("El comando para recordar está vacío. Debes proporcionar el texto después del prefijo.")
            # Añadir mensaje de error al historial
            st.session_state.messages.append({
                "role": "assistant",
                "content": "El comando para recordar estaba vacío. Por favor, incluye el texto a recordar después del prefijo."
            })
        # Validar longitud máxima
        elif len(knowledge_to_add) > MAX_KNOWLEDGE_LENGTH:
             error_msg = f"El texto a recordar es demasiado largo ({len(knowledge_to_add)} caracteres). El máximo permitido es {MAX_KNOWLEDGE_LENGTH}."
             st.chat_message("assistant").error(error_msg)
             # Añadir mensaje de error al historial
             st.session_state.messages.append({
                 "role": "assistant",
                 "content": error_msg
             })
        else:
            # Llamar a la función para manejar la adición de conocimiento
            # Mostrar mensaje del usuario en el chat
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            # Llamar a la función que manejará el guardado y reindexado
            handle_add_knowledge(knowledge_to_add)
            # Detener el flujo normal (no enviar al orquestador)
            # st.stop() # st.stop() puede ser problemático, es mejor solo no llamar a process_message

    else:
        # Si no es el comando, procesar normalmente con el orquestador
        process_message(user_input) # Usar user_input que ya está sin espacios extra

# Mostrar estado de indexación (ya no es necesario si se maneja arriba)
# if not indexing_successful:
#     st.error("Hubo un problema al inicializar/actualizar la base de conocimientos. Las funciones RAG pueden no funcionar correctamente.") 
import streamlit as st
import datetime

def initialize_session_state():
    """Inicializa el estado de la sesión en Streamlit si es necesario para la UI general."""
    # Clave general para mensajes de chat
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant",
            "content": "¡Hola! ¿En qué puedo ayudarte hoy?" # Mensaje de bienvenida genérico
        })

    # Claves específicas del flujo de incidentes (si se usan globalmente, mantenerlas aquí)
    # Si solo se usan en el agente de incidentes, podrían moverse allí.
    if "current_step" not in st.session_state:
        st.session_state.current_step = 0
            
    if "collected_data" not in st.session_state:
        st.session_state.collected_data = {}
        # Agregar la fecha del incidente automáticamente
        # Considera si esto debe estar aquí o solo en el contexto del incidente
        # st.session_state.collected_data["fecha_incidente"] = datetime.date.today().strftime("%Y-%m-%d")
            
    if "temp_list_items" not in st.session_state:
        st.session_state.temp_list_items = []
        
    if "confirmation_step" not in st.session_state:
         st.session_state.confirmation_step = False

    if "process_completed" not in st.session_state:
        st.session_state.process_completed = False

    # Clave para el contexto compartido entre agentes
    if "shared_context" not in st.session_state:
        # La inicialización real de SharedContext se hace en la app principal
        # Aquí solo aseguramos que la clave existe si se accede antes
        # st.session_state.shared_context = None # O {} o lo que sea apropiado
        pass # Es mejor inicializarlo donde se crea la instancia

    # Puedes añadir otras claves de session_state que necesites inicializar globalmente
    # Ejemplo:
    # if 'user_authenticated' not in st.session_state:
    #     st.session_state.user_authenticated = False

    # print("DEBUG: Session state initialized/verified by ui_utils.")

def display_messages(messages: list):
    """Muestra una lista de mensajes en la interfaz de Streamlit."""
    if not messages:
        st.info("No hay mensajes para mostrar.")
        return

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role and content:
            with st.chat_message(role):
                st.markdown(content)
        else:
            # Podría ser útil loguear mensajes mal formados
            print(f"Advertencia: Mensaje mal formado encontrado: {message}")

# Aquí añadiremos display_messages después 
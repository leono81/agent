import streamlit as st
from app.agents import ConfluenceAgent
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Título de la app
st.title("Asistente de Documentación Confluence")

# Inicializar el agente (solo una vez)
@st.cache_resource
def get_agent():
    return ConfluenceAgent()

agent = get_agent()

# Inicializar el historial de chat si no existe
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar mensajes anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input del usuario
query = st.chat_input("¿Qué quieres saber?")

if query:
    # Agregar mensaje del usuario al historial
    st.session_state.messages.append({"role": "user", "content": query})
    
    # Mostrar mensaje del usuario
    with st.chat_message("user"):
        st.markdown(query)
    
    # Mostrar pensando...
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Buscando información...")
        
        # Obtener respuesta del agente
        response = agent.process_message_sync(query)
        
        # Actualizar con la respuesta
        message_placeholder.markdown(response)
    
    # Agregar respuesta al historial
    st.session_state.messages.append({"role": "assistant", "content": response})
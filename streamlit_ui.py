# streamlit_ui.py
import streamlit as st
import asyncio
import os
import sys
from typing import List, Dict, Any, cast

# Añadir ruta del proyecto para importar módulos locales
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Importar la lógica principal del agente y tipos de mensaje
# (Asegúrate que estas rutas sean correctas respecto a streamlit_ui.py)
try:
    from jira_agent.jira_tool_agent import run_jira_conversation
    # Usaremos Any para el historial por simplicidad en Streamlit,
    # aunque internamente sean ModelMessage. Opcional: importar ModelMessage si prefieres tipado estricto.
    # from pydantic_ai.messages import ModelMessage
except ImportError as e:
    st.error(f"Error al importar el agente: {e}. Asegúrate de ejecutar Streamlit desde el directorio raíz 'jira_issue_manager' y que la estructura de carpetas sea correcta.")
    st.stop() # Detener la app si no se puede importar el agente

# --- Configuración de la Página Streamlit ---
st.set_page_config(
    page_title="Agente de Jira",
    page_icon=" conversación",
    layout="wide"
)

st.title("💬 Jira Assistant Chat")
st.caption("Interactúa con tu instancia de Jira de forma conversacional.")

# --- Inicialización del Historial de Chat ---
# Usamos st.session_state para mantener el historial entre recargas de la app
if "messages" not in st.session_state:
    # El historial almacenará diccionarios simples para fácil visualización en Streamlit
    # Cada diccionario tendrá 'role' ('user' o 'assistant') y 'content' (string)
    st.session_state.messages = []
if "internal_history" not in st.session_state:
     # Almacenamos aquí el historial interno de Pydantic AI (objetos ModelMessage)
     st.session_state.internal_history = [] # List[Any] o List[ModelMessage]

# --- Mostrar Mensajes Anteriores ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Input del Usuario ---
if prompt := st.chat_input("Pregúntale algo a Jira Assistant..."):
    # Añadir mensaje del usuario al historial visible y mostrarlo
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # --- Llamar al Agente ---
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Pensando...")

        try:
            # Ejecutar la lógica de la conversación ASÍNCRONA
            # Pasamos el historial INTERNO de Pydantic AI
            new_internal_messages, agent_response_text = asyncio.run(
                run_jira_conversation(prompt, st.session_state.internal_history)
            )

            # Actualizar el historial interno con los nuevos mensajes de esta ronda
            st.session_state.internal_history.extend(new_internal_messages)

            # Mostrar la respuesta del agente
            message_placeholder.markdown(agent_response_text)
            # Añadir respuesta del agente al historial visible
            st.session_state.messages.append({"role": "assistant", "content": agent_response_text})

        except ValueError as ve:
            # Errores esperados (ej. credenciales faltantes)
            error_msg = f"Error de configuración o valor: {ve}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except ImportError as ie:
             # Si hay error de importación al correr (menos probable aquí)
             error_msg = f"Error de importación: {ie}"
             st.error(error_msg)
             st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            # Otros errores inesperados
            error_msg = f"Ocurrió un error inesperado: {e}"
            st.exception(e) # Muestra el traceback en Streamlit
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

# --- Botón para Limpiar Historial (Opcional) ---
if st.button("Limpiar Conversación"):
    st.session_state.messages = []
    st.session_state.internal_history = []
    st.rerun() # Recargar la página para reflejar el cambio
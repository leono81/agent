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
    from pydantic_ai.messages import ModelMessage
except ImportError as e:
    st.error(f"Error al importar el agente: {e}. Asegúrate de ejecutar Streamlit desde el directorio raíz 'jira_issue_manager' y que la estructura de carpetas sea correcta.")
    st.stop() # Detener la app si no se puede importar el agente

# --- Configuración de la Página Streamlit ---
st.set_page_config(
    page_title="Asistente de Jira",
    page_icon=" conversation", # Puedes cambiar el emoji
    layout="wide"
)

st.title("💬 Asistente de Jira ")
st.caption("Interactúa con tu instancia de Jira de forma conversacional.")

# --- Inicialización del Historial de Chat ---
if "messages" not in st.session_state:
    # Historial para mostrar en la UI (diccionarios)
    st.session_state.messages = []
if "internal_history" not in st.session_state:
     # Historial para Pydantic AI (objetos ModelMessage)
     st.session_state.internal_history = [] # Inicialmente List[Any] o List[ModelMessage]

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
            # Asegurarnos que el historial interno es del tipo correcto si usamos tipado estricto
            internal_history_typed: List[ModelMessage] = cast(List[ModelMessage], st.session_state.internal_history)

            # Necesitamos ejecutar la corutina en un event loop
            # Streamlit < 1.17 : asyncio.run() funciona
            # Streamlit >= 1.17: Mejor usar asyncio.new_event_loop() y run_in_executor o st.spinner
            # Por simplicidad ahora, usamos asyncio.run()
            try:
                 # Intenta obtener el loop existente de Streamlit si es posible
                 loop = asyncio.get_running_loop()
            except RuntimeError:
                 # Si no hay loop, crea uno nuevo (puede pasar al ejecutar script directamente)
                 loop = asyncio.new_event_loop()
                 asyncio.set_event_loop(loop)

            # Ejecuta la corutina
            new_internal_messages, agent_response_text = loop.run_until_complete(
                 run_jira_conversation(prompt, internal_history_typed)
            )


            # Actualizar el historial interno con los nuevos mensajes de esta ronda
            st.session_state.internal_history.extend(new_internal_messages)

            # Mostrar la respuesta del agente
            message_placeholder.markdown(agent_response_text)
            # Añadir respuesta del agente al historial visible
            st.session_state.messages.append({"role": "assistant", "content": agent_response_text})

        except ValueError as ve:
            error_msg = f"Error de configuración o valor: {ve}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except ImportError as ie:
             error_msg = f"Error de importación: {ie}"
             st.error(error_msg)
             st.session_state.messages.append({"role": "assistant", "content": error_msg})
        except Exception as e:
            error_msg = f"Ocurrió un error inesperado durante la conversación."
            st.error(error_msg)
            st.exception(e) # Muestra el traceback en Streamlit para depuración
            # Añadir mensaje genérico al historial visible
            st.session_state.messages.append({"role": "assistant", "content": "Lo siento, ocurrió un error procesando tu solicitud."})
            # Loguear el error detallado si tenemos el logger configurado aquí también
            # (Opcional: importar y usar setup_logger aquí)
            # logger = setup_logger("streamlit_ui")
            # logger.exception("Error en la interfaz Streamlit")


# --- Botón para Limpiar Historial (Opcional) ---
st.sidebar.title("Opciones")
if st.sidebar.button("Limpiar Conversación"):
    st.session_state.messages = []
    st.session_state.internal_history = []
    st.rerun() # Recargar la página para reflejar el cambio
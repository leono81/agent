import os
import streamlit as st
from datetime import datetime

from app.utils.indexing import update_vector_store, KNOWLEDGE_BASE_DIR
from app.utils.logger import get_logger

logger = get_logger(__name__)

def handle_add_knowledge(knowledge_text: str):
    """
    Procesa un fragmento de texto proporcionado por el usuario para añadirlo
    a la base de conocimientos.

    Pasos:
    1. Genera un nombre de archivo único basado en timestamp.
    2. Guarda el `knowledge_text` en un nuevo archivo `.txt` dentro del directorio
       `KNOWLEDGE_BASE_DIR` (definido en `app.utils.indexing`).
    3. Dispara una reindexación completa de la base de conocimientos llamando a
       `update_vector_store(force_reindex=True)`.
    4. Muestra feedback al usuario en la interfaz de Streamlit (spinner,
       mensajes de éxito/error) y actualiza el historial de chat.
    5. Maneja errores durante la escritura del archivo o la reindexación.

    Args:
        knowledge_text: El texto limpio (sin el prefijo) que el usuario desea añadir.
    """
    logger.info(f"Intentando añadir nuevo conocimiento: '{knowledge_text[:50]}...'") # Loguea el inicio

    try:
        # Generar Nombre de Archivo único
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S_%f') # Añadir microsegundos para mayor unicidad
        filename = f"user_added_{timestamp}.txt"
        file_path = os.path.join(KNOWLEDGE_BASE_DIR, filename)
        
        # Asegurarse de que el directorio knowledge_base existe
        os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)

        logger.info(f"Guardando conocimiento en: {file_path}")
        # Guardar Archivo
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(knowledge_text)
        logger.info(f"Nuevo conocimiento guardado en: {file_path}")

    except IOError as e:
        error_msg = f"Error al guardar la información en {file_path}: {e}"
        logger.error(error_msg, exc_info=True)
        st.chat_message("assistant").error(f"❌ Lo siento, hubo un problema al guardar tu información: {e}")
        # Añadir mensaje de error al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ Lo siento, hubo un problema al guardar tu información: {e}"
        })
        return # Detener si no se pudo guardar

    # Disparar Reindexación
    logger.info("Archivo guardado, iniciando reindexación forzada...")
    try:
        with st.spinner("🧠 Actualizando mi base de conocimientos..."):
            # Llamar a la función de indexación forzando la ejecución
            update_vector_store(force_reindex=True)
        
        success_msg = "✅ ¡Información guardada y añadida a mi conocimiento!"
        logger.info(success_msg)
        st.chat_message("assistant").success(success_msg)
        # Añadir mensaje de éxito al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": success_msg
        })

    except Exception as e:
        error_msg = f"Se guardó la información en {filename}, pero falló la actualización de la base de conocimientos: {e}"
        logger.error(error_msg, exc_info=True)
        st.chat_message("assistant").error(f"⚠️ {error_msg}")
        # Añadir mensaje de error al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"⚠️ {error_msg}"
        }) 
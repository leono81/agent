import os
import streamlit as st
from datetime import datetime
import logfire

from app.utils.indexing import update_vector_store, KNOWLEDGE_BASE_DIR
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Configurar Logfire (opcional, pero útil para seguimiento)
try:
    # Podrías querer usar la misma configuración que en otros módulos
    logfire.configure(send_to_logfire=False) 
    logfire.info(f"Logfire configurado para {__name__}")
except Exception as e:
    logger.warning(f"No se pudo configurar Logfire en {__name__}: {e}")


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
    logfire.info(f"Intentando añadir nuevo conocimiento: '{knowledge_text[:50]}...'") # Loguea el inicio

    try:
        # Generar Nombre de Archivo único
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S_%f') # Añadir microsegundos para mayor unicidad
        filename = f"user_added_{timestamp}.txt"
        file_path = os.path.join(KNOWLEDGE_BASE_DIR, filename)
        
        # Asegurarse de que el directorio knowledge_base existe
        os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)

        logfire.info(f"Guardando conocimiento en: {file_path}")
        # Guardar Archivo
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(knowledge_text)
        logger.info(f"Nuevo conocimiento guardado en: {file_path}")

    except IOError as e:
        error_msg = f"Error al guardar la información en {file_path}: {e}"
        logger.error(error_msg, exc_info=True)
        logfire.error(error_msg, exc_info=True)
        st.chat_message("assistant").error(f"❌ Lo siento, hubo un problema al guardar tu información: {e}")
        # Añadir mensaje de error al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ Lo siento, hubo un problema al guardar tu información: {e}"
        })
        return # Detener si no se pudo guardar

    # Disparar Reindexación
    logfire.info("Archivo guardado, iniciando reindexación forzada...")
    try:
        with st.spinner("🧠 Actualizando mi base de conocimientos..."):
            # Llamar a la función de indexación forzando la ejecución
            update_vector_store(force_reindex=True)
        
        success_msg = "✅ ¡Información guardada y añadida a mi conocimiento!"
        logger.info(success_msg)
        logfire.info("Reindexación completada exitosamente.")
        st.chat_message("assistant").success(success_msg)
        # Añadir mensaje de éxito al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": success_msg
        })

    except Exception as e:
        error_msg = f"Se guardó la información en {filename}, pero falló la actualización de la base de conocimientos: {e}"
        logger.error(error_msg, exc_info=True)
        logfire.error(f"Error durante la reindexación forzada: {e}", exc_info=True)
        st.chat_message("assistant").error(f"⚠️ {error_msg}")
        # Añadir mensaje de error al historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"⚠️ {error_msg}"
        }) 
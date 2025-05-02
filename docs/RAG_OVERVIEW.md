# ¿Qué es RAG y cómo ayuda al Asistente Atlassian?

## ¿Qué es RAG?

RAG son las siglas de "Retrieval-Augmented Generation" (Generación Aumentada por Recuperación).

Imagina que el asistente (el LLM o IA que responde tus preguntas) tiene su conocimiento "interno" general, pero no sabe detalles específicos de *nuestro* proyecto, como qué significan nuestras siglas internas, cuáles son nuestros proyectos clave en Jira, o cómo son nuestros procedimientos habituales.

RAG es como darle al asistente acceso a una **base de datos de conocimiento local** (una especie de "memoria externa" o "apuntes") donde podemos guardar toda esa información específica.

Cuando haces una pregunta, el asistente, antes de responder:

1.  **Busca (Recupera):** Consulta rápidamente en su base de datos local si hay información relevante para tu pregunta.
2.  **Aumenta:** Añade la información relevante que encontró a tu pregunta original.
3.  **Genera:** Usa su inteligencia general *más* la información específica recuperada para darte una respuesta mucho más precisa y contextualizada.

## ¿Cómo se implementa aquí?

*   **Base de Conocimiento:** Tenemos una carpeta llamada `knowledge_base/`. Aquí ponemos archivos de texto (preferentemente Markdown, `.md`) con la información que queremos que el asistente "aprenda" (ej: definiciones de proyectos, acrónimos, pasos de procesos).
*   **"Cerebro" de Búsqueda Local:** Usamos una herramienta llamada ChromaDB para crear una base de datos especial (en la carpeta `vector_store_db/`) que permite buscar muy rápido en el contenido de `knowledge_base/` por significado, no solo por palabras exactas.
*   **Indexación Automática:** Cada vez que inicias la aplicación (`python app.py`), el sistema **comprueba automáticamente** si los archivos en `knowledge_base/` han cambiado. Si es así, actualiza el "cerebro" de búsqueda de ChromaDB. ¡Ya no necesitas ejecutar un script manualmente cada vez!
*   **Indexación Manual (Forzada):** Si por alguna razón necesitas *forzar* la reconstrucción del índice, puedes usar el script `python index_knowledge.py --force`.
*   **Integración en Agentes:** Por ahora, el agente de Jira (`JiraAgent`) es el que usa RAG. Cuando le haces una pregunta, busca en ChromaDB, obtiene el contexto relevante y se lo pasa al LLM junto con tu pregunta.

## Beneficios

*   **Respuestas más precisas:** El asistente entiende mejor el contexto específico de nuestros proyectos.
*   **Menos errores:** Evita malinterpretar siglas o procesos internos.
*   **Actualizable:** Podemos añadir o modificar conocimiento fácilmente actualizando los archivos en `knowledge_base/`. La próxima vez que inicies la app, los cambios se indexarán automáticamente.

## Pasos para Usar/Actualizar RAG

1.  **Activar Entorno Virtual:** Asegúrate de tener el entorno `venv` activo en tu terminal:
    ```bash
    source venv/bin/activate
    ```
2.  **Instalar Dependencias:** Si es la primera vez o si cambian los requisitos:
    ```bash
    # Puede ser necesario --break-system-packages en algunos sistemas Linux
    pip install -r requirements.txt
    ```
3.  **Añadir/Editar Conocimiento:** Modifica o añade archivos `.md` o `.txt` en la carpeta `knowledge_base/`.
4.  **Ejecutar la Aplicación:** Lanza el asistente como de costumbre (mientras el `venv` está activo):
    ```bash
    python app.py
    ```
    *La aplicación detectará los cambios en `knowledge_base/` y reindexará automáticamente si es necesario.*
5.  **(Opcional) Forzar Reindexación Manual:** Si necesitas reconstruir el índice explícitamente:
    ```bash
    python index_knowledge.py --force
    ```

# Detalles Técnicos de la Implementación RAG (Retrieval-Augmented Generation)

## 1. Visión General y Enfoque

Se ha implementado un sistema RAG local para enriquecer el contexto de los agentes (inicialmente `JiraAgent`) con conocimiento específico del proyecto o dominio, almacenado en archivos locales. El objetivo es mejorar la precisión y relevancia de las respuestas sin depender de entrenamiento adicional del LLM.

El enfoque elegido prioriza la ejecución local, la velocidad y el bajo coste:

*   **Vector Store:** ChromaDB (local, basado en archivos).
*   **Embeddings:** SentenceTransformers (`all-MiniLM-L6-v2`) ejecutándose localmente.
*   **Orquestación:** LangChain para la carga, división, indexación y recuperación de documentos.

## 2. Dependencias Añadidas

Se añadieron las siguientes librerías a `requirements.txt`:

```
# RAG Dependencies
langchain>=0.1.0
langchain-openai>=0.1.0
langchain-community>=0.0.20 # Para loaders/vectorstores iniciales (aunque ahora usamos paquetes específicos)
chromadb>=0.4.0
sentence-transformers>=2.2.0
# Updated RAG packages for deprecation warnings
langchain-chroma>=0.1.0 # Reemplazo community Chroma
langchain-huggingface>=0.0.3 # Reemplazo community HF Embeddings
```

*(Nota: Se añadieron `langchain-chroma` y `langchain-huggingface` para resolver warnings de deprecación y usar los paquetes más actualizados).*

## 3. Estructura de Directorios

*   `knowledge_base/`: Contiene los archivos de texto (preferentemente Markdown `.md`) con la información que servirá como base de conocimiento.
*   `vector_store_db/`: Almacena la base de datos vectorial creada por ChromaDB. **Importante:** Este directorio está añadido a `.gitignore` para no incluir la DB en el control de versiones.
*   `app/utils/indexing.py`: Contiene la lógica principal de indexación.
*   `index_knowledge.py`: Script wrapper para llamar a la indexación manual forzada.

## 4. Proceso de Indexación (`app/utils/indexing.py`, `orchestrator_app.py`, `index_knowledge.py`)

La lógica principal de indexación reside en la función `update_vector_store` dentro de `app/utils/indexing.py`.

**Pasos Clave en `update_vector_store`:**

1.  **Comprobación de Cambios:** Antes de indexar, la función `_should_reindex` compara la fecha de última modificación del directorio `VECTOR_STORE_DIR` con la fecha de última modificación de los archivos `.md`/`.txt` en `KNOWLEDGE_BASE_DIR`. La indexación solo procede si hay cambios o si el `VECTOR_STORE_DIR` no existe.
2.  **Carga:** Usa `DirectoryLoader` de LangChain para cargar todos los archivos `.md`/`.txt` desde `KNOWLEDGE_BASE_DIR`.
3.  **División:** Usa `RecursiveCharacterTextSplitter` para dividir los documentos en chunks.
4.  **Embeddings:** Inicializa `HuggingFaceEmbeddings` (usando el modelo `EMBEDDING_MODEL`).
5.  **Almacenamiento:** Crea/sobrescribe la base de datos `Chroma` usando los embeddings y los chunks, especificando `persist_directory=VECTOR_STORE_DIR`.

**Ejecución:**

*   **Automática (al inicio):** La función `update_vector_store` es llamada desde `orchestrator_app.py` al inicio de la ejecución de Streamlit, envuelta en `@st.cache_resource`. Esto asegura que la comprobación y la posible reindexación ocurran una vez por sesión, solo si es necesario.
*   **Manual (Forzada):** El script `index_knowledge.py` actúa como un simple wrapper que llama a `update_vector_store` con el argumento `force_reindex=True` si se le pasa la bandera `--force`:
    ```bash
    # Activar venv si no lo está
    # source venv/bin/activate
    python index_knowledge.py --force
    ```
    Esto es útil para forzar una reconstrucción completa del índice.

## 5. Integración en Agentes (`JiraAgent`)

La lógica RAG se ha integrado en `app/agents/jira_agent.py`:

1.  **Inicialización (`__init__`)**:
    *   Se cargan las configuraciones (`VECTOR_STORE_DIR`, `EMBEDDING_MODEL`) necesarias para cargar el retriever.
    *   Se inicializa `HuggingFaceEmbeddings`.
    *   Se carga la base de datos `Chroma` desde `VECTOR_STORE_DIR` usando los embeddings.
    *   Se crea un `retriever` a partir del vector store (`self.retriever = vector_store.as_retriever(...)`). Se configuran `search_kwargs={'k': 2}` para recuperar los 2 chunks más relevantes.
    *   Se manejan posibles errores durante la inicialización para que el agente pueda funcionar (sin RAG) si la DB no existe o falla la carga.

2.  **Procesamiento de Mensajes (`process_message_sync`)**:
    *   Antes de llamar al LLM (`Agent` de `pydantic-ai`), se verifica si `self.retriever` está inicializado.
    *   Si está disponible, se ejecuta `self.retriever.invoke(message)` para obtener los documentos relevantes.
    *   Los documentos recuperados se formatean en `rag_context_str`.
    *   Esta cadena de contexto RAG se antepone al mensaje original del usuario antes de pasarlo al `self.agent.run_sync()`.

## 6. Flujo de Datos RAG

1.  Usuario envía mensaje a `OrchestratorAgent` (via `orchestrator_app.py`).
2.  Orquestador clasifica y delega a `JiraAgent`.
3.  `JiraAgent.process_message_sync` recibe el mensaje.
4.  Se realiza una búsqueda semántica en ChromaDB (`vector_store_db/`) usando el mensaje.
5.  Se recuperan los `k` chunks más relevantes.
6.  Se formatean los chunks como `Contexto relevante: ...`.
7.  El contexto RAG se concatena con el mensaje original.
8.  El mensaje aumentado se envía al LLM (`pydantic-ai Agent`).
9.  El LLM genera una respuesta considerando el mensaje y el contexto RAG.
10. La respuesta final se devuelve al usuario.

## 7. Configuración y Consideraciones

*   Las constantes de configuración RAG (`KNOWLEDGE_BASE_DIR`, `VECTOR_STORE_DIR`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`) están definidas principalmente en `app/utils/indexing.py`.
*   `JiraAgent` actualmente necesita conocer `VECTOR_STORE_DIR` y `EMBEDDING_MODEL` para cargar el retriever. **Oportunidad de mejora:** Refactorizar para que `JiraAgent` reciba el retriever ya inicializado o la configuración necesaria de forma centralizada (e.g., desde el orquestador o un objeto de configuración).
*   El rendimiento de RAG depende de la calidad de los documentos, el modelo de embeddings y la configuración del `retriever` (`k`).
*   La indexación automática al inicio puede añadir un pequeño retraso al arranque si la base de conocimientos es muy grande o si hay cambios frecuentes. Si esto se convierte en un problema, se podría explorar la indexación asíncrona.

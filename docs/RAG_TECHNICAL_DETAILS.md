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

## 4. Proceso de Indexación (`index_knowledge.py`)

Este script se encarga de procesar los documentos de `knowledge_base/` y crear/actualizar la base de datos vectorial en `vector_store_db/`.

**Pasos Clave:**

1.  **Carga:** Usa `DirectoryLoader` de LangChain para cargar todos los archivos `.md` desde `KNOWLEDGE_BASE_DIR`.
2.  **División:** Usa `RecursiveCharacterTextSplitter` para dividir los documentos en chunks más pequeños (`CHUNK_SIZE`, `CHUNK_OVERLAP`) para optimizar la recuperación.
3.  **Embeddings:** Inicializa `HuggingFaceEmbeddings` (usando el modelo `EMBEDDING_MODEL` especificado, por defecto `all-MiniLM-L6-v2`).
4.  **Almacenamiento:** Crea una instancia de `Chroma` usando los embeddings generados y los chunks de texto. Especifica `persist_directory=VECTOR_STORE_DIR` para guardar la base de datos localmente.
5.  **Persistencia:** (Aunque ChromaDB ahora persiste automáticamente, se mantenía una llamada explícita a `vector_store.persist()`, que ahora es innecesaria pero no perjudicial).

**Ejecución:**
Se debe ejecutar manualmente después de añadir/modificar archivos en `knowledge_base/`. **Requiere que el entorno virtual (`venv`) esté activo.**

```bash
# Activar venv si no lo está
# source venv/bin/activate
python index_knowledge.py
```

## 5. Integración en Agentes (`JiraAgent`)

La lógica RAG se ha integrado en `app/agents/jira_agent.py`:

1.  **Inicialización (`__init__`)**:
    *   Se cargan las configuraciones (`VECTOR_STORE_DIR`, `EMBEDDING_MODEL`).
    *   Se inicializa `HuggingFaceEmbeddings`.
    *   Se carga la base de datos `Chroma` desde `VECTOR_STORE_DIR` usando los embeddings.
    *   Se crea un `retriever` a partir del vector store (`self.retriever = vector_store.as_retriever(...)`). Se configuran `search_kwargs={'k': 2}` para recuperar los 2 chunks más relevantes.
    *   Se manejan posibles errores durante la inicialización para que el agente pueda funcionar sin RAG si la DB no existe o falla la carga.

2.  **Procesamiento de Mensajes (`process_message_sync`)**:
    *   Antes de llamar al LLM (el `Agent` de `pydantic-ai`), se verifica si el `retriever` está inicializado.
    *   Si está disponible, se ejecuta `self.retriever.invoke(message)` para obtener los documentos relevantes de ChromaDB basados en el mensaje del usuario.
    *   Los documentos recuperados se formatean en una cadena de texto legible (`rag_context_str`).
    *   Esta cadena de contexto RAG se antepone al mensaje original del usuario antes de pasarlo al `self.agent.run_sync()`:
        ```python
        input_with_context = f"Contexto relevante:
{rag_context_str}

Mensaje Original:
{message}"
        # ...
        response = self.agent.run_sync(input_data={"input": input_with_context})
        ```

## 6. Flujo de Datos RAG

1.  Usuario envía mensaje a `OrchestratorAgent`.
2.  Orquestador clasifica y delega a `JiraAgent`.
3.  `JiraAgent.process_message_sync` recibe el mensaje.
4.  Se realiza una búsqueda semántica en ChromaDB (`vector_store_db/`) usando el mensaje como query.
5.  Se recuperan los `k` chunks más relevantes de la base de conocimiento.
6.  Estos chunks se formatean como `Contexto relevante: ...`.
7.  El contexto RAG se concatena con el mensaje original.
8.  El mensaje aumentado se envía al LLM subyacente (`pydantic-ai Agent`).
9.  El LLM genera una respuesta, considerando tanto el mensaje original como el contexto RAG adicional.
10. La respuesta final se devuelve al usuario.

## 7. Configuración y Consideraciones

*   Las constantes `KNOWLEDGE_BASE_DIR`, `VECTOR_STORE_DIR`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP` están definidas en `index_knowledge.py`.
*   Las constantes `VECTOR_STORE_DIR` y `EMBEDDING_MODEL` se repiten en `jira_agent.py` para la carga del retriever. Sería ideal centralizar esta configuración (e.g., en `app/config/config.py`).
*   El rendimiento de RAG depende de la calidad de los documentos en `knowledge_base/`, la efectividad del modelo de embeddings y la configuración del `retriever` (`k`).
*   La indexación debe ejecutarse manualmente. Para sistemas más dinámicos, se podría considerar una indexación periódica o basada en eventos.

# Asistente Atlassian: Resumen Técnico del Proyecto

## 1. Visión General

Este proyecto implementa un **Asistente Atlassian**, una aplicación web conversacional (chatbot) diseñada para permitir a los usuarios interactuar con sus instancias de **Jira** y **Confluence** utilizando lenguaje natural en español. La interfaz principal está construida con Streamlit y se enriquece con una base de conocimientos local a través de **Retrieval-Augmented Generation (RAG)**.

## 2. Arquitectura General

La aplicación sigue un patrón de **Orquestador + Agentes Especializados + RAG**:

*   **Interfaz de Usuario (Streamlit):** Proporciona la interfaz web conversacional (`orchestrator_app.py` es el script principal de Streamlit).
*   **Punto de Entrada (`app.py`):** Actúa como un wrapper que lanza `orchestrator_app.py`.
*   **Orquestador (`app/agents/orchestrator_agent.py`):** Controlador central que clasifica la intención (Jira, Confluence, Incidente) y delega al agente apropiado. Gestiona el flujo y el contexto conversacional (`SharedContext` definido aquí).
*   **Agentes Especializados (`app/agents/`):**
    *   `jira_agent.py`: Maneja lógica de Jira, **enriquecido con RAG** para obtener contexto adicional de `knowledge_base/`.
    *   `confluence_agent.py`: Maneja lógica de Confluence.
    *   `incident_template_agent.py`: Guía la creación de plantillas de incidentes.
*   **Mecanismo RAG:**
    *   `knowledge_base/`: Almacena documentos Markdown/texto con conocimiento específico.
    *   `vector_store_db/`: Base de datos ChromaDB generada (no en Git).
    *   `app/utils/indexing.py`: Contiene la lógica para cargar, dividir, generar embeddings (con SentenceTransformers) y almacenar en ChromaDB.
    *   La indexación se dispara automáticamente al inicio desde `orchestrator_app.py` si se detectan cambios.
    *   `index_knowledge.py`: Script para forzar manualmente la reindexación.
*   **Clientes API (`app/utils/`):**
    *   `jira_client.py`: Comunicación con API Jira.
    *   `confluence_client.py`: Comunicación con API Confluence.
*   **Configuración (`.env`):** Gestiona credenciales y parámetros.
*   **Modelos de Datos (`app/agents/models.py`):** Define estructuras Pydantic para datos de Atlassian.
*   **Logging (`app/utils/logger.py`, Logfire):** Configura y gestiona el logging/observabilidad.

## 3. Tecnologías y Dependencias Clave

*   **Framework Web:** Streamlit (`streamlit>=1.32.0`)
*   **Inteligencia Artificial:** OpenAI API (`openai>=1.12.0`)
*   **Modelado de Datos (IA):** Pydantic-AI (`pydantic-ai>=0.1.3`)
*   **API Atlassian:** `atlassian-python-api>=3.41.10`
*   **Orquestación RAG:** LangChain (`langchain`, `langchain-community`, `langchain-openai`, `langchain-chroma`, `langchain-huggingface`)
*   **Vector Store:** ChromaDB (`chromadb>=0.4.0`)
*   **Embeddings Locales:** SentenceTransformers (`sentence-transformers>=2.2.0`, modelo `all-MiniLM-L6-v2`)
*   **Cliente HTTP:** `httpx>=0.26.0`
*   **Gestión de Configuración:** `python-dotenv>=1.0.0`
*   **Logging/Observabilidad:** Logfire (`logfire>=0.15.0`)
*   **Lenguaje:** Python 3.8+

## 4. Características Técnicas Notables

*   **Procesamiento de Lenguaje Natural (PLN):** Uso de OpenAI para entender solicitudes, clasificar intenciones y extraer entidades.
*   **Retrieval-Augmented Generation (RAG):** Mejora de respuestas mediante la recuperación de contexto relevante desde una base de conocimientos local (`knowledge_base/`) usando ChromaDB y embeddings locales.
*   **Indexación Automática RAG:** La base de conocimientos se actualiza en la base vectorial al inicio de la aplicación si se detectan cambios.
*   **Manejo Avanzado de Fechas:** Interpretación y formateo de fechas en español.
*   **Arquitectura Modular:** Separación de responsabilidades (UI, Orquestador, Agentes, RAG, Clientes API).
*   **Contexto Conversacional:** Mantenimiento del estado (`SharedContext`) y la ventana de historial entre interacciones y agentes.
*   **Configuración Externa:** Uso de `.env` para credenciales.

## 5. Puntos de Entrada

*   **Principal:** `app.py` (ejecutar con `python app.py`). Este script actúa como wrapper.
*   **Streamlit App:** `orchestrator_app.py` (ejecutado por `app.py`).
*   **Indexación Manual:** `index_knowledge.py` (ejecutar con `python index_knowledge.py --force`).
*   Otros (`confluence_app.py`, `run_app.py`) pueden existir pero `app.py` es el recomendado actualmente.

## 6. Cómo Ejecutar (Recomendado)

1.  Clonar repositorio.
2.  Crear y activar entorno virtual (`venv`).
3.  Instalar dependencias: `pip install -r requirements.txt`
4.  Configurar `.env`.
5.  (Opcional) Añadir/modificar archivos en `knowledge_base/`.
6.  Ejecutar: `python app.py`

Este documento sirve como una guía rápida para entender la estructura técnica y los componentes clave del proyecto "Asistente Atlassian". 
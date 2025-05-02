# Asistente Atlassian: Resumen Técnico del Proyecto

## 1. Visión General

Este proyecto implementa un **Asistente Atlassian**, una aplicación web conversacional (chatbot) diseñada para permitir a los usuarios interactuar con sus instancias de **Jira** y **Confluence** utilizando lenguaje natural en español. La interfaz principal está construida con Streamlit.

## 2. Arquitectura General

La aplicación sigue un patrón de **Orquestador + Agentes Especializados**:

*   **Interfaz de Usuario (Streamlit):** Proporciona la interfaz web conversacional. El código relevante se encuentra principalmente en `app/ui/app.py`, aunque existen otros puntos de entrada (`/app.py`, `/orchestrator_app.py`). `/orchestrator_app.py` parece ser el punto de entrada principal que integra la lógica de orquestación.
*   **Orquestador (`app/agents/orchestrator_agent.py`):** Actúa como el controlador central. Recibe la entrada del usuario, utiliza IA (OpenAI) para clasificar la intención (Jira, Confluence, etc.) y delega la tarea al agente apropiado. Gestiona el flujo de la conversación y mantiene el contexto.
*   **Agentes Especializados (`app/agents/`):**
    *   `jira_agent.py`: Maneja lógica específica de Jira (queries, worklogs, transiciones de estado).
    *   `confluence_agent.py`: Maneja lógica específica de Confluence (búsqueda, visualización de páginas).
    *   `incident_template_agent.py`: Guía al usuario para completar plantillas de incidentes.
*   **Clientes API (`app/utils/`):**
    *   `jira_client.py`: Encapsula la comunicación con la API REST de Jira.
    *   `confluence_client.py`: Encapsula la comunicación con la API REST de Confluence.
*   **Configuración (`app/config/config.py`, `.env`):** Gestiona credenciales y parámetros de la aplicación.
*   **Modelos de Datos (`app/agents/models.py`):** Define estructuras de datos (probablemente Pydantic) usadas internamente, posiblemente con `pydantic-ai` para interacción con la IA.
*   **Logging (`app/utils/logger.py`):** Configura y gestiona el logging usando Logfire.

## 3. Tecnologías y Dependencias Clave

*   **Framework Web:** Streamlit (`streamlit>=1.32.0`)
*   **Inteligencia Artificial:** OpenAI API (`openai>=1.12.0`)
*   **Modelado de Datos (IA):** Pydantic-AI (`pydantic-ai>=0.1.3`)
*   **API Atlassian:** `atlassian-python-api>=3.41.10`
*   **Cliente HTTP:** `httpx>=0.26.0` (posiblemente usado por la librería de Atlassian o directamente)
*   **Gestión de Configuración:** `python-dotenv>=1.0.0`
*   **Logging/Observabilidad:** Logfire (`logfire>=0.15.0`)
*   **Lenguaje:** Python 3.8+

## 4. Características Técnicas Notables

*   **Procesamiento de Lenguaje Natural (PLN):** Uso intensivo de OpenAI para entender las solicitudes del usuario en español, clasificar intenciones y extraer entidades.
*   **Manejo Avanzado de Fechas:** Implementación específica para interpretar y formatear fechas en español, incluyendo el manejo de la fecha actual y la corrección de ambigüedades.
*   **Arquitectura Modular:** Separación clara de responsabilidades entre la UI, el orquestador, los agentes especializados y los clientes API.
*   **Contexto Conversacional:** Mantenimiento del estado y contexto de la conversación (probablemente usando `st.session_state` de Streamlit) a medida que el usuario interactúa y el control pasa entre agentes.
*   **Configuración Externa:** Uso de variables de entorno para gestionar información sensible y parámetros de configuración.

## 5. Puntos de Entrada

Existen múltiples archivos `app.py`:

*   `/app.py`: Posible punto de entrada simple o versión inicial (mencionado en `README.md`).
*   `/orchestrator_app.py`: Probablemente el punto de entrada para la aplicación completa con orquestación.
*   `/confluence_app.py`: Posiblemente una versión enfocada solo en Confluence.
*   `app/ui/app.py`: Contiene la lógica de la UI de Streamlit, importada por los puntos de entrada anteriores.

Se recomienda investigar cuál es el punto de entrada principal previsto para la ejecución (`orchestrator_app.py` es un fuerte candidato).

## 6. Cómo Ejecutar (Según README)

1.  Clonar repositorio.
2.  Instalar dependencias: `pip install -r requirements.txt`
3.  Configurar `.env` a partir de `env.example`.
4.  Ejecutar: `python app.py` (Nota: verificar si `python orchestrator_app.py` es más apropiado).

Este documento sirve como una guía rápida para entender la estructura técnica y los componentes clave del proyecto "Asistente Atlassian". 
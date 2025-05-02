# Asistente Atlassian

Un agente conversacional para gestionar Jira y Confluence utilizando IA, ahora con conocimiento específico del proyecto gracias a RAG.

## Características

- **Orquestación inteligente** - Detecta automáticamente si una consulta es para Jira o Confluence
- **Gestión de issues** - Visualiza y gestiona tus issues de Jira
- **Registro de tiempo** - Agrega registros de trabajo a tus issues
- **Cambio de estados** - Cambia el estado de tus issues de forma conversacional
- **Análisis de horas** - Verifica si has cumplido con tus horas de trabajo
- **Búsqueda de documentación** - Encuentra documentación en Confluence
- **Consulta de contenidos** - Visualiza y extrae información de páginas de Confluence
- **Generación Aumentada por Recuperación (RAG)** - Utiliza una base de conocimientos local (`knowledge_base/`) para proporcionar respuestas más precisas sobre información específica del proyecto (actualmente integrado en el agente de Jira)
- **Indexación Automática** - La base de conocimientos RAG se actualiza automáticamente al iniciar la aplicación si se detectan cambios
- **Interfaz conversacional** - Interactúa con Jira y Confluence utilizando lenguaje natural
- **IA avanzada** - Utiliza modelos de OpenAI para procesar consultas en lenguaje natural
- **Persistencia de contexto** - Mantiene el contexto de la conversación entre agentes
- **Gestión de fechas** - Manejo avanzado de fechas en español con detección automática de la fecha actual
- **Corrección de confusiones** - Sistema inteligente para detectar y corregir confusiones con fechas
- **Interfaz en español** - Localización completa de la interfaz, incluyendo formato de fechas en español

## Requisitos

- Python 3.8+
- Cuenta de Jira con acceso a API
- Token de API de Jira
- Cuenta de Confluence con acceso a API
- Token de API de Confluence
- Clave de API de OpenAI
- Dependencias listadas en `requirements.txt` (incluyendo `streamlit`, `langchain-*`, `chromadb`, `sentence-transformers`, etc.)

## Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tuusuario/atlassian-assistant.git
   cd atlassian-assistant
   ```

2. Crea y activa un entorno virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Configura las variables de entorno:
   ```bash
   cp env.example .env
   ```
   Edita el archivo `.env` con tus credenciales de Jira, Confluence y OpenAI.

## Base de Conocimientos (RAG)

Este proyecto utiliza **Retrieval-Augmented Generation (RAG)** para mejorar las respuestas del asistente con información específica.

*   **Fuente de Conocimiento (`knowledge_base/`):**
    *   Coloca archivos Markdown (`.md`) o de texto (`.txt`) en este directorio.
    *   Estos archivos deben contener la información específica que deseas que el asistente conozca (definiciones, procedimientos, acrónimos, etc.).
*   **Base de Datos Vectorial (`vector_store_db/`):**
    *   ChromaDB almacena aquí una representación optimizada (embeddings) del contenido de `knowledge_base/` para búsquedas rápidas.
    *   Este directorio se genera automáticamente y **no debe incluirse en Git** (está en `.gitignore`).
*   **Indexación Automática:**
    *   Al iniciar la aplicación (`python app.py`), el sistema comprueba si ha habido cambios en `knowledge_base/` desde la última indexación.
    *   Si se detectan cambios (o si `vector_store_db/` no existe), la base de datos vectorial se actualiza automáticamente. Verás un mensaje como "Actualizando base de conocimientos..." en la interfaz de Streamlit.
*   **Indexación Manual Forzada:**
    *   Si necesitas forzar una reindexación completa manualmente (por ejemplo, si sospechas que el índice está corrupto), puedes ejecutar:
        ```bash
        # Asegúrate de que el venv está activo
        python index_knowledge.py --force
        ```
*   **Uso Actual:**
    *   Actualmente, solo el **Agente Jira** está configurado para utilizar el contexto RAG recuperado de esta base de conocimientos.

## Uso

1. Asegúrate de que tu entorno virtual (`venv`) esté activado:
   ```bash
   source venv/bin/activate
   ```
2. Añade la información relevante a la carpeta `knowledge_base/` (si aún no lo has hecho).
3. Ejecuta la aplicación principal:
   ```bash
   python app.py
   ```
   *Nota: `app.py` actúa como un wrapper que a su vez ejecuta la aplicación Streamlit principal definida en `orchestrator_app.py`.*

Esto iniciará la interfaz web en una URL local (normalmente `http://localhost:8501`). La primera vez (o si cambiaste `knowledge_base/`), puede tardar un poco más mientras se indexan los documentos.

## Ejemplos de uso

### Jira

- "¿Qué historias tengo asignadas?"
- "Agregar 2h de trabajo a PSIMDESASW-111"
- "¿Cuál es el estado de PSIMDESASW-222?"
- "Cambiar el estado de mi historia PSIMDESASW-333"
- "¿Cumplí con mis horas de ayer?"
- "Explícame qué es el proyecto Foobar" (Si "proyecto Foobar" está definido en `knowledge_base/`)

### Confluence

- "Buscar páginas sobre microservicios"
- "¿Qué documentación tenemos sobre AWS?"
- "Muestra la documentación del proyecto XYZ"
- "¿Dónde encuentro información sobre el proceso de deploy?"
- "Crear una página nueva sobre arquitectura"

## Estructura del proyecto

```
atlassian-assistant/
│
├── app/                          # Código fuente de la aplicación
│   ├── agents/                   # Agentes IA
│   │   ├── jira_agent.py         # Agente de Jira
│   │   ├── confluence_agent.py   # Agente de Confluence
│   │   ├── orchestrator_agent.py # Orquestador que delega a los agentes
│   │   └── models.py             # Modelos de datos para los agentes
│   │
│   ├── config/                   # Configuración
│   │   └── config.py             # Archivo de configuración
│   │
│   ├── logs/                     # Logs de la aplicación
│   │
│   ├── ui/                       # Interfaz de usuario
│   │   └── app.py                # Aplicación Streamlit para Jira
│   │
│   └── utils/                    # Utilidades
│       ├── jira_client.py        # Cliente para interactuar con la API de Jira
│       ├── confluence_client.py  # Cliente para interactuar con la API de Confluence
│       └── logger.py             # Configuración de logs
│
├── knowledge_base/               # Directorio para archivos de conocimiento RAG (.md, .txt)
│
├── vector_store_db/              # Base de datos vectorial ChromaDB (generada, en .gitignore)
│
├── docs/                         # Documentación adicional (como RAG_OVERVIEW.md)
│
├── .env                          # Variables de entorno (no incluido en el repositorio)
├── env.example                   # Ejemplo de variables de entorno
├── requirements.txt              # Dependencias
├── app.py                        # Punto de entrada de la aplicación
├── orchestrator_app.py           # Aplicación Streamlit con orquestador
├── confluence_app.py             # Aplicación Streamlit para Confluence
├── index_knowledge.py            # Script para indexación manual forzada
└── README.md                     # Este archivo
```

## Configuración

### Jira

Para obtener un token de API de Jira:

1. Inicia sesión en tu cuenta de Jira
2. Ve a Configuración de la cuenta > Seguridad > Tokens de API
3. Crea un token y cópialo
4. Agrega el token a tu archivo `.env`

### Confluence

Para obtener un token de API de Confluence:

1. Inicia sesión en tu cuenta de Atlassian
2. Ve a Configuración de la cuenta > Seguridad > Tokens de API
3. Crea un token y cópialo
4. Agrega el token a tu archivo `.env`

### OpenAI

Para obtener una clave de API de OpenAI:

1. Crea una cuenta en [OpenAI](https://platform.openai.com/)
2. Ve a la sección "API Keys" y genera una nueva clave
3. Copia la clave y agrégala a tu archivo `.env` como `OPENAI_API_KEY`

## Arquitectura del Orquestador

El sistema utiliza un patrón de delegación de agentes con contexto compartido:

1. **OrchestratorAgent**: Recibe todas las consultas y determina a qué agente especializado delegarlas
2. **Clasificador**: Utiliza IA para clasificar cada consulta como relacionada con Jira o Confluence
3. **Contexto compartido**: Mantiene el historial de la conversación y el contexto entre cambios de agente
4. **Agentes especializados**: Procesan las consultas específicas de su dominio

El orquestador es responsable de:
- Clasificar las consultas entrantes
- Mantener la coherencia de la conversación
- Gestionar transiciones entre temas
- Conservar el contexto entre diferentes agentes
- Manejar información de fecha actual
- Corregir confusiones con fechas

## Sistema de manejo de fechas

El sistema implementa un manejo avanzado de fechas con las siguientes características:

1. **Detección automática de fecha actual**: El sistema detecta y mantiene la fecha actual en todas las interacciones.
2. **Formato localizado**: Las fechas se formatean en español utilizando el formato "día de mes de año".
3. **Contexto compartido**: La fecha actual se mantiene en el contexto compartido y se actualiza en cada interacción.
4. **Corrección de confusiones**: El sistema detecta y corrige confusiones con fechas específicas (como "3 de noviembre de 2023").
5. **Prompts enriquecidos**: Los prompts de sistema de los agentes incluyen la fecha actual para mejorar el contexto.
6. **Mappeo manual de meses y días**: Implementa un sistema de mapeo manual para asegurar la localización correcta.

## Desarrollo

### Agregar nuevos agentes

Para agregar nuevos agentes:
1. Crea un nuevo archivo en el directorio `app/agents/`
2. Implementa la interfaz estándar con el método `process_message_sync`
3. Actualiza el orquestador para reconocer y delegar al nuevo agente 

### Ampliación del sistema

El sistema está diseñado para ser ampliado con:
- Soporte para más idiomas
- Integración con otros servicios de Atlassian
- Funcionalidades adicionales como creación de contenido
- Personalización de la interfaz de usuario 

## Changelog

### 2025-04-25: Corrección de husos horarios en registro de tiempo

- **Problema resuelto**: Se corrigió un problema donde los tiempos registrados en Jira aparecían con fecha incorrecta.
- **Causa**: El sistema estaba utilizando siempre UTC (+0000) para los registros de trabajo, sin tener en cuenta la zona horaria del usuario.
- **Solución**: Ahora se utiliza la zona horaria local del usuario para registrar los tiempos, lo que asegura que los worklogs aparezcan en el día correcto en Jira.
- **Implementación técnica**: Se modificó el método `_parse_date_str_to_jira_started_format` para usar mediodía (12:00) como hora por defecto y respetar la zona horaria local, evitando problemas con el cambio de horario de verano.
- **Corrección adicional (2025-04-25)**: Se ajustó el formato del offset de zona horaria para cumplir exactamente con el requisito de Jira (YYYY-MM-DDTHH:MM:SS.SSSZ), utilizando el formato sin dos puntos en el offset de zona horaria.

## Agente Templates Incidentes (ATI)

El ATI es un agente especializado en la recopilación de información para registrar Incidentes Mayores. Guía al usuario a través de una conversación estructurada siguiendo un template específico.

### Características

- Interfaz conversacional paso a paso en Streamlit
- Recopilación de datos estructurada según un template configurado
- Validación de datos y gestión de listas (usuarios de soporte, acciones realizadas)
- Paso de confirmación final antes de finalizar el proceso
- Integración con el orquestador del sistema multiagente

### Ejecución independiente

Para ejecutar el ATI de forma independiente, utiliza el siguiente comando:

```bash
streamlit run incident_template_app.py
```

### Ejecución a través del orquestador

El ATI también está integrado en el orquestador principal. Para interactuar con él a través del orquestador, inicia la aplicación principal y menciona que deseas registrar un incidente:

```bash
python app.py
```

Y luego, en la interfaz conversacional, puedes escribir mensajes como:
- "Quiero registrar un incidente mayor"
- "Necesito crear un template de incidente"
- "Ayúdame a documentar un problema"

El orquestador te redirigirá automáticamente al ATI. 
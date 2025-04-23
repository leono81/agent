# Asistente Atlassian

Un agente conversacional para gestionar Jira y Confluence utilizando IA.

## Características

- **Orquestación inteligente** - Detecta automáticamente si una consulta es para Jira o Confluence
- **Gestión de issues** - Visualiza y gestiona tus issues de Jira
- **Registro de tiempo** - Agrega registros de trabajo a tus issues
- **Cambio de estados** - Cambia el estado de tus issues de forma conversacional
- **Análisis de horas** - Verifica si has cumplido con tus horas de trabajo
- **Búsqueda de documentación** - Encuentra documentación en Confluence
- **Consulta de contenidos** - Visualiza y extrae información de páginas de Confluence
- **Interfaz conversacional** - Interactúa con Jira y Confluence utilizando lenguaje natural
- **IA avanzada** - Utiliza modelos de OpenAI para procesar consultas en lenguaje natural
- **Persistencia de contexto** - Mantiene el contexto de la conversación entre agentes

## Requisitos

- Python 3.8+
- Cuenta de Jira con acceso a API
- Token de API de Jira
- Cuenta de Confluence con acceso a API
- Token de API de Confluence
- Clave de API de OpenAI

## Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tuusuario/atlassian-assistant.git
   cd atlassian-assistant
   ```

2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configura las variables de entorno:
   ```bash
   cp env.example .env
   ```
   Edita el archivo `.env` con tus credenciales de Jira, Confluence y OpenAI.

## Uso

Ejecuta la aplicación:
```bash
python app.py
```

Esto iniciará la interfaz web en `http://localhost:8501`

## Ejemplos de uso

### Jira

- "¿Qué historias tengo asignadas?"
- "Agregar 2h de trabajo a PSIMDESASW-111"
- "¿Cuál es el estado de PSIMDESASW-222?"
- "Cambiar el estado de mi historia PSIMDESASW-333"
- "¿Cumplí con mis horas de ayer?"

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
├── .env                          # Variables de entorno (no incluido en el repositorio)
├── env.example                   # Ejemplo de variables de entorno
├── requirements.txt              # Dependencias
├── app.py                        # Punto de entrada de la aplicación
├── orchestrator_app.py           # Aplicación Streamlit con orquestador
├── confluence_app.py             # Aplicación Streamlit para Confluence
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

## Desarrollo

### Agregar nuevos agentes

Para agregar nuevos agentes:
1. Crea un nuevo archivo en el directorio `app/agents/`
2. Implementa la interfaz estándar con el método `process_message_sync`
3. Actualiza el orquestador para reconocer y delegar al nuevo agente 
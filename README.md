# Jira Agent

Un agente conversacional para gestionar issues de Jira utilizando IA.

## Características

- **Gestión de issues** - Visualiza y gestiona tus issues de Jira
- **Registro de tiempo** - Agrega registros de trabajo a tus issues
- **Cambio de estados** - Cambia el estado de tus issues de forma conversacional
- **Análisis de horas** - Verifica si has cumplido con tus horas de trabajo
- **Interfaz conversacional** - Interactúa con Jira utilizando lenguaje natural
- **IA avanzada** - Utiliza modelos de OpenAI para procesar consultas en lenguaje natural

## Requisitos

- Python 3.8+
- Cuenta de Jira con acceso a API
- Token de API de Jira
- Clave de API de OpenAI

## Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tuusuario/jira-agent.git
   cd jira-agent
   ```

2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configura las variables de entorno:
   ```bash
   cp env.example .env
   ```
   Edita el archivo `.env` con tus credenciales de Jira y OpenAI.

## Uso

Ejecuta la aplicación:
```bash
python app.py
```

Esto iniciará la interfaz web en `http://localhost:8501`

## Ejemplos de uso

- "¿Qué historias tengo asignadas?"
- "Agregar 2h de trabajo a PSIMDESASW-111"
- "¿Cuál es el estado de PSIMDESASW-222?"
- "Cambiar el estado de mi historia PSIMDESASW-333"
- "¿Cumplí con mis horas de ayer?"

## Estructura del proyecto

```
jira-agent/
│
├── app/                      # Código fuente de la aplicación
│   ├── agents/               # Agentes IA
│   │   ├── jira_agent.py     # Agente principal de Jira
│   │   └── models.py         # Modelos de datos para el agente
│   │
│   ├── config/               # Configuración
│   │   └── config.py         # Archivo de configuración
│   │
│   ├── logs/                 # Logs de la aplicación
│   │
│   ├── ui/                   # Interfaz de usuario
│   │   └── app.py            # Aplicación Streamlit
│   │
│   └── utils/                # Utilidades
│       ├── jira_client.py    # Cliente para interactuar con la API de Jira
│       └── logger.py         # Configuración de logs
│
├── .env                      # Variables de entorno (no incluido en el repositorio)
├── env.example               # Ejemplo de variables de entorno
├── requirements.txt          # Dependencias
├── app.py                    # Punto de entrada de la aplicación
└── README.md                 # Este archivo
```

## Configuración

### Jira

Para obtener un token de API de Jira:

1. Inicia sesión en tu cuenta de Jira
2. Ve a Configuración de la cuenta > Seguridad > Tokens de API
3. Crea un token y cópialo
4. Agrega el token a tu archivo `.env`

### OpenAI

Para obtener una clave de API de OpenAI:

1. Crea una cuenta en [OpenAI](https://platform.openai.com/)
2. Ve a la sección "API Keys" y genera una nueva clave
3. Copia la clave y agrégala a tu archivo `.env` como `OPENAI_API_KEY`

## Desarrollo

### Agregar nuevos agentes

Para agregar nuevos agentes, crea un nuevo archivo en el directorio `app/agents/` y sigue el patrón del agente existente.

### Personalización de la interfaz

La interfaz de usuario se encuentra en `app/ui/app.py` y puede ser personalizada según tus necesidades. 
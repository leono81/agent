import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
load_dotenv()

# Configuración para la API de Jira
JIRA_URL = os.getenv("JIRA_URL", "https://your-jira-instance.atlassian.net")
JIRA_USERNAME = os.getenv("JIRA_USERNAME", "your-email@example.com")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "your-api-token")

# Configuración para la API de Confluence
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "https://your-confluence-instance.atlassian.net")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME", "your-email@example.com")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "your-api-token")

# Configuración para OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-api-key")

# Configuración para logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.path.join(LOG_DIR, "agent.log")

# Configuración para Logfire
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN", "pylf_v1_us_WCthn2WSrxnsg18XjNwyFsJ0Djm3pYkBjSwwBPSwrlF3")
USE_LOGFIRE = os.getenv("USE_LOGFIRE", "True").lower() in ["true", "1", "yes"]

# Configuración de la aplicación
APP_NAME = os.getenv("APP_NAME", "Jira Agent") 
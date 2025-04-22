import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración de Jira
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Configuración de logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "app/logs/agent.log")

# Configuración de la aplicación
APP_NAME = os.getenv("APP_NAME", "Jira Agent")

# Configuración de OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 
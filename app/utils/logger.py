import os
import logging
import logfire
from app.config.config import LOG_LEVEL, LOG_FILE

# Asegurar que el directorio de logs existe
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Configuración de logfire
logfire.configure(send_to_logfire=False)

# Configurar logging estándar de Python con el handler de logfire
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),  # Console handler
        logfire.LogfireLoggingHandler(),
    ]
)

# Crear logger para el agente
agent_logger = logging.getLogger("jira_agent")

def get_logger(name=None):
    """
    Obtiene un logger configurado.
    
    Args:
        name (str, optional): Nombre del logger. Si no se proporciona, se usa el logger del agente.
        
    Returns:
        logging.Logger: Logger configurado.
    """
    if name:
        return logging.getLogger(f"jira_agent.{name}")
    return agent_logger 
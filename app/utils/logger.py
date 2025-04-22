import os
import logging
import logfire
from app.config.config import LOG_LEVEL, LOG_FILE, LOG_DIR, USE_LOGFIRE, LOGFIRE_TOKEN

# Asegurar que el directorio de logs existe
os.makedirs(LOG_DIR, exist_ok=True)

# Configurar logfire solo si está habilitado
if USE_LOGFIRE:
    try:
        # Si hay token disponible, úsalo directamente
        if LOGFIRE_TOKEN:
            os.environ["LOGFIRE_TOKEN"] = LOGFIRE_TOKEN
        logfire.configure()
    except Exception as e:
        print(f"No se pudo configurar Logfire: {e}")
        print("Continuando sin Logfire...")

# Configurar logging estándar para archivo
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(getattr(logging, LOG_LEVEL))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Configurar logging para consola
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Configurar logging estándar
logging.basicConfig(level=getattr(logging, LOG_LEVEL), handlers=[file_handler, console_handler])

# Obtener el logger configurado
agent_logger = logging.getLogger("jira_agent")

def get_logger(name=None):
    """
    Devuelve un logger configurado.
    
    Args:
        name (str, optional): Nombre del logger. Si es None, se devuelve el logger por defecto.
        
    Returns:
        Logger: Logger configurado.
    """
    if name:
        return logging.getLogger(name)
    return agent_logger 
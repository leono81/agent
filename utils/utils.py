# utils/utils.py
import logging
import os
import re
import datetime
from logging.handlers import RotatingFileHandler

log_directory = "workbench"
log_file_path = os.path.join(log_directory, "logs.txt")
os.makedirs(log_directory, exist_ok=True)

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')


file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# Obtener el nivel de log del entorno
log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# --- Crear y configurar el logger específico para ESTE módulo (utils) ---
logger = logging.getLogger(__name__) # Usar __name__ para obtener 'utils.utils'
logger.setLevel(log_level)
if not logger.handlers: # Evitar duplicados si se importa varias veces
    logger.addHandler(file_handler)
    # No añadir console handler aquí tampoco para mantener logs solo en archivo
    logger.propagate = False

def setup_logger(name: str, level: int = log_level) -> logging.Logger:
    """Configura y devuelve un logger que escribe SOLO en archivo.""" # <-- Descripción actualizada
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        logger.addHandler(file_handler)
        # Eliminamos la línea que añade el console_handler
        # logger.addHandler(console_handler)
        logger.propagate = False

    return logger

def parse_time_string_to_seconds(time_string: str) -> int | None:
    """
    Convierte un string de tiempo estilo Jira (ej. '2h 30m', '45m', '1d') a segundos.
    Asume día laboral de 8 horas. Devuelve None si el formato es inválido.
    """
    total_seconds = 0
    # Expresión regular para encontrar partes como '2h', '30m', '1d'
    pattern = re.compile(r'(\d+)\s*(d|h|m)\b', re.IGNORECASE)
    matches = pattern.findall(time_string)

    if not matches and not time_string.isdigit(): # Si no hay coincidencias y no es solo un número (de minutos?)
         logger.warning(f"Formato de tiempo inválido: '{time_string}'. No se pudo parsear.")
         return None

    valid_input = False
    for value, unit in matches:
        try:
            num_value = int(value)
            unit_lower = unit.lower()
            if unit_lower == 'd':
                total_seconds += num_value * 8 * 60 * 60 # Asumiendo 8h/día
                valid_input = True
            elif unit_lower == 'h':
                total_seconds += num_value * 60 * 60
                valid_input = True
            elif unit_lower == 'm':
                total_seconds += num_value * 60
                valid_input = True
        except ValueError:
            logger.warning(f"Valor numérico inválido en time_string: '{value}'")
            return None # Error si una parte no es numérica

    # Si no encontramos unidades d/h/m pero es un número, asumimos que son minutos
    if not valid_input and time_string.isdigit():
         try:
             total_seconds = int(time_string) * 60
             valid_input = True
         except ValueError:
             pass # Ya se retornaría None abajo

    if not valid_input:
        logger.warning(f"Formato de tiempo inválido o no reconocido: '{time_string}'")
        return None

    logger.debug(f"String de tiempo '{time_string}' convertido a {total_seconds} segundos.")
    return total_seconds

def format_iso_datetime(dt: datetime.datetime | None = None) -> str:
    """Formatea un datetime a ISO 8601 con timezone +0000 (formato común en Jira)."""
    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    # Formato: 2023-08-01T12:00:00.000+0000
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+0000'

def escape_jql_string(value: str) -> str:
    """
    Escapa caracteres especiales en un string para usarlo de forma segura dentro
    de una consulta JQL entre comillas simples o dobles.
    Principalmente escapa las comillas y la barra invertida.
    """
    if not isinstance(value, str):
        # Si no es string, intentar convertirlo, aunque idealmente ya debería serlo
        value = str(value)

    # Reemplazar barra invertida con doble barra invertida
    escaped_value = value.replace('\\', '\\\\')
    # Reemplazar comillas dobles con barra invertida y comillas dobles
    escaped_value = escaped_value.replace('"', '\\"')
    # Reemplazar comillas simples con barra invertida y comillas simples
    escaped_value = escaped_value.replace("'", "\\'")

    # Podríamos añadir más caracteres si fuera necesario, pero estos son los más comunes.
    logger.debug(f"Escapando JQL: '{value}' -> '{escaped_value}'")
    return escaped_value

# Ejemplo de logger para usar en otros módulos
# from utils.utils import setup_logger
# logger = setup_logger(__name__)
# logger.info("Este es un mensaje de info")
import os
import atexit
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import re  # Importar regex para parsing
import locale # Importar locale

from pydantic_ai import Agent, RunContext, Tool
from pydantic import BaseModel, Field

from app.utils.jira_client import JiraClient
from app.utils.logger import get_logger
from app.agents.models import Issue, Worklog, Transition, AgentResponse
from app.config.config import OPENAI_API_KEY, LOGFIRE_TOKEN, USE_LOGFIRE

# Importar logfire para instrumentación
try:
    import logfire
    has_logfire = True
except ImportError:
    has_logfire = False

# Forward reference para type hint de JiraAgent dentro de JiraAgentDependencies
if TYPE_CHECKING:
    from .jira_agent import JiraAgent

# Configurar logger ANTES de intentar usarlo
logger = get_logger("jira_agent")

# Configurar locale a español para parsear meses
try:
    # Intentar configuración común para Linux/macOS
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8') 
except locale.Error:
    try:
        # Intentar configuración alternativa/Windows
        locale.setlocale(locale.LC_TIME, 'es-ES') 
    except locale.Error:
        # Ahora el logger existe, así que esto funcionará
        logger.warning("No se pudo configurar el locale a español (es_ES o es-ES). El parseo de meses en texto puede fallar.")

# Configurar logfire para el agente (si está disponible)
use_logfire = False
if has_logfire and USE_LOGFIRE:
    try:
        # Configurar Logfire con el token proporcionado
        os.environ["LOGFIRE_TOKEN"] = LOGFIRE_TOKEN
        logfire.configure(send_to_logfire=True)  # Activar envío a Logfire
        logger.info("Logfire configurado correctamente con token de escritura")
        use_logfire = True
        
        # Registrar función para cerrar Logfire al salir
        def cleanup_logfire():
            logger.info("Cerrando Logfire...")
            try:
                # Esperar 2 segundos para que se envíen los últimos logs
                import time
                time.sleep(2)
                # En algunas versiones más recientes de Logfire es posible llamar a logfire.shutdown()
                # Pero verificamos si existe el método
                if hasattr(logfire, 'shutdown'):
                    logfire.shutdown()
            except Exception as e:
                logger.warning(f"Error al cerrar Logfire: {e}")
        
        # Registrar la función para ejecutarse al salir
        atexit.register(cleanup_logfire)
        
        # Instrumentar también las peticiones HTTP para un mejor seguimiento
        try:
            logfire.instrument_httpx(capture_all=True)
            logger.info("Instrumentación HTTPX activada")
        except Exception as http_e:
            logger.warning(f"No se pudo activar la instrumentación HTTPX: {http_e}")
            
    except Exception as e:
        logger.warning(f"No se pudo configurar Logfire: {e}. La instrumentación no estará disponible.")

# Configuración global de pydanticai para usar la API key de OpenAI
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Importar la señal desde el orquestador o definirla aquí si es más limpio
# Por ahora, la definimos aquí para evitar dependencias circulares
AGENT_CANNOT_HANDLE_SIGNAL = "$AGENT_CANNOT_HANDLE"

@dataclass
class JiraAgentDependencies:
    """Dependencias para el agente de Jira."""
    jira_client: JiraClient
    context: Dict[str, Any]  # Contexto para almacenar información entre interacciones
    agent_instance: 'JiraAgent'

class JiraAgent:
    """Agente para interactuar con Jira de forma conversacional."""
    
    def __init__(self):
        """Inicializa el agente de Jira."""
        try:
            # Iniciar cliente Jira
            jira_client = JiraClient()
            
            # Crear diccionario de contexto para almacenar estado entre interacciones
            context = {
                "conversation_history": [],
                "last_search_results": [],
                "current_issue": None
            }
            
            # Crear dependencias para el agente
            self._deps = JiraAgentDependencies(
                jira_client=jira_client,
                context=context,
                agent_instance=self
            )
            
            # Preparar las herramientas para el agente
            agent_tools = [
                Tool(self.get_conversation_history, takes_ctx=True, 
                    name="get_conversation_history",
                    description="Obtiene el historial reciente de la conversación entre el usuario y el agente."),
                Tool(self.remember_current_issue, takes_ctx=True, 
                    name="remember_current_issue",
                    description="Guarda la issue actual en la memoria para futuras referencias. Usa esta herramienta cada vez que el usuario seleccione una issue específica."),
                Tool(self.get_current_issue, takes_ctx=True, 
                    name="get_current_issue",
                    description="Obtiene la issue actualmente guardada en memoria, si existe. Útil cuando el usuario hace referencia a 'la issue actual', 'esta issue', etc."),
                Tool(self.get_my_issues, takes_ctx=True, 
                    name="get_my_issues",
                    description="Obtiene las issues asignadas al usuario actual en Jira. Muestra las issues con su título, estado, y prioridad."),
                Tool(self.get_my_worklogs_yesterday, takes_ctx=True, 
                    name="get_my_worklogs_yesterday",
                    description=(
                        "Obtiene y formatea los worklogs del usuario de ayer, incluyendo estado de 8h. "
                        "Si la respuesta contiene 'use_directly: True', debes usar el valor de 'markdown_output' directamente como tu respuesta final, sin modificarlo."
                    )
                ),
                Tool(self.search_issues, takes_ctx=True, 
                    name="search_issues",
                    description="Busca issues en Jira basado en un término de búsqueda. Útil para encontrar issues específicas por título, descripción o palabra clave."),
                Tool(self.smart_search_issues, takes_ctx=True, 
                    name="smart_search_issues",
                    description="Busca issues en Jira de manera inteligente, combinando búsqueda por términos y filtrado por diferentes criterios. Esta es la herramienta principal para buscar issues. Usa esta herramienta en lugar de search_issues."),
                Tool(self.get_issue_by_reference, takes_ctx=True, 
                    name="get_issue_by_reference",
                    description="Obtiene la clave de una issue basada en una referencia del usuario (como 'opción 1', 'la primera', etc.). Usa esta herramienta antes de realizar acciones sobre una issue mencionada por el usuario."),
                Tool(self.get_issue_details, takes_ctx=True, 
                    name="get_issue_details",
                    description="Obtiene detalles completos de una issue específica de Jira."),
                Tool(self.get_issue_worklogs, takes_ctx=True, 
                    name="get_issue_worklogs",
                    description="Obtiene los registros de trabajo (worklogs) de una issue específica de Jira."),
                Tool(self.add_worklog, takes_ctx=True, 
                    name="add_worklog",
                    description="Agrega un registro de trabajo (worklog) a una issue de Jira. Requiere la clave de la issue, tiempo dedicado y opcionalmente un comentario y fecha."),
                Tool(self.add_comment, takes_ctx=True, 
                    name="add_comment",
                    description="Agrega un comentario a una issue de Jira SIN registrar tiempo. Útil cuando el usuario solo quiere comentar sin imputar horas."),
                Tool(self.get_issue_transitions, takes_ctx=True, 
                    name="get_issue_transitions",
                    description="Obtiene las transiciones disponibles para una issue específica de Jira."),
                Tool(self.transition_issue, takes_ctx=True, 
                    name="transition_issue",
                    description="Cambia el estado de una issue de Jira utilizando una transición disponible."),
                Tool(self.get_current_time_tracking, takes_ctx=True, 
                    name="get_current_time_tracking",
                    description="Obtiene información detallada sobre el tiempo registrado para la issue especificada, incluyendo tiempo estimado, tiempo gastado, y tiempo restante."),
                Tool(self.get_my_worklogs_for_date, takes_ctx=True, 
                    name="get_my_worklogs_for_date",
                    description="Obtiene y formatea los worklogs del usuario para una fecha específica, incluyendo estado de 8h. "
                    "Si la respuesta contiene 'use_directly: True', debes usar el valor de 'markdown_output' directamente como tu respuesta final, sin modificarlo."
                )
            ]
            
            # Inicializar el agente de PydanticAI
            self.agent = Agent(
                "openai:gpt-4o",  # Usa GPT-4o para mejor procesamiento de contexto
                deps_type=JiraAgentDependencies,
                tools=agent_tools,  # Usar la lista de herramientas preparada
                # Habilitar memoria para mantener contexto de conversación
                system_prompt=(
                    "Eres un asistente experto en Jira que ayuda a los usuarios a gestionar sus issues. "
                    "Puedes proporcionar información sobre issues, buscar issues, agregar registros de trabajo "
                    "y cambiar estados de issues en Jira. "
                    "Sé conciso, claro y siempre útil. Cuando necesites más información, pregunta al usuario. "
                    "\n\n"
                    "INFORMACIÓN IMPORTANTE SOBRE FECHAS:\n"
                    f"- La fecha actual es {self._deps.context.get('current_date_human', datetime.now().strftime('%d de %B de %Y'))}.\n"
                    f"- Hoy es {self._deps.context.get('weekday', datetime.now().strftime('%A'))}.\n"
                    "- Cuando el usuario haga referencia a 'hoy', usa la fecha actual indicada arriba.\n"
                    "- Cuando el usuario mencione 'ayer', calcula correctamente el día anterior.\n"
                    "\n\n"
                    "DIRECTRICES IMPORTANTES DE CONTEXTO Y MEMORIA: "
                    "- SIEMPRE usa la herramienta get_conversation_history al inicio de tu respuesta para recordar el contexto de la conversación. "
                    "  Esto te permitirá mantener la coherencia y recordar referencias a issues, búsquedas previas y preferencias del usuario. "
                    "- Cuando el usuario seleccione una issue, SIEMPRE usa remember_current_issue para guardarla para futuras referencias. "
                    "- Si el usuario hace referencia a 'la issue actual', 'esta issue', 'la misma issue', etc., usa get_current_issue para obtener la issue actual. "
                    "- Si el usuario hace referencia a algo mencionado previamente, consulta el historial para recordar el contexto. "
                    "\n\n"
                    "FUNCIONALIDADES DE CONSULTA DE TIEMPO: "
                    "- Para obtener todos los registros de trabajo del usuario actual ayer, utiliza get_my_worklogs_yesterday. "
                    "  Esta herramienta es útil cuando el usuario quiere saber cuánto tiempo registró ayer o en qué issues trabajó. "
                    "- La función solo devuelve los worklogs creados específicamente por el usuario actual, no muestra registros de otros usuarios."
                    "- Para consultas como '¿qué hice ayer?', '¿cuánto tiempo registré ayer?', 'muéstrame mis worklogs de ayer', "
                    "  usa directamente get_my_worklogs_yesterday sin realizar búsquedas adicionales. "
                    "\n\n"
                    "DIRECTRICES PARA BÚSQUEDA DE ISSUES: "
                    "- Para buscar issues, SIEMPRE utiliza la herramienta smart_search_issues. "
                    "- Cuando el usuario haga referencia a una issue por un número de opción o descripción (como 'opción 1', 'la primera', 'opción 7', 'esa issue', 'la daily'), "
                    "- DEBES utilizar la herramienta get_issue_by_reference para obtener la clave correcta de la issue (ej. PSIMDESASW-123) antes de proceder con otras acciones (como get_issue_details o add_worklog). "
                    "- SOLO USAMOS LAS HISTORIAS QUE EMPIEZAN CON PSIMDESASW. "
                    "- No intentes adivinar la clave de la issue basándote en el número de opción. Usa siempre get_issue_by_reference."
                    "- Cuando el usuario busque 'Dailys' o 'la Daily' en la búsqueda, debes entender que, se refiere a la issue PSIMDESASW-6701."
                    "\n\n"
                    "DIRECTRICES PARA REGISTRO DE TIEMPO (ADD_WORKLOG): "
                    "- Si el usuario da un nombre de issue ambiguo (ej. 'daily'), primero usa smart_search_issues, presenta las opciones, espera confirmación, usa get_issue_by_reference para obtener la clave, y LUEGO llama a add_worklog con la clave correcta. "
                    "- Puedes especificar el tiempo en minutos ('30 minutos'), horas decimales ('1.5 horas', '0,75 h') o mixto ('1 hora 30 minutos', '2h 15m'). "
                    "- Puedes especificar la fecha con términos relativos ('ayer', 'lunes pasado') o fechas exactas ('2024-05-20'). Si no se especifica, usa hoy."
                    "Cuando el usuario quiera registrar tiempo para 'Dailys' o 'la Daily' en la búsqueda, debes entender que, se refiere generalemente, se refiere a la issue PSIMDESASW-6701."
                    "\n\n"
                    "DIRECTRICES PARA COMENTARIOS: "
                    "- Si el usuario solo quiere añadir un comentario a una issue SIN registrar tiempo, usa la herramienta add_comment. "
                    "- No uses add_worklog cuando el usuario solo quiere comentar sin registrar tiempo. "
                    "- Ejemplos de peticiones para añadir solo comentarios: 'añade un comentario a la issue', 'comenta en la issue', 'agrega el comentario X a la issue'."
                    "\n\n"
                    "INFORMACIÓN TÉCNICA IMPORTANTE SOBRE LA API DE JIRA: "
                    "- El método issue_worklog de la API de Jira NO acepta argumentos con nombre (keyword arguments). "
                    "  Debe ser llamado con argumentos posicionales en el orden correcto: issue_key, started, time_in_sec. "
                    "- El parámetro 'started' debe estar en formato ISO 8601 con offset (ej. '2023-04-22T14:00:00.000+0000'). "
                    "- Si necesitas añadir comentarios, debes usar issue_add_comment como método separado, ya que issue_worklog no procesa comentarios. "
                    "- La herramienta add_worklog ya maneja esta lógica internamente, pero recuerda estos detalles si necesitas resolver problemas. "
                    "- Para cualquier error relacionado con la API, consulta la documentación de la biblioteca 'atlassian-python-api'."
                ),
                instrument=use_logfire  # Habilitar instrumentación para monitoreo con logfire solo si está disponible
            )
            
            logger.info("Agente de Jira inicializado correctamente")
            
        except Exception as e:
            logger.error(f"Error al inicializar el agente de Jira: {e}")
            raise
    
    def _parse_time_str_to_seconds(self, time_str: str) -> Optional[int]:
        """Convierte una cadena de tiempo en varios formatos a segundos."""
        time_str = time_str.lower().replace(",", ".")
        total_minutes = 0
        
        # Formato: Xh Ym (ej. 2h 30m)
        match_hm = re.search(r'(\d+\.?\d*)\s*h(?:ora?s?)?\s*(\d+\.?\d*)\s*m(?:inuto?s?)?'
                             r'|(\d+\.?\d*)\s*h(?:ora?s?)?'
                             r'|(\d+\.?\d*)\s*m(?:inuto?s?)?'
                             , time_str)

        if match_hm:
            hours = 0
            minutes = 0
            if match_hm.group(1) and match_hm.group(2):
                hours = float(match_hm.group(1))
                minutes = float(match_hm.group(2))
            elif match_hm.group(3):
                hours = float(match_hm.group(3))
            elif match_hm.group(4):
                minutes = float(match_hm.group(4))
            total_minutes = round(hours * 60 + minutes)
        elif "hora" in time_str or " h" in time_str:
            match = re.search(r'(\d+\.?\d*)', time_str)
            if match:
                total_minutes = round(float(match.group(1)) * 60)
        elif "minuto" in time_str or " min" in time_str or " m" in time_str:
            match = re.search(r'(\d+\.?\d*)', time_str)
            if match:
                total_minutes = round(float(match.group(1)))
        else:
             try:
                 # Asumir que son solo minutos si es un número
                 num_val = float(time_str)
                 # Considerar si es más probable que sean minutos u horas
                 # Si es <= 12, podríamos asumir horas? Por ahora asumimos minutos.
                 total_minutes = round(num_val)
             except ValueError:
                 logger.error(f"Formato de tiempo no reconocido: {time_str}")
                 return None

        if total_minutes <= 0:
            logger.error(f"Tiempo inválido o cero: {time_str} -> {total_minutes} mins")
            return None
            
        total_seconds = total_minutes * 60
        logger.info(f"Tiempo parseado: '{time_str}' -> {total_seconds} segundos")
        return total_seconds

    def _parse_date_str_to_jira_started_format(self, date_str: str) -> Optional[str]:
        """Convierte una cadena de fecha a formato YYYY-MM-DDTHH:MM:SS.sssZ respetando la zona horaria local."""
        # Reutilizar lógica de parseo de fecha para obtener objeto date
        parsed_date = self._parse_date_description_to_date_obj(date_str)

        if parsed_date:
            # En lugar de usar el inicio del día (00:00:00) y UTC (+0000),
            # usamos 12:00:00 (mediodía) para evitar problemas con cambios de horario de verano
            dt_obj = datetime.combine(parsed_date, datetime.min.time().replace(hour=12))
            
            # Crear un datetime con zona horaria aware usando el timezone local
            dt_with_tz = dt_obj.astimezone()
            
            # Formatear directamente al formato que Jira espera exactamente: YYYY-MM-ddTHH:mm:ss.SSSZ
            # Donde Z es +0000 o -0300, etc. sin los dos puntos
            # Primero obtenemos el offset sin los dos puntos
            utc_offset = dt_with_tz.strftime('%z')
            
            # Después formateamos la fecha completa
            jira_started_format = dt_with_tz.strftime("%Y-%m-%dT%H:%M:%S.000") + utc_offset
            
            logger.info(f"Fecha parseada: '{date_str}' -> {jira_started_format}")
            return jira_started_format
        
        return None

    def _parse_date_description_to_date_obj(self, date_description: str) -> Optional[date]:
        """Parsea una descripción textual de fecha a un objeto date."""
        parsed_date = None
        # Obtener la fecha actual desde el contexto si está disponible
        if self._deps and hasattr(self._deps, 'context') and 'current_date' in self._deps.context:
            try:
                current_date_str = self._deps.context['current_date']
                today = datetime.strptime(current_date_str, "%Y-%m-%d").date()
                logger.info(f"Usando fecha actual desde contexto para parseo: {today}")
            except (ValueError, KeyError) as e:
                logger.warning(f"Error al leer fecha del contexto para parseo, usando date.today(): {e}")
                today = date.today()
        else:
            today = date.today()
            logger.info(f"Usando fecha actual del sistema para parseo: {today}")

        desc_lower = date_description.lower().strip()
        # Remover artículos y preposiciones comunes
        desc_lower = re.sub(r'^(el|la|los|las|de|del)\s+|(\s+de|del)$', '', desc_lower).strip()

        if desc_lower == "hoy":
            parsed_date = today
        elif desc_lower == "ayer":
            parsed_date = today - timedelta(days=1)
        elif desc_lower == "anteayer":
            parsed_date = today - timedelta(days=2)
        elif "pasado" in desc_lower or "pasada" in desc_lower:
            # Manejar 'lunes pasado', 'semana pasada' (semana pasada necesita más lógica, omitido por ahora)
            days_of_week = {
                "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
                "domingo": 6
            }
            target_day = -1
            for day_name, day_index in days_of_week.items():
                if day_name in desc_lower:
                    target_day = day_index
                    break
            if target_day != -1:
                days_ago = (today.weekday() - target_day + 7) % 7
                if days_ago == 0: days_ago = 7 # Si hoy es el día, referirse a la semana pasada
                parsed_date = today - timedelta(days=days_ago)
            # Si no encuentra un día específico, no hacer nada aquí
        
        # Intentar formatos estándar después de los relativos
        if parsed_date is None:
            try:
                parsed_date = date.fromisoformat(desc_lower)
                logger.debug(f"Parseado '{date_description}' como ISO YYYY-MM-DD")
            except ValueError:
                try:
                    parsed_date = datetime.strptime(desc_lower, "%d/%m/%Y").date()
                    logger.debug(f"Parseado '{date_description}' como DD/MM/YYYY")
                except ValueError:
                    # Intentar formato "DD de MMMM [de YYYY]" (español)
                    try:
                        # Añadir año actual si falta
                        if not re.search(r'\d{4}', desc_lower):
                            desc_with_year = f"{desc_lower} de {today.year}"
                        else:
                            desc_with_year = desc_lower
                        parsed_date = datetime.strptime(desc_with_year, '%d de %B de %Y').date()
                        logger.debug(f"Parseado '{date_description}' como DD de MMMM [de YYYY]")
                    except ValueError:
                         # Intentar parseo de día de la semana (ej. "miércoles")
                        days_of_week = {
                            "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                            "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
                            "domingo": 6
                        }
                        target_day = -1
                        # Buscar coincidencia exacta del día
                        cleaned_desc = desc_lower.replace('este ','').strip()
                        if cleaned_desc in days_of_week:
                            target_day = days_of_week[cleaned_desc]
                        
                        if target_day != -1:
                            # Calcular diferencia de días (0 si es hoy, negativo si es futuro en la semana, positivo si pasado)
                            days_diff = target_day - today.weekday()
                            # Si es día futuro en la semana actual o hoy, usar esa fecha
                            # Si es día pasado en la semana actual, usar esa fecha
                            parsed_date = today + timedelta(days=days_diff)
                            logger.debug(f"Parseado '{date_description}' como día de la semana: {parsed_date}")
                        else:
                            logger.warning(f"Formato de descripción de fecha no reconocido: {date_description}")
                            return None # Fallo final
        
        # Si llegamos aquí con una fecha válida, retornarla
        if parsed_date:
             logger.info(f"Fecha parseada final para '{date_description}': {parsed_date}")
        return parsed_date

    def _parse_date_description_to_yyyymmdd(self, date_description: str) -> Optional[str]:
        """Convierte una descripción textual de fecha a formato YYYY-MM-DD."""
        parsed_date = self._parse_date_description_to_date_obj(date_description)
        if parsed_date:
            yyyymmdd = parsed_date.isoformat() # Formato YYYY-MM-DD
            logger.info(f"Descripción de fecha '{date_description}' parseada a: {yyyymmdd}")
            return yyyymmdd
        else:
            logger.error(f"No se pudo parsear la descripción de fecha: '{date_description}'")
            return None

    def _format_seconds(self, seconds: int) -> str:
        """
        Formatea segundos a un formato legible.
        
        Args:
            seconds: Segundos a formatear.
            
        Returns:
            Tiempo formateado (ej. "5h 30m").
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"
    
    async def process_message(self, message: str) -> str:
        """
        Procesa un mensaje del usuario y devuelve la respuesta del agente.
        
        Args:
            message (str): Mensaje del usuario.
            
        Returns:
            str: Respuesta del agente.
        """
        try:
            # Obtener el contexto actual
            context = self._deps.context
            
            # Añadir el mensaje actual al historial de conversación
            if "conversation_history" in context:
                context["conversation_history"].append({"role": "user", "content": message})
            
            logger.info(f"Procesando mensaje: {message}")
            
            # Opcional: Imprimir historial actual para depuración
            history_len = len(context.get("conversation_history", []))
            logger.debug(f"Historial de conversación actual: {history_len} mensajes")
            
            # Procesar mensaje con el agente utilizando las dependencias almacenadas
            result = await self.agent.run(message, deps=self._deps)
            response = result.output
            
            # Añadir la respuesta del agente al historial
            if "conversation_history" in context:
                context["conversation_history"].append({"role": "assistant", "content": response})
                # Limitar historial a últimos 20 mensajes para prevenir crecimiento excesivo
                if len(context["conversation_history"]) > 20:
                    context["conversation_history"] = context["conversation_history"][-20:]
                    logger.debug("Historial de conversación truncado a 20 mensajes")
            
            logger.info("Mensaje procesado correctamente")
            return response
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            return f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"
    
    def process_message_sync(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Procesa un mensaje del usuario de forma síncrona, aceptando historial y metadatos.
        Incluye un ejemplo para devolver AGENT_CANNOT_HANDLE_SIGNAL.
        """
        logfire.info(f"JiraAgent procesando mensaje síncrono: {message}")

        # --- Ejemplo de Señal de Reflexión --- 
        # Si el mensaje indica explícitamente Confluence, devolvemos la señal
        if "show me Confluence page" in message:
            logfire.warning("Mensaje parece ser para Confluence, devolviendo señal de no manejo.")
            return AGENT_CANNOT_HANDLE_SIGNAL
        # --- Fin del Ejemplo ---

        # Actualizar contexto interno si se proporciona desde el orquestador
        if conversation_history is not None:
            self._deps.context["conversation_history"] = conversation_history
        if metadata is not None:
            # Actualizar metadatos relevantes, como la fecha
            if "current_date" in metadata:
                self._deps.context["current_date"] = metadata["current_date"]
            if "current_date_human" in metadata:
                self._deps.context["current_date_human"] = metadata["current_date_human"]
            if "weekday" in metadata:
                self._deps.context["weekday"] = metadata["weekday"]

        try:
            # Usar el agente interno de PydanticAI para procesar el mensaje
            # Asegurarse de pasar las dependencias correctas
            result = self.agent.run_sync(message, deps=self._deps)
            response = result.data
            logfire.info(f"JiraAgent respuesta generada: {response[:100]}...")
            return response
        except Exception as e:
            logger.error(f"Error en JiraAgent.process_message_sync: {e}", exc_info=True)
            logfire.error(f"Error en JiraAgent.process_message_sync: {e}")
            # Devolver un mensaje de error genérico o más específico si es posible
            return f"Lo siento, tuve un problema al procesar tu solicitud con Jira: {e}"

    async def add_comment(self, ctx: RunContext[JiraAgentDependencies], issue_key: str, comment: str) -> Dict[str, Any]:
        """
        Añade un comentario a una issue de Jira sin registrar tiempo.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: La clave de la issue (ej. PSIMDESASW-1234)
            comment: El comentario a añadir
            
        Returns:
            Un diccionario con el resultado de la operación
        """
        try:
            logger.info(f"Añadiendo comentario a la issue {issue_key}")
            result = ctx.deps.jira_client.add_comment(issue_key, comment)
            logger.info(f"Comentario añadido exitosamente a la issue {issue_key}")
            return {"success": True, "message": f"Comentario añadido exitosamente a la issue {issue_key}"}
        except Exception as e:
            error_msg = f"Error al añadir comentario a la issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def get_current_time_tracking(self, ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
        """
        Obtiene información detallada sobre el tiempo registrado para la issue especificada.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: La clave de la issue de Jira (ej. PSIMDESASW-1234)
            
        Returns:
            Dict[str, Any]: Diccionario con información sobre el tiempo estimado, tiempo gastado y tiempo restante.
        """
        try:
            logger.info(f"Obteniendo información de tiempo para la issue {issue_key}")
            # Obtener los detalles de tiempo total registrado
            time_spent_info = ctx.deps.jira_client.get_total_time_spent(issue_key)
            
            # Obtener los detalles de la issue para verificar estimaciones
            issue_details = self._deps.jira_client.get_issue_details(issue_key)
            
            result = {
                "issue_key": issue_key,
                "success": True,
                "time_spent": time_spent_info.get("time_spent_seconds", 0),
                "time_spent_formatted": time_spent_info.get("time_spent_formatted", "0h"),
                "worklogs_count": time_spent_info.get("worklogs_count", 0)
            }
            
            # Añadir información de tiempo estimado si está disponible
            if issue_details and "fields" in issue_details:
                fields = issue_details["fields"]
                
                # Obtener tiempo original estimado (si existe)
                if "timeoriginalestimate" in fields and fields["timeoriginalestimate"]:
                    original_estimate_seconds = fields["timeoriginalestimate"]
                    result["original_estimate_seconds"] = original_estimate_seconds
                    result["original_estimate_formatted"] = self._format_seconds(original_estimate_seconds)
                
                # Obtener tiempo restante estimado (si existe)
                if "timeestimate" in fields and fields["timeestimate"]:
                    remaining_estimate_seconds = fields["timeestimate"]
                    result["remaining_estimate_seconds"] = remaining_estimate_seconds
                    result["remaining_estimate_formatted"] = self._format_seconds(remaining_estimate_seconds)
            
            logger.info(f"Información de tiempo obtenida correctamente para {issue_key}")
            return result
            
        except Exception as e:
            error_msg = f"Error al obtener información de tiempo para {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {
                "issue_key": issue_key,
                "success": False,
                "error": error_msg
            }

    async def get_conversation_history(self, ctx: RunContext[JiraAgentDependencies]) -> List[Dict[str, str]]:
        """
        Obtiene el historial reciente de la conversación.
        
        Returns:
            List[Dict[str, str]]: Lista de mensajes de la conversación.
        """
        history = ctx.deps.context.get("conversation_history", [])
        logger.info(f"Obtenido historial de conversación: {len(history)} mensajes")
        return history

    async def remember_current_issue(self, ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
        """
        Guarda la issue actual en la memoria para futuras referencias.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue (ej. PSIMDESASW-1234)
            
        Returns:
            Dict[str, Any]: Resultado de la operación.
        """
        logger.info(f"Guardando issue actual: {issue_key}")
        
        # Obtener la URL de la issue
        issue_url = ctx.deps.jira_client.get_issue_url(issue_key)
        
        # Guardar tanto la clave como la URL en el contexto
        ctx.deps.context["current_issue"] = issue_key
        ctx.deps.context["current_issue_url"] = issue_url
        
        return {
            "success": True, 
            "message": f"Issue {issue_key} guardada como issue actual",
            "issue_key": issue_key,
            "url": issue_url
        }
    
    async def get_current_issue(self, ctx: RunContext[JiraAgentDependencies]) -> Dict[str, Any]:
        """
        Obtiene la issue actualmente guardada en memoria.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            
        Returns:
            Dict[str, Any]: Información sobre la issue actual o un mensaje de error.
        """
        current_issue = ctx.deps.context.get("current_issue")
        current_issue_url = ctx.deps.context.get("current_issue_url")
        
        if current_issue:
            logger.info(f"Obtenida issue actual: {current_issue}")
            return {
                "success": True, 
                "issue_key": current_issue,
                "url": current_issue_url
            }
        else:
            logger.info("No hay issue actual guardada")
            return {"success": False, "error": "No hay ninguna issue seleccionada actualmente"}
    
    async def get_my_issues(self, ctx: RunContext[JiraAgentDependencies]) -> Dict[str, Any]:
        """
        Obtiene las issues asignadas al usuario actual en Jira.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            
        Returns:
            Dict[str, Any]: Lista de issues asignadas al usuario.
        """
        try:
            logger.info("Obteniendo issues asignadas al usuario")
            issues = ctx.deps.jira_client.get_my_issues()
            
            # Guardar resultado en el contexto para referencias posteriores
            ctx.deps.context["last_search_results"] = issues
            
            formatted_issues = []
            for i, issue in enumerate(issues):
                issue_key = issue.get("key", "Sin clave")
                summary = issue.get("fields", {}).get("summary", "Sin título")
                status = issue.get("fields", {}).get("status", {}).get("name", "Sin estado")
                priority = issue.get("fields", {}).get("priority", {}).get("name", "Sin prioridad")
                
                # Obtener URL para la issue
                issue_url = ctx.deps.jira_client.get_issue_url(issue_key)
                
                formatted_issues.append({
                    "option": i + 1,
                    "key": issue_key,
                    "summary": summary,
                    "status": status,
                    "priority": priority,
                    "url": issue_url  # Añadir URL para acceso directo
                })
            
            logger.info(f"Obtenidas {len(formatted_issues)} issues asignadas al usuario")
            return {
                "success": True,
                "count": len(formatted_issues),
                "issues": formatted_issues
            }
            
        except Exception as e:
            error_msg = f"Error al obtener issues asignadas: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def search_issues(self, ctx: RunContext[JiraAgentDependencies], search_term: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Busca issues en Jira basado en un término de búsqueda.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            search_term: Término de búsqueda.
            max_results: Número máximo de resultados (por defecto 10).
            
        Returns:
            Dict[str, Any]: Resultados de la búsqueda.
        """
        try:
            logger.info(f"Buscando issues con término: '{search_term}'")
            issues = ctx.deps.jira_client.search_issues(search_term, max_results)
            
            # Guardar resultado en el contexto para referencias posteriores
            ctx.deps.context["last_search_results"] = issues
            
            formatted_issues = []
            for i, issue in enumerate(issues):
                issue_key = issue.get("key", "Sin clave")
                summary = issue.get("fields", {}).get("summary", "Sin título")
                status = issue.get("fields", {}).get("status", {}).get("name", "Sin estado")
                priority = issue.get("fields", {}).get("priority", {}).get("name", "Sin prioridad")
                
                # Obtener URL para la issue
                issue_url = ctx.deps.jira_client.get_issue_url(issue_key)
                
                formatted_issues.append({
                    "option": i + 1,
                    "key": issue_key,
                    "summary": summary,
                    "status": status,
                    "priority": priority,
                    "url": issue_url  # Añadir URL para acceso directo
                })
            
            logger.info(f"Búsqueda completada: {len(formatted_issues)} issues encontradas")
            return {
                "success": True,
                "count": len(formatted_issues),
                "search_term": search_term,
                "issues": formatted_issues
            }
            
        except Exception as e:
            error_msg = f"Error al buscar issues: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def smart_search_issues(self, ctx: RunContext[JiraAgentDependencies], query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Busca issues en Jira de manera inteligente, combinando búsqueda por términos y filtrado.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            query: Consulta de búsqueda, puede incluir términos como 'asignadas a mí', 'en progreso', etc.
            max_results: Número máximo de resultados (por defecto 10).
            
        Returns:
            Dict[str, Any]: Resultados de la búsqueda inteligente.
        """
        try:
            logger.info(f"Búsqueda inteligente de issues: '{query}'")
            
            # Determinar si la consulta es para issues asignadas al usuario
            if re.search(r'(mis issues|asignadas a m[íi]|mis tareas)', query.lower()):
                # Si se piden las issues del usuario, usar get_my_issues
                logger.info("Detectada consulta de issues propias")
                return await self.get_my_issues(ctx)
            
            # En otros casos, realizar búsqueda normal
            logger.info("Realizando búsqueda estándar")
            return await self.search_issues(ctx, query, max_results)
            
        except Exception as e:
            error_msg = f"Error en búsqueda inteligente: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def get_issue_by_reference(self, ctx: RunContext[JiraAgentDependencies], reference: str) -> Dict[str, Any]:
        """
        Obtiene la clave de una issue basada en una referencia del usuario.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            reference: Referencia como "opción 1", "la primera", etc.
            
        Returns:
            Dict[str, Any]: Información de la issue referenciada o error.
        """
        try:
            logger.info(f"Buscando issue por referencia: '{reference}'")
            last_results = ctx.deps.context.get("last_search_results", [])
            
            if not last_results:
                return {"success": False, "error": "No hay resultados de búsqueda recientes para referenciar"}
            
            # Intentar identificar un número de opción en la referencia
            option_match = re.search(r'(?:opción|opcion|option|número|numero|number)?\s*(\d+)', reference.lower())
            first_match = re.search(r'(primera|primer|first)', reference.lower())
            last_match = re.search(r'(última|ultimo|last)', reference.lower())
            
            selected_index = None
            
            if option_match:
                # Opción por número
                option_num = int(option_match.group(1))
                if 1 <= option_num <= len(last_results):
                    selected_index = option_num - 1
            elif first_match:
                # Primera opción
                selected_index = 0
            elif last_match:
                # Última opción
                selected_index = len(last_results) - 1
            else:
                # Intentar buscar por término exacto en el título o descripción
                for i, issue in enumerate(last_results):
                    summary = issue.get("fields", {}).get("summary", "").lower()
                    key = issue.get("key", "").lower()
                    
                    if reference.lower() in summary or reference.lower() in key:
                        selected_index = i
                        break
            
            if selected_index is not None:
                issue = last_results[selected_index]
                issue_key = issue.get("key")
                summary = issue.get("fields", {}).get("summary", "Sin título")
                
                # Obtener URL para la issue
                issue_url = ctx.deps.jira_client.get_issue_url(issue_key)
                
                logger.info(f"Referencia resuelta a issue: {issue_key} ({summary})")
                return {
                    "success": True,
                    "issue_key": issue_key,
                    "summary": summary,
                    "url": issue_url  # Añadir URL para acceso directo
                }
            else:
                return {"success": False, "error": f"No se pudo identificar una issue con la referencia '{reference}'"}
                
        except Exception as e:
            error_msg = f"Error al resolver referencia de issue: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
    async def get_issue_details(self, ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
        """
        Obtiene detalles completos de una issue específica de Jira.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue (ej. PSIMDESASW-1234)
            
        Returns:
            Dict[str, Any]: Detalles de la issue o error.
        """
        try:
            logger.info(f"Obteniendo detalles de issue: {issue_key}")
            issue = ctx.deps.jira_client.get_issue_details(issue_key)
            
            if not issue:
                return {"success": False, "error": f"No se pudo encontrar la issue {issue_key}"}
            
            # Extraer campos importantes para la respuesta
            fields = issue.get("fields", {})
            
            # Obtener la URL de la issue
            issue_url = ctx.deps.jira_client.get_issue_url(issue_key)
            
            formatted_issue = {
                "key": issue_key,
                "summary": fields.get("summary", "Sin título"),
                "description": fields.get("description", "Sin descripción"),
                "status": fields.get("status", {}).get("name", "Sin estado"),
                "priority": fields.get("priority", {}).get("name", "Sin prioridad"),
                "assignee": fields.get("assignee", {}).get("displayName", "Sin asignar"),
                "reporter": fields.get("reporter", {}).get("displayName", "Sin reportador"),
                "created": fields.get("created", "Fecha desconocida"),
                "updated": fields.get("updated", "Fecha desconocida"),
                "issuetype": fields.get("issuetype", {}).get("name", "Sin tipo"),
                "url": issue_url  # Añadir URL para acceso directo
            }
            
            logger.info(f"Detalles obtenidos para issue {issue_key}")
            return {
                "success": True,
                "issue": formatted_issue
            }
            
        except Exception as e:
            error_msg = f"Error al obtener detalles de issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def get_issue_worklogs(self, ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
        """
        Obtiene los registros de trabajo (worklogs) de una issue específica de Jira.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue (ej. PSIMDESASW-1234)
            
        Returns:
            Dict[str, Any]: Lista de worklogs de la issue o error.
        """
        try:
            logger.info(f"Obteniendo worklogs de issue: {issue_key}")
            worklogs = ctx.deps.jira_client.get_issue_worklogs(issue_key)
            
            formatted_worklogs = []
            total_seconds = 0
            
            for worklog in worklogs:
                author = worklog.get("author", {}).get("displayName", "Usuario desconocido")
                time_spent = worklog.get("timeSpentSeconds", 0)
                started = worklog.get("started", "Fecha desconocida")
                comment = worklog.get("comment", "Sin comentario")
                
                total_seconds += time_spent
                
                formatted_worklogs.append({
                    "author": author,
                    "time_spent": self._format_seconds(time_spent),
                    "started": started,
                    "comment": comment
                })
            
            logger.info(f"Obtenidos {len(formatted_worklogs)} worklogs para issue {issue_key}")
            return {
                "success": True,
                "count": len(formatted_worklogs),
                "total_time": self._format_seconds(total_seconds),
                "worklogs": formatted_worklogs
            }
            
        except Exception as e:
            error_msg = f"Error al obtener worklogs de issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def add_worklog(self, ctx: RunContext[JiraAgentDependencies], issue_key: str, time_str: str, comment: Optional[str] = None, date_str: Optional[str] = "hoy") -> Dict[str, Any]:
        """
        Agrega un registro de trabajo (worklog) a una issue de Jira.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue (ej. PSIMDESASW-1234)
            time_str: Tiempo invertido en formato legible (ej. "1h 30m", "90m", "1.5h")
            comment: Comentario para el worklog (opcional)
            date_str: Fecha del trabajo en formato legible (ej. "hoy", "ayer", "2023-04-22")
                      La fecha se registrará respetando la zona horaria del usuario,
                      lo que asegura que los worklogs aparezcan en el día correcto en Jira.
            
        Returns:
            Dict[str, Any]: Resultado de la operación o error.
        """
        try:
            logger.info(f"Agregando worklog a issue {issue_key}: {time_str}, '{comment}', fecha={date_str}")
            
            # Convertir tiempo a segundos
            time_in_sec = self._parse_time_str_to_seconds(time_str)
            if not time_in_sec:
                return {"success": False, "error": f"Formato de tiempo no válido: '{time_str}'"}
            
            # Convertir fecha a formato Jira (si se proporciona)
            started = None
            if date_str:
                started = self._parse_date_str_to_jira_started_format(date_str)
                if not started:
                    return {"success": False, "error": f"Formato de fecha no válido: '{date_str}'"}
            
            # Agregar worklog
            result = ctx.deps.jira_client.add_worklog(
                issue_key=issue_key,
                time_in_sec=time_in_sec,
                comment=comment,
                started=started
            )
            
            if result:
                logger.info(f"Worklog agregado correctamente a {issue_key}")
                return {
                    "success": True,
                    "message": f"Tiempo registrado correctamente en {issue_key}: {self._format_seconds(time_in_sec)}",
                    "issue_key": issue_key,
                    "time": self._format_seconds(time_in_sec),
                    "date": date_str
                }
            else:
                error_msg = f"Error al agregar worklog a {issue_key}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"Error al agregar worklog a {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def get_issue_transitions(self, ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
        """
        Obtiene las transiciones disponibles para una issue específica de Jira.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue (ej. PSIMDESASW-1234)
            
        Returns:
            Dict[str, Any]: Lista de transiciones disponibles o error.
        """
        try:
            logger.info(f"Obteniendo transiciones para issue: {issue_key}")
            transitions = ctx.deps.jira_client.get_issue_transitions(issue_key)
            
            formatted_transitions = []
            for transition in transitions:
                transition_id = transition.get("id")
                transition_name = transition.get("name", "Sin nombre")
                
                formatted_transitions.append({
                    "id": transition_id,
                    "name": transition_name
                })
            
            logger.info(f"Obtenidas {len(formatted_transitions)} transiciones para issue {issue_key}")
            return {
                "success": True,
                "count": len(formatted_transitions),
                "transitions": formatted_transitions
            }
            
        except Exception as e:
            error_msg = f"Error al obtener transiciones de issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def transition_issue(self, ctx: RunContext[JiraAgentDependencies], issue_key: str, transition_name: str) -> Dict[str, Any]:
        """
        Cambia el estado de una issue a través de una transición.
        
        Args:
            ctx: Contexto de ejecución con las dependencias
            issue_key: Clave de la issue
            transition_name: Nombre de la transición a aplicar
            
        Returns:
            Dict[str, Any]: Resultado de la transición
        """
        try:
            logger.info(f"Intentando transicionar issue {issue_key} a '{transition_name}'")
            
            # Obtener las transiciones disponibles
            transitions = ctx.deps.jira_client.get_issue_transitions(issue_key)
            
            # Buscar la transición por nombre
            transition_id = None
            for transition in transitions:
                if transition["name"].lower() == transition_name.lower():
                    transition_id = transition["id"]
                    break
            
            if not transition_id:
                logger.warning(f"Transición '{transition_name}' no encontrada para {issue_key}")
                return {
                    "success": False,
                    "error": f"La transición '{transition_name}' no está disponible para esta issue"
                }
            
            # Aplicar la transición
            result = ctx.deps.jira_client.transition_issue(issue_key, transition_id)
            
            if result:
                logger.info(f"Issue {issue_key} transicionada exitosamente a '{transition_name}'")
                return {
                    "success": True,
                    "issue_key": issue_key,
                    "message": f"Estado de issue {issue_key} cambiado a través de la transición '{transition_name}'"
                }
            else:
                logger.error(f"Error al transicionar issue {issue_key}")
                return {
                    "success": False,
                    "error": "Ocurrió un error al cambiar el estado de la issue"
                }
                
        except Exception as e:
            error_msg = f"Error al transicionar issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    async def get_my_worklogs_yesterday(self, ctx: RunContext[JiraAgentDependencies]) -> Dict[str, Any]:
        """
        Obtiene y formatea los worklogs del usuario de ayer. Llama a la función generalizada.
        """
        logger.info("Redirigiendo get_my_worklogs_yesterday a get_my_worklogs_for_date('ayer')")
        return await self.get_my_worklogs_for_date(ctx, date_description="ayer")

    async def get_my_worklogs_for_date(self, ctx: RunContext[JiraAgentDependencies], date_description: str) -> Dict[str, Any]:
        """
        Obtiene y formatea los worklogs del usuario para una fecha específica.
        """
        logger.info(f"Obteniendo worklogs para la fecha descrita como: '{date_description}'")
        target_seconds = 8 * 3600  # 8 horas

        # 1. Parsear la descripción de la fecha
        parsed_date_str = self._parse_date_description_to_yyyymmdd(date_description)
        if not parsed_date_str:
            return {
                "response": f"❌ No pude entender la fecha '{date_description}'. Por favor, usa formatos como 'hoy', 'ayer', 'anteayer', 'YYYY-MM-DD', 'DD/MM/YYYY' o 'lunes pasado'."
            }

        try:
            # 2. Llamar al método del cliente Jira con la fecha parseada
            result = ctx.deps.jira_client.get_my_worklogs_for_date(date_str=parsed_date_str, use_cache=False) # Desactivar caché para obtener siempre lo último

            if not result.get('success', False):
                error_msg = result.get('error', 'Error desconocido al obtener worklogs.')
                logger.error(f"Error al obtener worklogs para {parsed_date_str}: {error_msg}")
                return {"response": f"❌ Hubo un error al obtener tus worklogs para {parsed_date_str}: {error_msg}"}

            # 3. Extraer datos y formatear la respuesta en Markdown
            total_seconds = result.get('total_seconds', 0)
            total_formatted = self._format_seconds(total_seconds) # Usar _format_seconds de la clase
            worklogs_count = result.get('count', 0)
            username = result.get('username', 'Usuario')
            worklogs_list = result.get('worklogs', [])
            # Usar la fecha parseada y formateada para mostrar al usuario
            try:
                # Convertir de nuevo a objeto date para formatear
                date_obj = date.fromisoformat(parsed_date_str)
                today = date.today() # Obtener la fecha actual
                # Formatear la fecha dependiendo del año
                if date_obj.year == today.year:
                    # Mismo año: formato corto - usar %B para mes completo
                    display_date = date_obj.strftime('%d de %B')
                else:
                    # Año diferente: formato largo con año - usar %B para mes completo
                    display_date = date_obj.strftime('%d de %B de %Y')
            except ValueError:
                display_date = parsed_date_str # Fallback al formato YYYY-MM-DD

            # --- Construcción de la respuesta Markdown ---
            status_message = f"👤 **Usuario:** {username}\\n\\n🗓️ **Fecha:** {display_date}\\n\\n"

            if worklogs_count == 0:
                 status_message += f"ℹ️ No se encontraron registros de tiempo para esta fecha."
            elif total_seconds >= target_seconds:
                # Corregir el f-string y el escape de comillas
                status_message += f"🎉 **¡Excelente!** Registraste **{total_formatted}**. ({worklogs_count} registros)."
            else:
                missing_seconds = target_seconds - total_seconds
                missing_formatted = self._format_seconds(missing_seconds)
                # Corregir el f-string, escapes y saltos de línea
                status_message += (
                    f"💪 **¡Casi lo tienes!** Registraste **{total_formatted}**. \\n\\n"
                    f"   Te faltan solo **{missing_formatted}** para completar las 8 horas. ({worklogs_count} registros)."
                )

            details = ""
            if worklogs_list:
                logger.info(f"Agent Tool: Received {len(worklogs_list)} worklogs from client: {worklogs_list}") # Log received list
                details += "\n\n---\n\n📝 **Resumen de Registros:**\n"
                issues_summary = {}
                for wl in worklogs_list:
                    key = wl.get('issue_key', 'N/A')
                    summary = wl.get('issue_summary', 'Sin título')
                    # Corregir key a camelCase para coincidir con API de Jira
                    seconds = wl.get('timeSpentSeconds', 0) 
                    comment = wl.get('comment', '')
                    # Log individual worklog details being processed
                    logger.info(f"  Processing worklog for summary: key={key}, seconds={seconds}")
                    if key not in issues_summary:
                        issues_summary[key] = {'summary': summary, 'total_seconds': 0, 'entries': []}
                    issues_summary[key]['total_seconds'] += seconds
                    issues_summary[key]['entries'].append({'time': self._format_seconds(seconds), 'comment': comment})

                sorted_issues = sorted(issues_summary.items(), key=lambda item: item[1]['total_seconds'], reverse=True)

                for key, data in sorted_issues:
                    issue_total_seconds = data['total_seconds'] # Get the summed seconds
                    issue_total_time = self._format_seconds(issue_total_seconds) # Format the sum
                    # Log details before adding to output string
                    logger.info(f"  Formatting summary for issue: key={key}, total_seconds={issue_total_seconds}, formatted_time={issue_total_time}") 
                    details += f"\n\n- **{key}** ({data['summary']}): **{issue_total_time}**"

            # Corregir el f-string final
            final_response_markdown = f"{status_message}{details}"
            logger.info(f"Worklogs para {parsed_date_str} obtenidos y formateados correctamente.")
            
            # Devolver estructura específica para indicar respuesta preformateada
            return {"markdown_output": final_response_markdown, "use_directly": True}

        except Exception as e:
            logger.exception(f"Excepción inesperada al obtener/formatear worklogs para '{date_description}' ({parsed_date_str})")
            return {"response": f"❌ Ocurrió un error inesperado al procesar tu solicitud para '{date_description}': {str(e)}"} 
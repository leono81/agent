import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import re  # Importar regex para parsing

from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field

from app.utils.jira_client import JiraClient
from app.utils.logger import get_logger
from app.agents.models import Issue, Worklog, Transition, AgentResponse
from app.config.config import OPENAI_API_KEY

# Forward reference para type hint de JiraAgent dentro de JiraAgentDependencies
if TYPE_CHECKING:
    from .jira_agent import JiraAgent

# Configurar logger
logger = get_logger("jira_agent")

# Configuración global de pydanticai para usar la API key de OpenAI
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

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
            self.jira_client = JiraClient()
            
            # Inicializar contexto para mantener estado entre llamadas
            self.context = {
                "last_issues": [],  # Lista de últimas issues mostradas
                "last_search_term": None,  # Último término de búsqueda
                "issues_by_index": {}  # Mapeo de índices a claves de issues
            }
            
            # Crear el agente utilizando pydanticai
            self.agent = Agent(
                model="openai:gpt-4o",  # Modelo de OpenAI
                deps_type=JiraAgentDependencies,
                output_type=str,
                memory=True,  # Habilitar memoria para mantener contexto de conversación
                system_prompt=(
                    "Eres un asistente experto en Jira que ayuda a los usuarios a gestionar sus issues. "
                    "Puedes proporcionar información sobre issues, buscar issues, agregar registros de trabajo "
                    "y cambiar estados de issues en Jira. "
                    "Sé conciso, claro y siempre útil. Cuando necesites más información, pregunta al usuario. "
                    "Para buscar issues, SIEMPRE utiliza la herramienta smart_search_issues. "
                    "IMPORTANTE: Cuando el usuario haga referencia a una issue por un número de opción o descripción (como 'opción 1', 'la primera', 'opción 7', 'esa issue', 'la daily'), "
                    "DEBES utilizar la herramienta get_issue_by_reference para obtener la clave correcta de la issue (ej. PSIMDESASW-123) antes de proceder con otras acciones (como get_issue_details o add_worklog). "
                    "No intentes adivinar la clave de la issue basándote en el número de opción. Usa siempre get_issue_by_reference.\n\n"
                    "Para registrar tiempo (add_worklog): "
                    "- Si el usuario da un nombre de issue ambiguo (ej. 'daily'), primero usa smart_search_issues, presenta las opciones, espera confirmación, usa get_issue_by_reference para obtener la clave, y LUEGO llama a add_worklog con la clave correcta. "
                    "- Puedes especificar el tiempo en minutos ('30 minutos'), horas decimales ('1.5 horas', '0,75 h') o mixto ('1 hora 30 minutos', '2h 15m'). "
                    "- Puedes especificar la fecha con términos relativos ('ayer', 'lunes pasado') o fechas exactas ('2024-05-20'). Si no se especifica, usa hoy."
                )
            )
            
            # Registrar herramientas para el agente
            self._register_tools()
            
            logger.info("Agente de Jira inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar el agente de Jira: {e}")
            raise
    
    def _register_tools(self):
        """Registra las herramientas para el agente."""
        
        @self.agent.tool
        async def get_my_issues(ctx: RunContext[JiraAgentDependencies]) -> List[Dict[str, Any]]:
            """
            Obtiene todas las issues asignadas al usuario actual y actualiza el contexto.
            
            Returns:
                Lista de issues asignadas al usuario.
            """
            issues = ctx.deps.jira_client.get_my_issues()
            formatted_issues = []
            
            # Limpiar mapeo anterior
            ctx.deps.context["issues_by_index"] = {}
            ctx.deps.context["last_issues"] = []
            
            for idx, issue in enumerate(issues, 1):
                formatted_issue = {
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "index": idx
                }
                
                formatted_issues.append(formatted_issue)
                
                # Guardar en el contexto para referencias futuras
                ctx.deps.context["issues_by_index"][str(idx)] = issue["key"]
                ctx.deps.context["last_issues"].append(formatted_issue)
            
            logger.info(f"Obtenidas {len(formatted_issues)} issues")
            return formatted_issues
        
        @self.agent.tool
        async def search_issues(
            ctx: RunContext[JiraAgentDependencies], 
            search_term: str,
            max_results: Optional[int] = 10
        ) -> List[Dict[str, Any]]:
            """
            Busca issues por texto o clave, sin importar a quién estén asignadas.
            
            Args:
                search_term: Texto para buscar en el título, descripción o clave (ej. "daily", "PSIMDESASW-123").
                max_results: Número máximo de resultados a devolver.
                
            Returns:
                Lista de issues que coinciden con la búsqueda.
            """
            issues = ctx.deps.jira_client.search_issues(search_term, max_results)
            formatted_issues = []
            
            for issue in issues:
                # Obtener el asignado, si existe
                assignee = "Sin asignar"
                if issue["fields"].get("assignee"):
                    assignee = issue["fields"]["assignee"]["displayName"]
                
                formatted_issues.append({
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "assignee": assignee
                })
            
            logger.info(f"Búsqueda '{search_term}': Encontradas {len(formatted_issues)} issues")
            return formatted_issues
        
        @self.agent.tool
        async def smart_search_issues(
            ctx: RunContext[JiraAgentDependencies], 
            search_term: str,
            max_results: Optional[int] = 10
        ) -> Dict[str, Any]:
            """
            Busca issues inteligentemente o resuelve referencias numéricas.
            1. Si search_term parece una referencia numérica (ej. "opción 1", "la 5"), la resuelve usando el contexto.
            2. Si no, busca primero en las issues asignadas al usuario que coincidan.
            3. Si no encuentra coincidencias asignadas, busca en todas las issues.
            Actualiza el contexto con los resultados de la búsqueda (si no es una referencia).
            
            Args:
                search_term: Texto para buscar, clave de issue, o referencia numérica (ej. "daily", "PSIMDESASW-123", "opción 1").
                max_results: Número máximo de resultados a devolver en búsquedas generales.
                
            Returns:
                Resultado de la búsqueda/resolución de referencia.
            """
            # --- Inicio: Resolución de Referencias Numéricas --- 
            ref_lower = search_term.lower().strip()
            index_to_find = None
            # Extraer número de la referencia si existe
            if "opción" in ref_lower or "opcion" in ref_lower:
                parts = ref_lower.split()
                for part in parts:
                    if part.isdigit():
                        index_to_find = int(part)
                        break
            # Simplificar referencias ordinales básicas
            elif ref_lower in ["la primera", "1"]: index_to_find = 1
            elif ref_lower in ["la segunda", "2"]: index_to_find = 2
            elif ref_lower in ["la tercera", "3"]: index_to_find = 3
            elif ref_lower in ["la cuarta", "4"]: index_to_find = 4
            elif ref_lower in ["la quinta", "5"]: index_to_find = 5
            # ... (podríamos añadir más si fuera necesario)
            
            # Si se encontró un índice, intentar resolver la referencia
            if index_to_find is not None:
                if str(index_to_find) in ctx.deps.context["issues_by_index"]:
                    issue_key = ctx.deps.context["issues_by_index"][str(index_to_find)]
                    logger.info(f"Referencia '{search_term}' resuelta directamente a issue {issue_key} por smart_search_issues")
                    # Devolver un formato similar al de una búsqueda, pero indicando que se resolvió por referencia
                    # Podríamos incluso obtener los detalles aquí, pero mantengámoslo simple por ahora
                    resolved_issue = next((item for item in ctx.deps.context["last_issues"] if item["key"] == issue_key), None)
                    if resolved_issue:
                         return {
                             "found_by_reference": True,
                             "issues": [resolved_issue], # Devolver como lista para consistencia
                             "total_found": 1,
                             "search_term": search_term,
                             "message": f"Referencia '{search_term}' resuelta a la issue {issue_key} ({resolved_issue.get('summary', '')})."
                         }
                    else: 
                         # Si no está en last_issues (raro), devolver solo la clave
                          return {
                             "found_by_reference": True,
                             "issues": [{"key": issue_key, "index": index_to_find}], 
                             "total_found": 1,
                             "search_term": search_term,
                             "message": f"Referencia '{search_term}' resuelta a la issue {issue_key}."
                         }
                else:
                    # No se encontró el índice en el contexto
                    available_indices = list(ctx.deps.context["issues_by_index"].keys())
                    last_search = ctx.deps.context["last_search_term"] or "ninguno"
                    logger.warning(f"Referencia numérica '{search_term}' no encontrada en el contexto.")
                    return {
                        "error": f"No encontré una issue con la referencia '{search_term}'. " +
                                 f"El último término de búsqueda fue '{last_search}'. " +
                                 f"Las opciones disponibles eran: {', '.join(available_indices) if available_indices else 'ninguna'}"
                    }
            # --- Fin: Resolución de Referencias Numéricas --- 
            
            # Si no era una referencia numérica, proceder con la búsqueda normal
            logger.info(f"'{search_term}' no parece referencia numérica, procediendo con búsqueda normal.")
            
            # Guardar el término de búsqueda en el contexto
            ctx.deps.context["last_search_term"] = search_term
            
            # Limpiar mapeo anterior SOLO si es una nueva búsqueda (no referencia)
            ctx.deps.context["issues_by_index"] = {}
            ctx.deps.context["last_issues"] = []
            
            # Paso 1: Obtener todas las issues asignadas al usuario
            my_issues = ctx.deps.jira_client.get_my_issues()
            
            # Filtrar las que coinciden con el término de búsqueda
            filtered_my_issues = []
            for issue in my_issues:
                issue_key_lower = issue["key"].lower()
                summary_lower = issue["fields"]["summary"].lower()
                search_lower = search_term.lower()
                
                # Búsqueda más flexible: clave exacta O término en resumen
                if issue_key_lower == search_lower or search_lower in summary_lower:
                    assignee = "Sin asignar"
                    if issue["fields"].get("assignee"):
                        assignee = issue["fields"]["assignee"]["displayName"]
                    
                    filtered_my_issues.append({
                        "key": issue["key"],
                        "summary": issue["fields"]["summary"],
                        "status": issue["fields"]["status"]["name"],
                        "assignee": assignee
                    })
            
            # Si encontró issues asignadas al usuario, retornarlas
            if filtered_my_issues:
                logger.info(f"Smart búsqueda '{search_term}': Encontradas {len(filtered_my_issues)} issues asignadas al usuario")
                indexed_issues = []
                for idx, issue in enumerate(filtered_my_issues[:max_results], 1):
                    issue_with_index = issue.copy()
                    issue_with_index["index"] = idx
                    indexed_issues.append(issue_with_index)
                    ctx.deps.context["issues_by_index"][str(idx)] = issue["key"]
                    ctx.deps.context["last_issues"].append(issue_with_index)
                
                return {
                    "found_in_my_issues": True,
                    "issues": indexed_issues,
                    "total_found": len(filtered_my_issues),
                    "search_term": search_term,
                    "message": f"Encontré {len(filtered_my_issues)} issues asignadas a ti que coinciden con '{search_term}'."
                }
            
            # Paso 2: Si no encontró issues asignadas, buscar en todas
            logger.info(f"No se encontraron issues asignadas al usuario con '{search_term}'. Buscando en todas las issues.")
            all_issues = ctx.deps.jira_client.search_issues(search_term, max_results)
            
            formatted_all_issues = []
            for issue in all_issues:
                assignee = "Sin asignar"
                if issue["fields"].get("assignee"):
                    assignee = issue["fields"]["assignee"]["displayName"]
                
                formatted_all_issues.append({
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "assignee": assignee
                })
            
            indexed_all_issues = []
            for idx, issue in enumerate(formatted_all_issues, 1):
                issue_with_index = issue.copy()
                issue_with_index["index"] = idx
                indexed_all_issues.append(issue_with_index)
                ctx.deps.context["issues_by_index"][str(idx)] = issue["key"]
                ctx.deps.context["last_issues"].append(issue_with_index)
            
            logger.info(f"Smart búsqueda '{search_term}': Encontradas {len(formatted_all_issues)} issues en búsqueda global")
            # Si no se encontraron issues
            if not indexed_all_issues:
                 return {
                    "issues": [],
                    "total_found": 0,
                    "search_term": search_term,
                    "message": f"No encontré ninguna issue que coincida con '{search_term}', ni asignada a ti ni en búsqueda global."
                }
                
            return {
                "found_in_my_issues": False,
                "issues": indexed_all_issues,
                "total_found": len(formatted_all_issues),
                "search_term": search_term,
                "message": f"No encontré issues asignadas a ti con '{search_term}', pero encontré {len(formatted_all_issues)} issues en total."
            }
        
        @self.agent.tool
        async def get_issue_details(ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
            """
            Obtiene los detalles de una issue específica.
            IMPORTANTE: Esta función requiere la CLAVE EXACTA (ej. PSIMDESASW-111).
            Si el usuario dio una referencia numérica, smart_search_issues ya debería haberla resuelto.
            
            Args:
                issue_key: Clave EXACTA de la issue (ej. PSIMDESASW-111).
                
            Returns:
                Detalles de la issue.
            """
            issue = ctx.deps.jira_client.get_issue_details(issue_key)
            if not issue:
                logger.warning(f"Issue no encontrada: {issue_key}")
                return {"error": f"No se encontró la issue {issue_key}"}
            
            try:
                # Extraer datos relevantes con manejo seguro de valores
                result = {
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "assignee": "Sin asignar"
                }
                
                # Obtener el asignado de forma segura
                if issue["fields"].get("assignee") and issue["fields"]["assignee"].get("displayName"):
                    result["assignee"] = issue["fields"]["assignee"]["displayName"]
                
                # Añadir fechas de forma segura
                if "created" in issue["fields"]:
                    result["created"] = issue["fields"]["created"]
                if "updated" in issue["fields"]:
                    result["updated"] = issue["fields"]["updated"]
                
                # Añadir descripción si existe
                if issue["fields"].get("description"):
                    result["description"] = issue["fields"]["description"]
                
                logger.info(f"Obtenidos detalles de issue {issue_key}")
                return result
            except Exception as e:
                logger.error(f"Error al procesar detalles de la issue {issue_key}: {e}")
                return {"error": f"Error al procesar detalles de la issue {issue_key}: {str(e)}"}
        
        @self.agent.tool
        async def add_worklog(
            ctx: RunContext[JiraAgentDependencies],
            issue_key: str,
            time_spent_str: str,
            comment: Optional[str] = None,
            date_str: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Agrega un registro de trabajo a una issue específica.
            IMPORTANTE: Esta función requiere la CLAVE EXACTA de la issue (ej. PSIMDESASW-111). Si el usuario dio un nombre o referencia, usa smart_search_issues primero.
            
            Args:
                issue_key: Clave EXACTA de la issue (ej. PSIMDESASW-111).
                time_spent_str: Tiempo invertido (ej. "30 minutos", "1.5h", "1 hora 15 min").
                comment: Comentario opcional.
                date_str: Fecha del registro (ej. "ayer", "lunes pasado", "2024-05-21"). Si es None, se usa hoy.
                
            Returns:
                Resultado de la operación.
            """
            agent_instance = ctx.deps.agent_instance 
            
            # Parsear tiempo a SEGUNDOS
            time_in_seconds = agent_instance._parse_time_str_to_seconds(time_spent_str)
            if time_in_seconds is None: # Check for None explicitly
                return {"success": False, "error": f"Formato de tiempo inválido: '{time_spent_str}'. Usa ej. '30m', '1.5h', '2h 15m'"}
            
            # Parsear fecha a formato JIRA STARTED
            started_jira_format = None
            if date_str:
                started_jira_format = agent_instance._parse_date_str_to_jira_started_format(date_str)
                if not started_jira_format:
                    return {"success": False, "error": f"Formato de fecha inválido: '{date_str}'. Usa 'hoy', 'ayer', 'lunes pasado', 'YYYY-MM-DD'"}
            else:
                # Si no se da fecha, usar hoy en formato JIRA
                started_jira_format = agent_instance._parse_date_str_to_jira_started_format("hoy")
                if not started_jira_format: # Fallback por si acaso
                     logger.error("No se pudo parsear 'hoy' a formato Jira started.")
                     return {"success": False, "error": "Error interno al obtener la fecha de hoy."}

            # Intentar agregar el worklog con los parámetros correctos
            success = ctx.deps.jira_client.add_worklog(
                issue_key=issue_key,
                time_in_sec=time_in_seconds, # Pasar segundos
                comment=comment,
                started=started_jira_format # Pasar formato ISO 8601 con offset
            )
            
            if success:
                logger.info(f"Worklog agregado a {issue_key}: {time_spent_str} ({time_in_seconds}s) para fecha {started_jira_format[:10]}.")
                return {"success": True, "message": f"Tiempo registrado ({time_spent_str}) en {issue_key} para el día {started_jira_format[:10]}."}
            else:
                error_detail = "Error desconocido. Verifica la clave de la issue y tus permisos."
                logger.error(f"Error al agregar worklog a {issue_key}: {error_detail}")
                return {"success": False, "error": f"No se pudo registrar el tiempo en {issue_key}. {error_detail}"}
        
        @self.agent.tool
        async def get_issue_worklogs(
            ctx: RunContext[JiraAgentDependencies],
            issue_key: str,
            days_ago: Optional[int] = 7
        ) -> List[Dict[str, Any]]:
            """
            Obtiene los registros de trabajo de una issue en los últimos días.
            
            Args:
                issue_key: Clave de la issue (ej. PSIMDESASW-111).
                days_ago: Número de días hacia atrás para filtrar los worklogs.
                
            Returns:
                Lista de registros de trabajo.
            """
            worklogs = ctx.deps.jira_client.get_issue_worklogs(issue_key)
            
            # Convertir a formato más amigable
            formatted_worklogs = []
            cutoff_date = datetime.now() - timedelta(days=days_ago)
            
            for worklog in worklogs:
                # Convertir timestamp a datetime
                started = datetime.fromisoformat(worklog["started"].replace("Z", "+00:00"))
                
                # Solo incluir worklogs más recientes que el límite
                if started >= cutoff_date:
                    formatted_worklogs.append({
                        "author": worklog["author"]["displayName"],
                        "time_spent": worklog["timeSpent"],
                        "time_spent_seconds": worklog["timeSpentSeconds"],
                        "started": worklog["started"],
                        "comment": worklog.get("comment", "")
                    })
            
            logger.info(f"Obtenidos {len(formatted_worklogs)} worklogs para {issue_key}")
            return formatted_worklogs
        
        @self.agent.tool
        async def get_issue_transitions(
            ctx: RunContext[JiraAgentDependencies],
            issue_key: str
        ) -> List[Dict[str, Any]]:
            """
            Obtiene las transiciones disponibles para una issue.
            
            Args:
                issue_key: Clave de la issue (ej. PSIMDESASW-111).
                
            Returns:
                Lista de transiciones disponibles.
            """
            transitions = ctx.deps.jira_client.get_issue_transitions(issue_key)
            
            # Formato simplificado
            formatted_transitions = []
            for transition in transitions:
                formatted_transitions.append({
                    "id": transition["id"],
                    "name": transition["name"],
                    "to_status": transition["to"]["name"]
                })
            
            logger.info(f"Obtenidas {len(formatted_transitions)} transiciones para {issue_key}")
            return formatted_transitions
        
        @self.agent.tool
        async def transition_issue(
            ctx: RunContext[JiraAgentDependencies],
            issue_key: str,
            transition_id: str
        ) -> Dict[str, Any]:
            """
            Cambia el estado de una issue.
            
            Args:
                issue_key: Clave de la issue (ej. PSIMDESASW-111).
                transition_id: ID de la transición.
                
            Returns:
                Resultado de la operación.
            """
            success = ctx.deps.jira_client.transition_issue(issue_key, transition_id)
            
            if success:
                # Obtener el nuevo estado
                issue = ctx.deps.jira_client.get_issue_details(issue_key)
                new_status = issue["fields"]["status"]["name"] if issue else "desconocido"
                
                logger.info(f"Issue {issue_key} transicionada correctamente a {new_status}")
                return {
                    "success": True, 
                    "message": f"Issue {issue_key} cambiada correctamente a estado {new_status}"
                }
            else:
                logger.error(f"Error al transicionar issue {issue_key}")
                return {
                    "success": False, 
                    "error": f"No se pudo cambiar el estado de la issue {issue_key}"
                }
        
        @self.agent.tool
        async def get_worklogs_by_date(
            ctx: RunContext[JiraAgentDependencies],
            target_date: Optional[str] = None,
            user: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Obtiene los registros de trabajo para una fecha específica.
            
            Args:
                target_date: Fecha en formato YYYY-MM-DD. Si no se proporciona, se usa la fecha actual.
                user: Usuario para filtrar. Si no se proporciona, se usa el usuario actual.
                
            Returns:
                Resumen de los registros de trabajo.
            """
            # Usar fecha actual si no se proporciona
            if not target_date:
                target_date = date.today().isoformat()
            else:
                try:
                    # Validar formato de fecha
                    date.fromisoformat(target_date)
                except ValueError:
                    logger.error(f"Formato de fecha inválido: {target_date}")
                    return {"success": False, "error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
            
            try:
                # Obtener issues
                issues = ctx.deps.jira_client.get_my_issues()
                
                # Resumen de tiempo
                total_seconds = 0
                worklog_summary = []
                
                # Procesar cada issue
                for issue in issues:
                    issue_key = issue["key"]
                    worklogs = ctx.deps.jira_client.get_issue_worklogs(issue_key)
                    
                    issue_seconds = 0
                    issue_logs = []
                    
                    # Filtrar worklogs por fecha
                    for worklog in worklogs:
                        try:
                            # Convertir timestamp a fecha de forma segura
                            if "started" in worklog:
                                worklog_date = datetime.fromisoformat(
                                    worklog["started"].replace("Z", "+00:00")
                                ).date().isoformat()
                                
                                if worklog_date == target_date:
                                    seconds = worklog.get("timeSpentSeconds", 0)
                                    issue_seconds += seconds
                                    issue_logs.append({
                                        "time_spent": worklog.get("timeSpent", "desconocido"),
                                        "seconds": seconds,
                                        "comment": worklog.get("comment", "")
                                    })
                        except Exception as e:
                            logger.error(f"Error al procesar worklog en {issue_key}: {e}")
                            continue
                    
                    # Solo incluir issues con worklogs en la fecha objetivo
                    if issue_logs:
                        try:
                            worklog_summary.append({
                                "issue_key": issue_key,
                                "summary": issue["fields"]["summary"],
                                "total_seconds": issue_seconds,
                                "total_formatted": self._format_seconds(issue_seconds),
                                "logs": issue_logs
                            })
                            total_seconds += issue_seconds
                        except Exception as e:
                            logger.error(f"Error al añadir resumen de worklog para {issue_key}: {e}")
                
                # Calcular horas esperadas (8 horas = 28800 segundos)
                expected_seconds = 28800
                missing_seconds = max(0, expected_seconds - total_seconds)
                
                result = {
                    "date": target_date,
                    "total_seconds": total_seconds,
                    "total_formatted": self._format_seconds(total_seconds),
                    "expected_seconds": expected_seconds,
                    "expected_formatted": "8h",
                    "missing_seconds": missing_seconds,
                    "missing_formatted": self._format_seconds(missing_seconds),
                    "is_complete": total_seconds >= expected_seconds,
                    "worklogs": worklog_summary
                }
                
                logger.info(f"Obtenido resumen de worklogs para {target_date}")
                return result
            except Exception as e:
                logger.error(f"Error al obtener worklogs para {target_date}: {e}")
                return {"success": False, "error": f"Error al obtener worklogs: {str(e)}"}
    
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
        """Convierte una cadena de fecha a formato YYYY-MM-DDTHH:MM:SS.sss+ZZZZ (asumiendo UTC y 00:00:00)."""
        parsed_date = None
        today = date.today()
        date_str_lower = date_str.lower().strip()
        
        if date_str_lower == "hoy":
            parsed_date = today
        elif date_str_lower == "ayer":
            parsed_date = today - timedelta(days=1)
        elif "pasado" in date_str_lower:
            days_of_week = {"lunes": 0, "martes": 1, "miércoles": 2, "jueves": 3, "viernes": 4, "sábado": 5, "domingo": 6}
            target_day = -1
            for day_name, day_index in days_of_week.items():
                if day_name in date_str_lower:
                    target_day = day_index
                    break
            if target_day != -1:
                days_ago = (today.weekday() - target_day + 7) % 7
                if days_ago == 0: days_ago = 7
                parsed_date = today - timedelta(days=days_ago)
        else:
            try:
                parsed_date = date.fromisoformat(date_str)
            except ValueError:
                try:
                    parsed_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                except ValueError:
                    logger.warning(f"Formato de fecha no reconocido: {date_str}")
                    return None

        if parsed_date:
            # Formato: %Y-%m-%dT%H:%M:%S.%f%z -> YYYY-MM-DDTHH:MM:SS.sss+ZZZZ
            # Asumimos inicio del día (00:00:00) y UTC (+0000)
            dt_obj = datetime.combine(parsed_date, datetime.min.time()) 
            jira_started_format = dt_obj.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            logger.info(f"Fecha parseada: '{date_str}' -> {jira_started_format}")
            return jira_started_format
        
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
            message: Mensaje del usuario.
            
        Returns:
            Respuesta del agente.
        """
        try:
            # Crear dependencias con contexto y la instancia del agente
            deps = JiraAgentDependencies(jira_client=self.jira_client, context=self.context, agent_instance=self)
            
            # Ejecutar el agente
            logger.info(f"Procesando mensaje: {message}")
            result = await self.agent.run(message, deps=deps)
            
            logger.info("Mensaje procesado correctamente")
            return result.output
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            return f"Lo siento, ha ocurrido un error: {str(e)}"
    
    def process_message_sync(self, message: str) -> str:
        """
        Versión sincrónica de process_message para facilitar la integración con Streamlit.
        
        Args:
            message: Mensaje del usuario.
            
        Returns:
            Respuesta del agente.
        """
        try:
            # Crear dependencias con contexto y la instancia del agente
            deps = JiraAgentDependencies(jira_client=self.jira_client, context=self.context, agent_instance=self)
            
            # Ejecutar el agente
            logger.info(f"Procesando mensaje sincrónico: {message}")
            result = self.agent.run_sync(message, deps=deps)
            
            logger.info("Mensaje procesado correctamente")
            return result.output
        except Exception as e:
            logger.error(f"Error al procesar mensaje sincrónico: {e}")
            return f"Lo siento, ha ocurrido un error: {str(e)}" 
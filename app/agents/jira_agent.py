import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field

from app.utils.jira_client import JiraClient
from app.utils.logger import get_logger
from app.agents.models import Issue, Worklog, Transition, AgentResponse
from app.config.config import OPENAI_API_KEY

# Configurar logger
logger = get_logger("jira_agent")

# Configuración global de pydanticai para usar la API key de OpenAI
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

@dataclass
class JiraAgentDependencies:
    """Dependencias para el agente de Jira."""
    jira_client: JiraClient

class JiraAgent:
    """Agente para interactuar con Jira de forma conversacional."""
    
    def __init__(self):
        """Inicializa el agente de Jira."""
        try:
            self.jira_client = JiraClient()
            
            # Crear el agente utilizando pydanticai
            self.agent = Agent(
                model="openai:gpt-4o",  # Modelo de OpenAI
                deps_type=JiraAgentDependencies,
                output_type=str,
                system_prompt=(
                    "Eres un asistente experto en Jira que ayuda a los usuarios a gestionar sus issues. "
                    "Puedes proporcionar información sobre issues asignadas, agregar registros de trabajo, "
                    "cambiar estados de issues y responder preguntas relacionadas con Jira. "
                    "Sé conciso, claro y siempre útil. Cuando necesites más información, pregunta al usuario. "
                    "Utiliza las herramientas disponibles para interactuar con Jira."
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
            Obtiene todas las issues asignadas al usuario actual.
            
            Returns:
                Lista de issues asignadas al usuario.
            """
            issues = ctx.deps.jira_client.get_my_issues()
            formatted_issues = []
            
            for issue in issues:
                formatted_issues.append({
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                })
            
            logger.info(f"Obtenidas {len(formatted_issues)} issues")
            return formatted_issues
        
        @self.agent.tool
        async def get_issue_details(ctx: RunContext[JiraAgentDependencies], issue_key: str) -> Dict[str, Any]:
            """
            Obtiene los detalles de una issue específica.
            
            Args:
                issue_key: Clave de la issue (ej. PSIMDESASW-111).
                
            Returns:
                Detalles de la issue.
            """
            issue = ctx.deps.jira_client.get_issue_details(issue_key)
            if not issue:
                logger.warning(f"Issue no encontrada: {issue_key}")
                return {"error": f"No se encontró la issue {issue_key}"}
            
            # Extraer datos relevantes
            result = {
                "key": issue["key"],
                "summary": issue["fields"]["summary"],
                "status": issue["fields"]["status"]["name"],
                "assignee": issue["fields"].get("assignee", {}).get("displayName", "Sin asignar"),
                "created": issue["fields"]["created"],
                "updated": issue["fields"]["updated"],
            }
            
            logger.info(f"Obtenidos detalles de issue {issue_key}")
            return result
        
        @self.agent.tool
        async def add_worklog(
            ctx: RunContext[JiraAgentDependencies],
            issue_key: str,
            time_spent: str,
            comment: Optional[str] = None,
            start_date: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Agrega un registro de trabajo a una issue.
            
            Args:
                issue_key: Clave de la issue (ej. PSIMDESASW-111).
                time_spent: Tiempo invertido en formato Jira (1h, 30m, etc.).
                comment: Comentario opcional para el registro de trabajo.
                start_date: Fecha opcional en formato YYYY-MM-DD. Si no se proporciona, se usa la fecha actual.
                
            Returns:
                Resultado de la operación.
            """
            # Convertir fecha si es necesario
            if start_date:
                try:
                    # Convertir a datetime si es un string
                    if isinstance(start_date, str):
                        start_date = datetime.strptime(start_date, "%Y-%m-%d").isoformat()
                except ValueError:
                    logger.error(f"Formato de fecha inválido: {start_date}")
                    return {"success": False, "error": "Formato de fecha inválido. Usa YYYY-MM-DD."}
            
            success = ctx.deps.jira_client.add_worklog(
                issue_key=issue_key,
                time_spent=time_spent,
                comment=comment,
                start_date=start_date
            )
            
            if success:
                logger.info(f"Worklog agregado a {issue_key}: {time_spent}")
                return {"success": True, "message": f"Tiempo registrado correctamente: {time_spent} en {issue_key}"}
            else:
                logger.error(f"Error al agregar worklog a {issue_key}")
                return {"success": False, "error": f"No se pudo registrar el tiempo en {issue_key}"}
        
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
                    # Convertir timestamp a fecha
                    worklog_date = datetime.fromisoformat(
                        worklog["started"].replace("Z", "+00:00")
                    ).date().isoformat()
                    
                    if worklog_date == target_date:
                        seconds = worklog["timeSpentSeconds"]
                        issue_seconds += seconds
                        issue_logs.append({
                            "time_spent": worklog["timeSpent"],
                            "seconds": seconds,
                            "comment": worklog.get("comment", "")
                        })
                
                # Solo incluir issues con worklogs en la fecha objetivo
                if issue_logs:
                    worklog_summary.append({
                        "issue_key": issue_key,
                        "summary": issue["fields"]["summary"],
                        "total_seconds": issue_seconds,
                        "total_formatted": self._format_seconds(issue_seconds),
                        "logs": issue_logs
                    })
                    total_seconds += issue_seconds
            
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
            # Crear dependencias
            deps = JiraAgentDependencies(jira_client=self.jira_client)
            
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
            # Crear dependencias
            deps = JiraAgentDependencies(jira_client=self.jira_client)
            
            # Ejecutar el agente
            logger.info(f"Procesando mensaje sincrónico: {message}")
            result = self.agent.run_sync(message, deps=deps)
            
            logger.info("Mensaje procesado correctamente")
            return result.output
        except Exception as e:
            logger.error(f"Error al procesar mensaje sincrónico: {e}")
            return f"Lo siento, ha ocurrido un error: {str(e)}" 
from atlassian import Jira
from app.config.config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
from app.utils.logger import get_logger

logger = get_logger("jira_client")

class JiraClient:
    """Cliente para interactuar con la API de Jira."""
    
    def __init__(self):
        """Inicializa el cliente de Jira."""
        try:
            self.jira = Jira(
                url=JIRA_URL,
                username=JIRA_USERNAME,
                password=JIRA_API_TOKEN,
                cloud=True  # La mayoría de las instancias de Jira actuales son en la nube
            )
            logger.info("Cliente Jira inicializado correctamente")
        except Exception as e:
            logger.error(f"Error al inicializar el cliente Jira: {e}")
            raise

    def get_my_issues(self):
        """
        Obtiene las issues asignadas al usuario actual.
        
        Returns:
            list: Lista de issues asignadas al usuario actual.
        """
        try:
            jql = f'assignee = currentUser() ORDER BY updated DESC'
            issues = self.jira.jql(jql)
            logger.info(f"Obtenidas {len(issues['issues'])} issues asignadas al usuario")
            return issues['issues']
        except Exception as e:
            logger.error(f"Error al obtener issues: {e}")
            return []
    
    def search_issues(self, search_term=None, max_results=10):
        """
        Busca issues por texto o clave, sin filtrar por asignación.
        
        Args:
            search_term (str, optional): Texto para buscar en el título/descripción o clave de issue.
            max_results (int, optional): Número máximo de resultados a devolver.
            
        Returns:
            list: Lista de issues que coinciden con la búsqueda.
        """
        try:
            jql = None
            if search_term:
                # Si parece una clave de issue (contiene guion), buscar exactamente
                if "-" in search_term:
                    jql = f'key = "{search_term}" OR text ~ "{search_term}"'
                # Si no, buscar en el texto
                else:
                    jql = f'text ~ "{search_term}*" OR summary ~ "{search_term}*"'
            else:
                # Si no hay término de búsqueda, obtener issues recientes
                jql = 'ORDER BY updated DESC'
            
            issues = self.jira.jql(jql, limit=max_results)
            logger.info(f"Búsqueda: '{search_term}' - Encontradas {len(issues['issues'])} issues")
            return issues['issues']
        except Exception as e:
            logger.error(f"Error al buscar issues '{search_term}': {e}")
            return []
    
    def add_worklog(self, issue_key, time_in_sec, comment=None, started=None):
        """
        Agrega un registro de trabajo a una issue usando el método issue_worklog.
        
        Args:
            issue_key (str): Clave de la issue.
            time_in_sec (int): Tiempo invertido en segundos.
            comment (str, optional): Comentario para el registro de trabajo.
            started (str, optional): Fecha/hora de inicio en formato ISO 8601 con offset (ej. YYYY-MM-DDTHH:MM:SS.sss+ZZZZ).
                                     Si es None, la API podría usar la hora actual.
            
        Returns:
            bool: True si se agregó correctamente, False en caso contrario.
        """
        try:
            # Llamar al método correcto documentado: issue_worklog
            # IMPORTANTE: Según la documentación, los argumentos son posicionales en este orden:
            # issue_worklog(issue_key, started, time_in_sec)
            self.jira.issue_worklog(issue_key, started, time_in_sec)
            
            # La documentación indica que issue_worklog no devuelve valor en éxito, lanza excepción en error.
            # Si llegamos aquí, asumimos éxito.
            logger.info(f"Worklog agregado a {issue_key}: {time_in_sec}s para {started}")
            
            # Si se proporcionó comentario y la llamada anterior no falló, intentar añadir comentario a la issue
            if comment:
                try:
                    # Como no parece haber soporte directo para comentarios en worklog, añadimos un comentario a la issue
                    self.jira.issue_add_comment(issue_key, f"Worklog ({time_in_sec} segundos): {comment}")
                    logger.info(f"Comentario añadido a {issue_key} para el worklog: '{comment}'")
                except Exception as comment_e:
                    logger.warning(f"No se pudo añadir el comentario '{comment}' para el worklog en {issue_key}: {comment_e}")

            return True
            
        except Exception as e:
            logger.error(f"Error al llamar a issue_worklog para {issue_key}: {e}")
            return False
    
    def get_issue_details(self, issue_key):
        """
        Obtiene los detalles de una issue.
        
        Args:
            issue_key (str): Clave de la issue.
            
        Returns:
            dict: Detalles de la issue.
        """
        try:
            issue = self.jira.issue(issue_key)
            logger.info(f"Obtenidos detalles de issue {issue_key}")
            return issue
        except Exception as e:
            logger.error(f"Error al obtener detalles de issue {issue_key}: {e}")
            return None
    
    def get_issue_worklogs(self, issue_key):
        """
        Obtiene los registros de trabajo de una issue.
        
        Args:
            issue_key (str): Clave de la issue.
            
        Returns:
            list: Lista de registros de trabajo.
        """
        try:
            worklogs = self.jira.get_issue_worklog(issue_key)
            logger.info(f"Obtenidos {len(worklogs['worklogs'])} worklogs para {issue_key}")
            return worklogs['worklogs']
        except Exception as e:
            logger.error(f"Error al obtener worklogs de {issue_key}: {e}")
            return []
    
    def get_issue_transitions(self, issue_key):
        """
        Obtiene las transiciones disponibles para una issue.
        
        Args:
            issue_key (str): Clave de la issue.
            
        Returns:
            list: Lista de transiciones disponibles.
        """
        try:
            transitions = self.jira.get_issue_transitions(issue_key)
            logger.info(f"Obtenidas {len(transitions['transitions'])} transiciones para {issue_key}")
            return transitions['transitions']
        except Exception as e:
            logger.error(f"Error al obtener transiciones de {issue_key}: {e}")
            return []
    
    def transition_issue(self, issue_key, transition_id):
        """
        Cambia el estado de una issue.
        
        Args:
            issue_key (str): Clave de la issue.
            transition_id (str): ID de la transición.
            
        Returns:
            bool: True si se cambió correctamente, False en caso contrario.
        """
        try:
            self.jira.issue_transition(issue_key, transition_id)
            logger.info(f"Issue {issue_key} transicionada a estado {transition_id}")
            return True
        except Exception as e:
            logger.error(f"Error al transicionar issue {issue_key}: {e}")
            return False 
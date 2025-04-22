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
    
    def add_worklog(self, issue_key, time_spent, comment=None, start_date=None):
        """
        Agrega un registro de trabajo a una issue.
        
        Args:
            issue_key (str): Clave de la issue.
            time_spent (str): Tiempo invertido en formato Jira (1h, 30m, etc).
            comment (str, optional): Comentario para el registro de trabajo.
            start_date (str, optional): Fecha de inicio en formato ISO.
            
        Returns:
            bool: True si se agregó correctamente, False en caso contrario.
        """
        try:
            result = self.jira.add_worklog(
                issue_key=issue_key,
                time_spent=time_spent,
                comment=comment,
                start=start_date
            )
            logger.info(f"Worklog agregado a {issue_key}: {time_spent}")
            return True
        except Exception as e:
            logger.error(f"Error al agregar worklog a {issue_key}: {e}")
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
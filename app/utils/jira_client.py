from atlassian import Jira
from app.config.config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
from app.utils.logger import get_logger
import os
import time
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Any, Union, Tuple

# Configurar logger
logger = get_logger("jira_client")

class JiraClient:
    """
    Cliente para interactuar con la API de Jira.
    
    Esta clase proporciona métodos para realizar operaciones comunes en Jira,
    incluyendo búsqueda de issues, gestión de worklogs, transiciones, y
    consultas a Tempo para registros de tiempo.
    
    Attributes:
        jira: Instancia de la clase Jira de la biblioteca atlassian-python-api.
        _cache: Diccionario para almacenamiento en caché de resultados de consultas.
        _cache_expiry: Tiempo de expiración de la caché en segundos.
    """
    
    def __init__(self, cache_expiry_seconds: int = 300):
        """
        Inicializa el cliente de Jira con autenticación y caché.
        
        Args:
            cache_expiry_seconds: Tiempo en segundos para la expiración de la caché (por defecto 5 minutos).
        
        Raises:
            Exception: Si hay un error en la inicialización del cliente Jira.
        """
        try:
            # Inicializar cliente Jira
            self.jira = Jira(
                url=JIRA_URL,
                username=JIRA_USERNAME,
                password=JIRA_API_TOKEN,
                cloud=True  # La mayoría de las instancias de Jira actuales son en la nube
            )
            
            # Inicializar sistema de caché para mejorar rendimiento
            self._cache = {}
            self._cache_expiry = cache_expiry_seconds
            
            logger.info(f"Cliente Jira inicializado correctamente: {JIRA_URL}")
        except Exception as e:
            logger.error(f"Error al inicializar el cliente Jira: {str(e)}")
            raise

    def _cache_get(self, key: str) -> Optional[Dict]:
        """
        Obtiene un valor de la caché si existe y no ha expirado.
        
        Args:
            key: Clave para buscar en la caché.
        
        Returns:
            El valor almacenado o None si no existe o ha expirado.
        """
        if key in self._cache:
            timestamp, value = self._cache[key]
            if time.time() - timestamp < self._cache_expiry:
                logger.debug(f"Caché hit para {key}")
                return value
            logger.debug(f"Caché expirada para {key}")
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """
        Almacena un valor en la caché con la marca de tiempo actual.
        
        Args:
            key: Clave para almacenar en la caché.
            value: Valor a almacenar.
        """
        self._cache[key] = (time.time(), value)
        logger.debug(f"Almacenado en caché: {key}")

    def get_my_issues(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene las issues asignadas al usuario actual.
        
        Args:
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            list: Lista de issues asignadas al usuario actual.
        """
        cache_key = "my_issues"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            jql = f'assignee = currentUser() ORDER BY updated DESC'
            issues = self.jira.jql(jql)
            
            if 'issues' in issues:
                result = issues['issues']
                logger.info(f"Obtenidas {len(result)} issues asignadas al usuario")
                self._cache_set(cache_key, result)
                return result
            else:
                logger.warning("Respuesta inesperada de Jira: 'issues' no encontrado en la respuesta")
                return []
        except Exception as e:
            logger.error(f"Error al obtener issues asignadas: {str(e)}")
            return []
    
    def search_issues(self, search_term: Optional[str] = None, max_results: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Busca issues por texto o clave, sin filtrar por asignación.
        
        Args:
            search_term: Texto para buscar en el título/descripción o clave de issue.
            max_results: Número máximo de resultados a devolver (por defecto 10).
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            list: Lista de issues que coinciden con la búsqueda.
        """
        cache_key = f"search_{search_term}_{max_results}"
        if use_cache and search_term:  # Solo usar caché si hay término de búsqueda
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
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
            
            if 'issues' in issues:
                result = issues['issues']
                logger.info(f"Búsqueda: '{search_term}' - Encontradas {len(result)} issues")
                
                if search_term:  # Solo almacenar en caché si hay término de búsqueda
                    self._cache_set(cache_key, result)
                
                return result
            else:
                logger.warning("Respuesta inesperada de Jira: 'issues' no encontrado en la respuesta")
                return []
        except Exception as e:
            logger.error(f"Error al buscar issues '{search_term}': {str(e)}")
            return []
    
    def add_worklog(self, issue_key: str, time_in_sec: int, comment: Optional[str] = None, started: Optional[str] = None) -> bool:
        """
        Agrega un registro de trabajo a una issue usando el método issue_worklog.
        
        Args:
            issue_key: Clave de la issue.
            time_in_sec: Tiempo invertido en segundos.
            comment: Comentario para el registro de trabajo.
            started: Fecha/hora de inicio en formato ISO 8601 con offset (ej. YYYY-MM-DDTHH:MM:SS.SSSZ).
                     Si es None, la API podría usar la hora actual.
                     IMPORTANTE: El offset de zona horaria (Z) debe estar en formato +0000 o -0300
                     sin dos puntos. El formato con dos puntos (+00:00) no es aceptado por Jira.
            
        Returns:
            bool: True si se agregó correctamente, False en caso contrario.
        """
        try:
            # Llamar al método correcto documentado: issue_worklog con argumentos posicionales
            self.jira.issue_worklog(issue_key, started, time_in_sec)
            
            # La documentación indica que issue_worklog no devuelve valor en éxito, lanza excepción en error.
            # Si llegamos aquí, asumimos éxito.
            logger.info(f"Worklog agregado a {issue_key}: {time_in_sec}s para {started}")
            
            # Invalidar la caché relacionada con esta issue
            self._invalidate_cache_for_issue(issue_key)
            
            # Si se proporcionó comentario y la llamada anterior no falló, intentar añadir comentario a la issue
            if comment:
                try:
                    # Como no parece haber soporte directo para comentarios en worklog, añadimos un comentario a la issue
                    self.jira.issue_add_comment(issue_key, f"Worklog ({time_in_sec} segundos): {comment}")
                    logger.info(f"Comentario añadido a {issue_key} para el worklog: '{comment}'")
                except Exception as comment_e:
                    logger.warning(f"No se pudo añadir el comentario '{comment}' para el worklog en {issue_key}: {str(comment_e)}")

            return True
            
        except Exception as e:
            logger.error(f"Error al llamar a issue_worklog para {issue_key}: {str(e)}")
            return False
    
    def _invalidate_cache_for_issue(self, issue_key: str) -> None:
        """
        Invalida entradas de caché relacionadas con una issue específica.
        
        Args:
            issue_key: Clave de la issue cuyos datos se deben invalidar en caché.
        """
        keys_to_remove = []
        for key in self._cache:
            if issue_key in key:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Caché invalidada para {key}")
    
    def get_issue_details(self, issue_key: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Obtiene los detalles completos de una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            dict: Detalles de la issue o None si no se encuentra o hay un error.
        """
        cache_key = f"issue_details_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            issue = self.jira.issue(issue_key)
            logger.info(f"Obtenidos detalles de issue {issue_key}")
            self._cache_set(cache_key, issue)
            return issue
        except Exception as e:
            logger.error(f"Error al obtener detalles de issue {issue_key}: {str(e)}")
            return None
    
    def get_issue_worklogs(self, issue_key: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene los registros de trabajo de una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            list: Lista de registros de trabajo o lista vacía si hay un error.
        """
        cache_key = f"worklogs_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            worklogs = self.jira.issue_get_worklog(issue_key)
            
            if 'worklogs' in worklogs:
                result = worklogs['worklogs']
                logger.info(f"Obtenidos {len(result)} worklogs para {issue_key}")
                self._cache_set(cache_key, result)
                return result
            else:
                logger.warning(f"Respuesta inesperada de Jira: 'worklogs' no encontrado para {issue_key}")
                return []
        except Exception as e:
            logger.error(f"Error al obtener worklogs de {issue_key}: {str(e)}")
            return []
    
    def get_issue_transitions(self, issue_key: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene las transiciones disponibles para una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            list: Lista de transiciones disponibles o lista vacía si hay un error.
        """
        cache_key = f"transitions_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            transitions = self.jira.get_issue_transitions(issue_key)
            
            if 'transitions' in transitions:
                result = transitions['transitions']
                logger.info(f"Obtenidas {len(result)} transiciones para {issue_key}")
                self._cache_set(cache_key, result)
                return result
            else:
                logger.warning(f"Respuesta inesperada de Jira: 'transitions' no encontrado para {issue_key}")
                return []
        except Exception as e:
            logger.error(f"Error al obtener transiciones de {issue_key}: {str(e)}")
            return []
    
    def transition_issue(self, issue_key: str, transition_id: str) -> bool:
        """
        Cambia el estado de una issue.
        
        Args:
            issue_key: Clave de la issue.
            transition_id: ID de la transición.
            
        Returns:
            bool: True si se cambió correctamente, False en caso contrario.
        """
        try:
            self.jira.issue_transition(issue_key, transition_id)
            logger.info(f"Issue {issue_key} transicionada a estado {transition_id}")
            
            # Invalidar la caché relacionada con esta issue
            self._invalidate_cache_for_issue(issue_key)
            
            return True
        except Exception as e:
            logger.error(f"Error al transicionar issue {issue_key}: {str(e)}")
            return False
    
    def get_total_time_spent(self, issue_key: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Calcula el tiempo total registrado para una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            dict: Diccionario con tiempo total en segundos y tiempo formateado (hh:mm:ss)
        """
        cache_key = f"total_time_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            # Obtener worklogs estándar de Jira
            worklog_data = self.jira.issue_get_worklog(issue_key)
            total_seconds = 0
            
            if 'worklogs' in worklog_data and worklog_data['worklogs']:
                # Sumar tiempo de cada worklog
                for worklog in worklog_data['worklogs']:
                    if 'timeSpentSeconds' in worklog:
                        total_seconds += worklog['timeSpentSeconds']
            
            # Convertir segundos a formato legible (hh:mm:ss)
            formatted_time = self._format_seconds(total_seconds)
            
            # Intentar obtener también los worklogs de Tempo si están disponibles
            try:
                tempo_result = self.get_tempo_worklogs(issue_key, use_cache=use_cache)
                tempo_seconds = tempo_result.get("total_seconds", 0)
                
                if tempo_seconds > 0:
                    tempo_formatted = tempo_result.get("total_formatted", "00:00:00")
                    
                    # Incluir la información de Tempo en el resultado
                    logger.info(f"Tiempo total registrado para {issue_key}: {formatted_time} (Jira) + {tempo_formatted} (Tempo)")
                    result = {
                        "jira_seconds": total_seconds,
                        "jira_formatted": formatted_time,
                        "tempo_seconds": tempo_seconds,
                        "tempo_formatted": tempo_formatted,
                        "total_seconds": total_seconds + tempo_seconds,
                        "total_formatted": self._format_seconds(total_seconds + tempo_seconds)
                    }
                    self._cache_set(cache_key, result)
                    return result
            except Exception as tempo_e:
                # Si hay error con Tempo, solo lo registramos pero continuamos
                logger.warning(f"No se pudieron obtener worklogs de Tempo para {issue_key}: {str(tempo_e)}")
            
            logger.info(f"Tiempo total registrado para {issue_key}: {formatted_time}")
            result = {
                "total_seconds": total_seconds,
                "total_formatted": formatted_time
            }
            self._cache_set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error al calcular tiempo total para {issue_key}: {str(e)}")
            return {
                "total_seconds": 0,
                "total_formatted": "00:00:00",
                "error": str(e)
            }
    
    def get_time_by_activity(self, issue_key: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Obtiene el tiempo registrado agrupado por actividades (basado en comentarios).
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            dict: Tiempo por actividad y tiempo total.
        """
        cache_key = f"time_by_activity_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            # Obtener todos los worklogs
            worklog_data = self.jira.issue_get_worklog(issue_key)
            activities = {}
            total_seconds = 0
            
            if 'worklogs' in worklog_data and worklog_data['worklogs']:
                # Procesar cada worklog
                for worklog in worklog_data['worklogs']:
                    if 'timeSpentSeconds' not in worklog:
                        continue
                        
                    time_spent = worklog['timeSpentSeconds']
                    total_seconds += time_spent
                    
                    # Obtener actividad del comentario o usar "Sin categorizar" como predeterminado
                    activity = "Sin categorizar"
                    if 'comment' in worklog and worklog['comment']:
                        # Si hay comentario, usar las primeras palabras como actividad
                        comment = worklog['comment'].strip()
                        # Extraer la primera línea o hasta 30 caracteres como identificador de actividad
                        activity_name = comment.split('\n')[0]
                        activity = (activity_name[:30] + '...') if len(activity_name) > 30 else activity_name
                    
                    # Agregar al diccionario de actividades
                    if activity not in activities:
                        activities[activity] = 0
                    activities[activity] += time_spent
            
            # Formatear los tiempos para cada actividad
            formatted_activities = {}
            for activity, seconds in activities.items():
                formatted_activities[activity] = {
                    "seconds": seconds,
                    "formatted": self._format_seconds(seconds),
                    "percentage": round((seconds / total_seconds * 100) if total_seconds > 0 else 0, 2)
                }
            
            # Intentar obtener también los worklogs de Tempo
            tempo_total = 0
            tempo_activities = {}
            
            try:
                tempo_result = self.get_tempo_worklogs(issue_key, use_cache=use_cache)
                tempo_worklogs = tempo_result.get("tempo_worklogs", [])
                
                if tempo_worklogs:
                    for tempo_log in tempo_worklogs:
                        if 'timeSpentSeconds' not in tempo_log:
                            continue
                            
                        time_spent = tempo_log['timeSpentSeconds']
                        tempo_total += time_spent
                        
                        # Obtener actividad de Tempo (puede estar en diferentes campos según configuración)
                        activity = "Sin categorizar (Tempo)"
                        if 'comment' in tempo_log and tempo_log['comment']:
                            comment = tempo_log['comment'].strip()
                            activity_name = comment.split('\n')[0]
                            activity = (activity_name[:30] + '...') if len(activity_name) > 30 else activity_name
                        elif 'description' in tempo_log and tempo_log['description']:
                            description = tempo_log['description'].strip()
                            activity_name = description.split('\n')[0]
                            activity = (activity_name[:30] + '...') if len(activity_name) > 30 else activity_name
                        
                        # Agregar al diccionario de actividades de Tempo
                        if activity not in tempo_activities:
                            tempo_activities[activity] = 0
                        tempo_activities[activity] += time_spent
                    
                    # Formatear actividades de Tempo
                    for activity, seconds in tempo_activities.items():
                        formatted_activities[activity] = {
                            "seconds": seconds,
                            "formatted": self._format_seconds(seconds),
                            "percentage": round((seconds / (total_seconds + tempo_total) * 100) if (total_seconds + tempo_total) > 0 else 0, 2)
                        }
                    
                    # Actualizar porcentajes para las actividades de Jira
                    if tempo_total > 0:
                        grand_total = total_seconds + tempo_total
                        for activity in activities.keys():
                            formatted_activities[activity]["percentage"] = round((activities[activity] / grand_total * 100) if grand_total > 0 else 0, 2)
            
            except Exception as tempo_e:
                logger.warning(f"No se pudieron obtener actividades de Tempo para {issue_key}: {str(tempo_e)}")
            
            # Preparar respuesta
            result = {
                "activities": formatted_activities,
                "total_seconds": total_seconds + tempo_total,
                "total_formatted": self._format_seconds(total_seconds + tempo_total)
            }
            
            logger.info(f"Actividades para {issue_key}: {len(formatted_activities)} diferentes")
            self._cache_set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error al obtener actividades para {issue_key}: {str(e)}")
            return {
                "activities": {},
                "total_seconds": 0,
                "total_formatted": "00:00:00",
                "error": str(e)
            }
    
    def get_tempo_worklogs(self, issue_key: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Obtiene los registros de trabajo de Tempo para una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            dict: Diccionario con los datos de worklogs de Tempo.
        """
        cache_key = f"tempo_worklogs_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            # Intentar con el método específico de Tempo
            try:
                tempo_worklogs = self.jira.tempo_timesheets_get_worklogs_by_issue(issue_key)
                if tempo_worklogs:
                    total_seconds = sum(worklog.get('timeSpentSeconds', 0) for worklog in tempo_worklogs)
                    formatted_time = self._format_seconds(total_seconds)
                    logger.info(f"Obtenidos {len(tempo_worklogs)} worklogs de Tempo para {issue_key}, tiempo total: {formatted_time}")
                    
                    result = {
                        "tempo_worklogs": tempo_worklogs,
                        "total_seconds": total_seconds,
                        "total_formatted": formatted_time
                    }
                    self._cache_set(cache_key, result)
                    return result
                else:
                    logger.info(f"No se encontraron worklogs de Tempo para {issue_key}")
            except Exception as e1:
                logger.warning(f"Error al usar tempo_timesheets_get_worklogs_by_issue para {issue_key}: {str(e1)}")
                
            # Intentar con la versión 4 de la API de Tempo que requiere más parámetros
            try:
                tempo_worklogs = self.jira.tempo_4_timesheets_find_worklogs(
                    taskKey=[issue_key]  # Enviar como lista según la documentación
                )
                if tempo_worklogs:
                    total_seconds = sum(worklog.get('timeSpentSeconds', 0) for worklog in tempo_worklogs)
                    formatted_time = self._format_seconds(total_seconds)
                    logger.info(f"Obtenidos {len(tempo_worklogs)} worklogs de Tempo v4 para {issue_key}, tiempo total: {formatted_time}")
                    
                    result = {
                        "tempo_worklogs": tempo_worklogs,
                        "total_seconds": total_seconds,
                        "total_formatted": formatted_time
                    }
                    self._cache_set(cache_key, result)
                    return result
                else:
                    logger.info(f"No se encontraron worklogs de Tempo v4 para {issue_key}")
            except Exception as e2:
                logger.warning(f"Error al usar tempo_4_timesheets_find_worklogs para {issue_key}: {str(e2)}")
            
            # Si llegamos aquí, no pudimos obtener datos de ninguna forma
            result = {
                "tempo_worklogs": [],
                "total_seconds": 0,
                "total_formatted": "00:00:00",
                "message": "No se encontraron datos de Tempo o no hay acceso a la API de Tempo"
            }
            self._cache_set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error general al obtener worklogs de Tempo para {issue_key}: {str(e)}")
            return {
                "tempo_worklogs": [],
                "total_seconds": 0,
                "total_formatted": "00:00:00",
                "error": str(e)
            }
    
    def clear_cache(self) -> None:
        """
        Limpia toda la caché del cliente.
        """
        self._cache = {}
        logger.info("Caché del cliente Jira limpiada completamente")
    
    def _format_seconds(self, seconds: int) -> str:
        """
        Formatea segundos a formato hh:mm:ss
        
        Args:
            seconds: Tiempo en segundos
            
        Returns:
            str: Tiempo formateado (hh:mm:ss)
        """
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    
    def get_issue_with_context7(self, issue_key: str) -> Dict[str, Any]:
        """
        Obtiene información detallada de una issue, optimizada para Context7.
        
        Incluye detalles adicionales como transiciones disponibles, worklogs y
        tiempo total, todo en una sola respuesta estructurada para Context7.
        
        Args:
            issue_key: Clave de la issue.
            
        Returns:
            dict: Datos completos de la issue para Context7.
        """
        try:
            # Obtener detalles básicos
            issue_details = self.get_issue_details(issue_key)
            
            if not issue_details:
                return {"error": f"No se pudo encontrar la issue {issue_key}"}
            
            # Obtener transiciones
            transitions = self.get_issue_transitions(issue_key)
            
            # Obtener worklogs
            worklogs = self.get_issue_worklogs(issue_key)
            
            # Calcular tiempo total
            time_spent = self.get_total_time_spent(issue_key)
            
            # Preparar respuesta enriquecida para Context7
            result = {
                "key": issue_key,
                "details": issue_details,
                "transitions": transitions,
                "worklogs": worklogs,
                "time_spent": time_spent,
                "retrieved_at": datetime.now().isoformat()
            }
            
            logger.info(f"Obtenida información enriquecida para Context7 de {issue_key}")
            return result
            
        except Exception as e:
            logger.error(f"Error al obtener datos de issue {issue_key} para Context7: {str(e)}")
            return {
                "error": f"Error al procesar datos para Context7: {str(e)}"
            }
    
    def search_issues_with_context7(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Realiza una búsqueda avanzada de issues con formato optimizado para Context7.
        
        Args:
            query: Texto o JQL para la búsqueda.
            max_results: Número máximo de resultados.
            
        Returns:
            dict: Resultados de búsqueda estructurados para Context7.
        """
        try:
            # Detectar si es JQL o texto simple
            is_jql = any(op in query for op in ["=", "~", ">", "<", ">=", "<=", "ORDER BY", "AND", "OR", "NOT", "IN"])
            
            if is_jql:
                # Es JQL, usarlo directamente
                jql = query
            else:
                # Es texto simple, convertir a JQL
                if "-" in query:
                    jql = f'key = "{query}" OR text ~ "{query}"'
                else:
                    jql = f'text ~ "{query}*" OR summary ~ "{query}*"'
            
            # Realizar búsqueda
            issues = self.jira.jql(jql, limit=max_results)
            
            # Preparar respuesta para Context7
            if 'issues' in issues:
                issues_list = issues['issues']
                
                # Enriquecer los resultados con información adicional útil
                result = {
                    "query": query,
                    "jql_used": jql,
                    "total_found": issues.get('total', len(issues_list)),
                    "max_results": max_results,
                    "issues": issues_list,
                    "retrieved_at": datetime.now().isoformat()
                }
                
                logger.info(f"Búsqueda Context7: '{query}' - Encontradas {len(issues_list)} issues")
                return result
            else:
                logger.warning(f"Respuesta inesperada de búsqueda Context7 para '{query}'")
                return {
                    "query": query,
                    "jql_used": jql,
                    "error": "No se encontraron issues o formato de respuesta inesperado",
                    "issues": []
                }
                
        except Exception as e:
            logger.error(f"Error en búsqueda Context7 '{query}': {str(e)}")
            return {
                "query": query,
                "error": str(e),
                "issues": []
            }
    
    def add_comment(self, issue_key: str, comment: str, visibility: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Agrega un comentario a una issue.
        
        Args:
            issue_key: Clave de la issue (ej. PROJ-123).
            comment: Texto del comentario a añadir.
            visibility: Diccionario con la visibilidad del comentario.
                        Ejemplo: {"type": "group", "value": "jira-developers"}
        
        Returns:
            dict: Información sobre el comentario agregado o error.
        """
        try:
            # Validación básica de entrada
            if not issue_key or not comment:
                logger.warning("Se requiere issue_key y comment para añadir un comentario")
                return {
                    "success": False,
                    "error": "Se requiere issue_key y comment"
                }
            
            # Llamar a la API de Jira para añadir el comentario
            result = self.jira.issue_add_comment(issue_key, comment, visibility=visibility)
            
            # Invalidar caché relacionada con esta issue
            self._invalidate_cache_for_issue(issue_key)
            
            logger.info(f"Comentario añadido a {issue_key}: '{comment[:50]}{'...' if len(comment) > 50 else ''}'")
            
            return {
                "success": True,
                "issue_key": issue_key,
                "comment_id": result.get('id') if isinstance(result, dict) else None,
                "message": "Comentario añadido correctamente"
            }
            
        except Exception as e:
            logger.error(f"Error al añadir comentario a {issue_key}: {str(e)}")
            return {
                "success": False,
                "issue_key": issue_key,
                "error": str(e)
            }
    
    def get_comments(self, issue_key: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene todos los comentarios de una issue.
        
        Args:
            issue_key: Clave de la issue.
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            list: Lista de comentarios de la issue.
        """
        cache_key = f"comments_{issue_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            # Obtener comentarios usando la API de Jira
            comments_data = self.jira.issue_get_comments(issue_key)
            
            if isinstance(comments_data, dict) and 'comments' in comments_data:
                comments = comments_data['comments']
                logger.info(f"Obtenidos {len(comments)} comentarios para {issue_key}")
                self._cache_set(cache_key, comments)
                return comments
            else:
                logger.warning(f"Formato inesperado de respuesta para comentarios de {issue_key}")
                return []
                
        except Exception as e:
            logger.error(f"Error al obtener comentarios de {issue_key}: {str(e)}")
            return []
    
    def get_issue_url(self, issue_key: str) -> str:
        """
        Genera la URL completa para una issue de Jira que permite acceso directo vía navegador.
        
        Args:
            issue_key: Clave de la issue (ej. PSIMDESASW-1234).
            
        Returns:
            str: URL completa para acceder a la issue en el navegador.
        """
        # Asegurar que la URL base no termina con barra
        base_url = JIRA_URL.rstrip('/')
        
        # Generar la URL siguiendo el formato estándar de Jira: {JIRA_URL}/browse/{ISSUE_KEY}
        issue_url = f"{base_url}/browse/{issue_key}"
        
        logger.debug(f"URL generada para {issue_key}: {issue_url}")
        return issue_url
    
    def get_my_worklogs_yesterday(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Obtiene los registros de trabajo creados por el usuario actual ayer.
        
        Esta función usa JQL para buscar issues donde el usuario actual registró tiempo ayer,
        y luego filtra los worklogs para incluir solo los que efectivamente fueron creados ayer
        y por el usuario actual.
        
        Args:
            use_cache: Si se debe usar la caché (por defecto True).
            
        Returns:
            dict: Diccionario con información sobre los worklogs de ayer y el tiempo total.
        """
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        cache_key = f"my_worklogs_{yesterday}"
        
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            # Obtener información del usuario actual
            try:
                current_user = self.jira.myself()
                current_username = current_user.get('name', '')
                current_account_id = current_user.get('accountId', '')
                current_display_name = current_user.get('displayName', '')
                
                logger.info(f"Usuario actual: {current_display_name} (username: {current_username}, accountId: {current_account_id})")
            except Exception as e:
                logger.warning(f"No se pudo obtener información del usuario actual: {str(e)}")
                current_username = JIRA_USERNAME
                current_account_id = ''
                current_display_name = ''
            
            # JQL para encontrar issues donde el usuario registró tiempo ayer
            jql = 'worklogAuthor = currentUser() AND worklogDate = "-1d"'
            
            # Realizar la búsqueda, solicitando específicamente el campo worklog
            issues = self.jira.jql(jql, fields=["summary", "worklog"])
            
            logger.info(f"Buscando worklogs creados ayer ({yesterday}) por el usuario actual")
            
            if 'issues' not in issues:
                logger.warning("Respuesta inesperada de Jira: 'issues' no encontrado en la respuesta")
                return {
                    "success": False,
                    "error": "Respuesta inesperada de Jira: 'issues' no encontrado",
                    "date": yesterday
                }
            
            total_seconds = 0
            total_formatted = "00:00:00"
            filtered_worklogs = []
            
            # Procesar cada issue que cumple con el criterio JQL
            for issue in issues['issues']:
                issue_key = issue.get('key', 'Sin clave')
                summary = issue.get('fields', {}).get('summary', 'Sin título')
                
                # Obtener worklogs de la issue
                worklog_data = issue.get('fields', {}).get('worklog', {})
                
                # Verificar si hay worklogs en la respuesta
                if not worklog_data or 'worklogs' not in worklog_data:
                    # Si no hay worklogs en la respuesta, obtenerlos directamente
                    try:
                        worklogs = self.get_issue_worklogs(issue_key)
                    except Exception as e:
                        logger.error(f"Error al obtener worklogs adicionales para {issue_key}: {str(e)}")
                        continue
                else:
                    worklogs = worklog_data['worklogs']
                
                # Filtrar worklogs para incluir solo los de ayer y del usuario actual
                for worklog in worklogs:
                    # Verificar si el autor es el usuario actual
                    author = worklog.get('author', {})
                    author_name = author.get('name', '')
                    author_account_id = author.get('accountId', '')
                    author_display_name = author.get('displayName', '')
                    
                    # Verificar que el autor coincida con el usuario actual
                    is_current_user = False
                    if current_account_id and author_account_id:
                        # Preferir comparación por accountId (más confiable)
                        is_current_user = current_account_id == author_account_id
                    elif current_username and author_name:
                        # Comparación por username como fallback
                        is_current_user = current_username == author_name
                    elif current_display_name and author_display_name:
                        # Comparación por displayName como último recurso
                        is_current_user = current_display_name == author_display_name
                    
                    if not is_current_user:
                        logger.debug(f"Saltando worklog que no pertenece al usuario actual: {author_display_name}")
                        continue
                    
                    # Obtener y formatear la fecha del worklog
                    started = worklog.get('started', '')
                    if started and 'T' in started:
                        worklog_date = started.split('T')[0]  # Extraer solo la fecha (YYYY-MM-DD)
                    else:
                        worklog_date = ''
                    
                    # Si la fecha coincide con ayer
                    if worklog_date == yesterday:
                        # Recopilar datos relevantes del worklog
                        time_spent_seconds = worklog.get('timeSpentSeconds', 0)
                        time_spent = worklog.get('timeSpent', '')
                        comment = worklog.get('comment', 'Sin comentario')
                        
                        # Añadir al resultado
                        filtered_worklogs.append({
                            "issue_key": issue_key,
                            "issue_summary": summary,
                            "issue_url": self.get_issue_url(issue_key),
                            "started": started,
                            "time_spent_seconds": time_spent_seconds,
                            "time_spent": time_spent,
                            "comment": comment,
                            "author": author_display_name
                        })
                        
                        # Actualizar total
                        total_seconds += time_spent_seconds
            
            # Formatear tiempo total
            if total_seconds > 0:
                total_formatted = self._format_seconds(total_seconds)
            
            # Preparar resultado
            result = {
                "success": True,
                "date": yesterday,
                "count": len(filtered_worklogs),
                "total_seconds": total_seconds,
                "total_formatted": total_formatted,
                "worklogs": filtered_worklogs,
                "username": current_display_name or current_username
            }
            
            logger.info(f"Encontrados {len(filtered_worklogs)} worklogs para el {yesterday}, total: {total_formatted}")
            
            # Almacenar en caché
            self._cache_set(cache_key, result)
            
            return result
            
        except Exception as e:
            error_msg = f"Error al obtener worklogs de ayer: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "date": yesterday
            } 
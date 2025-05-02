from atlassian import Jira
from app.config.config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
from app.utils.logger import get_logger
import os
import time
from datetime import datetime, timedelta, date
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
    
    def get_user_worklogs_for_date(self, date_str: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Obtiene los worklogs de un usuario para una fecha específica utilizando
        la API de Jira para obtener directamente el tiempo registrado.
        
        Args:
            date_str: Fecha en formato YYYY-MM-DD
            use_cache: Si se debe usar la caché
            
        Returns:
            dict: Información de los worklogs
        """
        cache_key = f"user_worklogs_{date_str}"
        
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
                
        try:
            # Obtener información del usuario actual
            current_user = self.jira.myself()
            current_username = current_user.get('name', '')
            current_account_id = current_user.get('accountId', '')
            current_display_name = current_user.get('displayName', '')
            
            logger.info(f"Obteniendo worklogs para {current_display_name} en la fecha {date_str}")
            
            # Construir la fecha con formato ISO 8601 (requerido por Jira)
            start_date = f"{date_str}T00:00:00.000+0000"
            end_date = f"{date_str}T23:59:59.999+0000"
            
            # API para obtener los worklogs del usuario en un rango de fechas
            endpoint = "/rest/api/2/worklog/updated"
            
            # Consultar la API para obtener IDs de worklogs actualizados
            since = 0  # Desde el primer worklog
            all_worklog_ids = []
            
            while True:
                # Parámetros para obtener IDs de worklogs actualizados
                params = {"since": since}
                
                response = self.jira.get(endpoint, params=params)
                
                if not response or 'values' not in response:
                    break
                    
                worklog_updates = response.get('values', [])
                if not worklog_updates:
                    break
                    
                # Actualizar el valor 'since' para la próxima iteración
                since = response.get('lastPage', since)
                if since == response.get('lastPage', since):
                    # No hay más páginas
                    break
                    
                # Guardar los IDs de los worklogs
                for update in worklog_updates:
                    worklog_id = update.get('worklogId')
                    if worklog_id:
                        all_worklog_ids.append(worklog_id)
                        
            logger.info(f"Encontrados {len(all_worklog_ids)} IDs de worklogs totales")
            
            # Obtener los detalles de cada worklog y filtrar por fecha y usuario
            filtered_worklogs = []
            total_seconds = 0
            issue_data = {}  # Para almacenar información de las issues
            
            for worklog_id in all_worklog_ids:
                worklog_endpoint = f"/rest/api/2/worklog/{worklog_id}"
                try:
                    worklog = self.jira.get(worklog_endpoint)
                    
                    # Verificar si el worklog es del usuario actual
                    author = worklog.get('author', {})
                    author_account_id = author.get('accountId', '')
                    
                    is_current_user = author_account_id == current_account_id
                    if not is_current_user:
                        continue
                        
                    # Verificar si el worklog es de la fecha solicitada
                    started = worklog.get('started', '')
                    if not started or 'T' not in started:
                        continue
                        
                    worklog_date = started.split('T')[0]
                    if worklog_date != date_str:
                        continue
                        
                    # Si llegamos aquí, el worklog cumple ambos criterios
                    issue_id = worklog.get('issueId', '')
                    if not issue_id:
                        continue
                        
                    # Si es la primera vez que vemos esta issue, obtener su información
                    if issue_id not in issue_data:
                        try:
                            issue_info = self.jira.issue(issue_id)
                            issue_key = issue_info.get('key', '')
                            issue_summary = issue_info.get('fields', {}).get('summary', 'Sin título')
                            issue_data[issue_id] = {
                                'key': issue_key,
                                'summary': issue_summary
                            }
                        except Exception as e:
                            logger.warning(f"Error al obtener información de la issue {issue_id}: {str(e)}")
                            issue_data[issue_id] = {
                                'key': f"ISSUE-{issue_id}",
                                'summary': 'Sin título'
                            }
                    
                    # Obtener información de la issue
                    issue_key = issue_data[issue_id]['key']
                    issue_summary = issue_data[issue_id]['summary']
                    
                    # Recopilar datos relevantes del worklog
                    author_display_name = author.get('displayName', '')
                    time_spent = worklog.get('timeSpent', '')
                    time_spent_seconds = worklog.get('timeSpentSeconds', 0)
                    comment = worklog.get('comment', 'Sin comentario')
                    
                    logger.info(f"Encontrado worklog: {issue_key} - {time_spent} - {comment}")
                    
                    # Añadir al resultado
                    filtered_worklogs.append({
                        "issue_key": issue_key,
                        "issue_summary": issue_summary,
                        "issue_url": self.get_issue_url(issue_key),
                        "started": started,
                        "time_spent_seconds": time_spent_seconds,
                        "time_spent": time_spent,
                        "comment": comment,
                        "author": author_display_name
                    })
                    
                    # Actualizar total
                    total_seconds += time_spent_seconds
                    
                except Exception as e:
                    logger.warning(f"Error al procesar worklog {worklog_id}: {str(e)}")
                    
            # Formatear tiempo total
            total_formatted = self._format_seconds(total_seconds) if total_seconds > 0 else "00:00:00"
            
            # Preparar resultado
            result = {
                "success": True,
                "date": date_str,
                "count": len(filtered_worklogs),
                "total_seconds": total_seconds,
                "total_formatted": total_formatted,
                "worklogs": filtered_worklogs,
                "username": current_display_name or current_username
            }
            
            logger.info(f"Encontrados {len(filtered_worklogs)} worklogs para {date_str}, total: {total_formatted}")
            
            # Almacenar en caché
            self._cache_set(cache_key, result)
            
            return result
            
        except Exception as e:
            error_msg = f"Error al obtener worklogs para la fecha {date_str}: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "date": date_str
            }
    
    def get_my_worklogs_for_date(self, date_str: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Obtiene los registros de trabajo creados por el usuario actual para una fecha específica.

        Args:
            date_str: Fecha en formato YYYY-MM-DD.
            use_cache: Si se debe usar la caché (por defecto True).

        Returns:
            dict: Diccionario con información sobre los worklogs de la fecha especificada.
        """
        # Update cache key
        cache_key = f"my_worklogs_{date_str}_v4" # Increment version
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached

        try:
            # 1. Obtener información del usuario actual
            try:
                current_user = self.jira.myself()
                current_account_id = current_user.get('accountId')
                current_display_name = current_user.get('displayName', '')
                if not current_account_id:
                    logger.error("No se pudo obtener el accountId del usuario actual. No se puede continuar.")
                    return {
                        "success": False,
                        "error": "No se pudo obtener el accountId del usuario actual.",
                        "date": date_str 
                    }
                logger.info(f"Usuario actual: {current_display_name} (accountId: {current_account_id})")
            except Exception as e:
                logger.error(f"Error crítico al obtener información del usuario actual: {str(e)}")
                return {
                    "success": False,
                    "error": f"Error al obtener información del usuario actual: {str(e)}",
                    "date": date_str
                }

            # 2. JQL para encontrar issues candidatas - MODIFICADO para usar date_str
            # Antes: jql = 'worklogAuthor = currentUser() AND worklogDate = "-1d"'
            jql = f'worklogAuthor = currentUser() AND worklogDate = "{date_str}"'
            logger.info(f"Ejecutando consulta JQL inicial para encontrar issues candidatas: {jql}")
            # Pedir solo la clave (key) y el resumen (summary) para identificar la issue
            initial_search_results = self.jira.jql(jql, fields=["key", "summary"], limit=200) 
            if 'issues' not in initial_search_results:
                logger.warning(f"Respuesta inesperada de Jira (búsqueda inicial para {date_str}): 'issues' no encontrado")
                return {
                    "success": False,
                    "error": f"Respuesta inesperada de Jira: 'issues' no encontrado en búsqueda inicial para {date_str}",
                    "date": date_str 
                }

            candidate_issues = initial_search_results['issues']
            total_candidate_issues = len(candidate_issues)
            # Update log message
            logger.info(f"Encontradas {total_candidate_issues} issues candidatas con worklogs del usuario para {date_str}.")

            total_seconds = 0
            # Renombrar lista para claridad
            final_filtered_worklogs = [] 
            processed_issues_keys = set()
            # 3. Iterar sobre las issues candidatas 
            for issue_data in candidate_issues:
                issue_key = issue_data.get('key')
                # Obtener resumen para logs y posible uso futuro
                issue_summary = issue_data.get('fields', {}).get('summary', 'Sin título') 
                if not issue_key:
                    logger.warning("Issue encontrada sin key en la respuesta JQL, saltando.")
                    continue

                logger.info(f"Procesando issue candidata: {issue_key} - {issue_summary}")
                processed_issues_keys.add(issue_key)
                
                # Obtener y filtrar worklogs para ESTA issue específica
                try:
                    # Llamar al nuevo método auxiliar (a crear)
                    worklogs_for_this_issue = self._get_and_filter_worklogs_for_issue_date(
                        issue_key, date_str, current_account_id
                    )
                    
                    # Procesar los worklogs devueltos (ya filtrados)
                    for worklog in worklogs_for_this_issue:
                        time_spent_seconds = worklog.get('timeSpentSeconds', 0)
                        # Añadir datos adicionales necesarios para el reporte final
                        worklog['issue_key'] = issue_key 
                        worklog['issue_summary'] = issue_summary
                        worklog['issue_url'] = self.get_issue_url(issue_key)
                        # El author ya debería estar en el worklog devuelto
                        # worklog['author'] = worklog.get('author', {}).get('displayName', current_display_name)
                        
                        final_filtered_worklogs.append(worklog)
                        total_seconds += time_spent_seconds
                        
                    logger.info(f"  Procesamiento de {issue_key} completado. Se añadieron {len(worklogs_for_this_issue)} worklogs filtrados.")
                except Exception as filter_e:
                    logger.error(f"  Error obteniendo/filtrando worklogs para {issue_key} en fecha {date_str}: {filter_e}")
                    continue # Continuar con la siguiente issue
            # 6. Formatear resultado final
            total_formatted = self._format_seconds(total_seconds) if total_seconds > 0 else "00:00:00"
            # Usar la lista final acumulada
            final_count = len(final_filtered_worklogs) 
            result = {
                "success": True,
                "date": date_str,
                "count": final_count,
                "total_seconds": total_seconds,
                "total_formatted": total_formatted,
                # Usar la lista final acumulada
                "worklogs": final_filtered_worklogs, 
                "username": current_display_name,
                "processed_issues": list(processed_issues_keys),
                "candidate_issue_count": total_candidate_issues
            }
            # Update log message
            logger.info(f"Proceso completado. Encontrados {final_count} worklogs filtrados para el {date_str}, total: {total_formatted}. Issues candidatas procesadas: {len(processed_issues_keys)}.")
            # Almacenar en caché
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            # Update log message and error return
            error_msg = f"Error general al obtener worklogs para {date_str}: {str(e)}"
            logger.exception(error_msg) # Usar exception para incluir traceback
            return {
                "success": False,
                "error": error_msg,
                "date": date_str # Use date_str in error return
            }
        
            
    # --- NUEVO MÉTODO AUXILIAR --- 
    def _get_and_filter_worklogs_for_issue_date(self, issue_key: str, date_str: str, user_account_id: str) -> List[Dict]:
        """
        Obtiene TODOS los worklogs para una issue usando paginación y luego los filtra 
        manualmente por fecha y autor.
        
        Args:
            issue_key: Clave de la issue.
            date_str: Fecha objetivo (YYYY-MM-DD).
            user_account_id: AccountId del usuario a filtrar.
            
        Returns:
            Lista de diccionarios de worklog filtrados.
        """
        logger.info(f"  Aux: Iniciando obtención paginada de worklogs para {issue_key} para filtrar por fecha={date_str}, autor={user_account_id}")
        all_issue_worklogs = [] 
        start_at = 0
        max_results = 100 # Tamaño de página razonable, ajustable si es necesario
        total_worklogs_reported = -1 # Para saber cuándo parar
        worklogs_endpoint = f"/rest/api/3/issue/{issue_key}/worklog"

        # --- Inicio: Bucle de Paginación --- 
        while True:
            params = {'startAt': start_at, 'maxResults': max_results}
            logger.debug(f"    Aux Paginación: Obteniendo página startAt={start_at}, maxResults={max_results}")
            try:
                response_data = self.jira.get(worklogs_endpoint, params=params)
                
                if not isinstance(response_data, dict):
                    logger.warning(f"    Aux Paginación: Respuesta inesperada (no dict) para {issue_key} en startAt={start_at}")
                    break # Salir del bucle si la respuesta no es válida
                    
                worklogs_page = response_data.get('worklogs', [])
                current_page_size = len(worklogs_page)
                # Obtener el total real la primera vez
                if total_worklogs_reported == -1:
                    total_worklogs_reported = response_data.get('total', 0)
                    logger.info(f"  Aux: Issue {issue_key} reporta un total de {total_worklogs_reported} worklogs.")
                
                if not worklogs_page:
                    logger.debug(f"    Aux Paginación: Página vacía encontrada en startAt={start_at}. Terminando paginación.")
                    break
                
                all_issue_worklogs.extend(worklogs_page)
                logger.debug(f"    Aux Paginación: Añadidos {current_page_size} worklogs. Total acumulado: {len(all_issue_worklogs)}")
                
                start_at += current_page_size
                
                # Condición de salida
                if start_at >= total_worklogs_reported:
                    logger.debug(f"    Aux Paginación: Paginación completada (startAt >= total).")
                    break
                    
            except Exception as e:
                logger.error(f"  Aux: Error durante paginación para {issue_key} en startAt={start_at}: {e}")
                # Considerar si reintentar o abortar. Por ahora, abortamos la paginación.
                break 
        # --- Fin: Bucle de Paginación --- 

        logger.info(f"  Aux: Obtenidos {len(all_issue_worklogs)} worklogs totales para {issue_key} tras paginación.")

        # --- Inicio: Filtrado Manual (sin cambios) --- 
        filtered_worklogs = []
        try:
            target_date_obj = date.fromisoformat(date_str)
        except ValueError:
            logger.error(f"  Aux: Error interno, date_str '{date_str}' no es YYYY-MM-DD")
            return []
            
        for worklog in all_issue_worklogs:
            try:
                # 1. Filtrado por Fecha
                started = worklog.get('started', '')
                if not started:
                    continue
                worklog_dt = datetime.strptime(started, '%Y-%m-%dT%H:%M:%S.%f%z')
                if worklog_dt.date() != target_date_obj:
                    continue
                    
                # 2. Filtrado por Usuario
                if user_account_id:
                    author = worklog.get('author', {})
                    if author.get('accountId') != user_account_id:
                        continue
                        
                # Pasa ambos filtros
                filtered_worklogs.append(worklog)
                
            except ValueError as parse_error: # Catch date parsing errors inside loop
                 worklog_id = worklog.get('id', 'N/A')
                 logger.warning(f"    [WL-{worklog_id}] Ignorando worklog: Error parseando fecha ('{started}'): {parse_error}")
                 continue
            except Exception as loop_error: # Catch unexpected errors inside loop
                 worklog_id = worklog.get('id', 'N/A')
                 logger.error(f"    [WL-{worklog_id}] Error inesperado procesando worklog: {loop_error}")
                 continue # Skip to next worklog on error
                 
        logger.info(f"  Aux: Filtrado manual para {issue_key} resultó en {len(filtered_worklogs)} worklogs.")
        return filtered_worklogs
        
    # --- FIN MÉTODO AUXILIAR ---
    
    # La función get_issue_worklogs_for_date fue eliminada/reemplazada
    
    # ... (resto de los métodos de la clase JiraClient) ... 
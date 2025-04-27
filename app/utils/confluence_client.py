from atlassian import Confluence
from app.config.config import CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN
from app.utils.logger import get_logger
import os
import time
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Any, Union, Tuple

# Configurar logger
logger = get_logger("confluence_client")

class ConfluenceClient:
    """
    Cliente para interactuar con la API de Confluence.
    
    Esta clase proporciona métodos para realizar operaciones comunes en Confluence,
    incluyendo búsqueda de contenido, obtención de páginas, y consulta de espacios.
    
    Attributes:
        confluence: Instancia de la clase Confluence de la biblioteca atlassian-python-api.
        _cache: Diccionario para almacenamiento en caché de resultados de consultas.
        _cache_expiry: Tiempo de expiración de la caché en segundos.
    """
    
    def __init__(self, cache_expiry_seconds: int = 300):
        """
        Inicializa el cliente de Confluence con autenticación y caché.
        
        Args:
            cache_expiry_seconds: Tiempo en segundos para la expiración de la caché (por defecto 5 minutos).
        
        Raises:
            Exception: Si hay un error en la inicialización del cliente Confluence.
        """
        try:
            # Inicializar cliente Confluence
            self.confluence = Confluence(
                url=CONFLUENCE_URL,
                username=CONFLUENCE_USERNAME,
                password=CONFLUENCE_API_TOKEN,
                cloud=True  # La mayoría de las instancias de Confluence actuales son en la nube
            )
            
            # Guardar la URL base para construcción de enlaces completos
            self.base_url = CONFLUENCE_URL.rstrip("/")
            if not self.base_url.endswith("/wiki"):
                self.base_url += "/wiki"
            
            # Inicializar sistema de caché para mejorar rendimiento
            self._cache = {}
            self._cache_expiry = cache_expiry_seconds
            
            # Los espacios que queremos consultar
            self.target_spaces = ["PSIMDESASW", "ITIndustrial"]
            
            logger.info(f"Cliente Confluence inicializado correctamente: {CONFLUENCE_URL}")
        except Exception as e:
            logger.error(f"Error al inicializar el cliente Confluence: {str(e)}")
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

    def _get_full_url(self, relative_url: str) -> str:
        """
        Convierte una URL relativa en una URL completa.
        
        Args:
            relative_url: URL relativa que puede comenzar con "/" o no.
            
        Returns:
            str: URL completa.
        """
        if not relative_url:
            return ""
            
        # Asegurarse de que la URL relativa comienza con "/"
        if not relative_url.startswith("/"):
            relative_url = "/" + relative_url
            
        return f"{self.base_url}{relative_url}"
    
    def get_all_spaces(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene todos los espacios disponibles en Confluence.
        
        Args:
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            list: Lista de espacios en Confluence.
        """
        cache_key = "all_spaces"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            spaces = self.confluence.get_all_spaces(start=0, limit=500, expand='description.plain,homepage')
            if 'results' in spaces:
                result = spaces['results']
                logger.info(f"Obtenidos {len(result)} espacios de Confluence")
                self._cache_set(cache_key, result)
                return result
            else:
                logger.warning("Respuesta inesperada de Confluence: 'results' no encontrado en la respuesta")
                return []
        except Exception as e:
            logger.error(f"Error al obtener espacios: {str(e)}")
            return []
    
    def get_space(self, space_key: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Obtiene información detallada sobre un espacio específico.
        
        Args:
            space_key: Clave del espacio a obtener.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            dict: Información del espacio o None si no se encuentra.
        """
        cache_key = f"space_{space_key}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            space = self.confluence.get_space(space_key, expand='description.plain,homepage')
            logger.info(f"Obtenida información para el espacio: {space_key}")
            self._cache_set(cache_key, space)
            return space
        except Exception as e:
            logger.error(f"Error al obtener espacio {space_key}: {str(e)}")
            return None
    
    def get_space_content(self, space_key: str, content_type: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene el contenido de un espacio específico.
        
        Args:
            space_key: Clave del espacio.
            content_type: Tipo de contenido (page, blogpost, etc). Si es None, obtiene todo.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            list: Lista de contenido en el espacio.
        """
        cache_key = f"space_content_{space_key}_{content_type}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            content = self.confluence.get_space_content(
                space_key=space_key,
                depth="all",
                start=0,
                limit=500,
                content_type=content_type,
                expand="body.storage"
            )
            
            if 'page' in content and 'results' in content['page']:
                result = content['page']['results']
                # Añadir URLs completas
                for item in result:
                    if '_links' in item and 'webui' in item['_links']:
                        item['_links']['webui_full'] = self._get_full_url(item['_links']['webui'])
                
                logger.info(f"Obtenidos {len(result)} elementos de contenido en el espacio {space_key}")
                self._cache_set(cache_key, result)
                return result
            else:
                logger.warning(f"Respuesta inesperada de Confluence para el espacio {space_key}")
                return []
        except Exception as e:
            logger.error(f"Error al obtener contenido del espacio {space_key}: {str(e)}")
            return []
    
    def search_content(self, query: str, spaces: Optional[List[str]] = None, max_results: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Busca contenido en Confluence usando CQL.
        
        Args:
            query: Término de búsqueda.
            spaces: Lista de espacios donde buscar. Si es None, usa los espacios objetivo por defecto.
            max_results: Número máximo de resultados.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            list: Lista de resultados de la búsqueda.
        """
        # Si no se proporcionan espacios, usar los espacios objetivo
        if spaces is None:
            spaces = self.target_spaces
        
        space_clause = " OR ".join([f"space = {space}" for space in spaces])
        cql = f"text ~ \"{query}\" AND ({space_clause})"
        
        cache_key = f"search_{query}_{','.join(spaces)}_{max_results}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            results = self.confluence.cql(
                cql=cql,
                start=0,
                limit=max_results,
                expand="body.storage,version",
                include_archived_spaces=False,
                excerpt=True
            )
            
            if 'results' in results:
                search_results = results['results']
                # Añadir URLs completas
                for result in search_results:
                    if 'url' in result:
                        result['full_url'] = self._get_full_url(result['url'])
                
                logger.info(f"Búsqueda '{query}': Encontrados {len(search_results)} resultados")
                self._cache_set(cache_key, search_results)
                return search_results
            else:
                logger.warning(f"Respuesta inesperada de Confluence para la búsqueda '{query}'")
                return []
        except Exception as e:
            logger.error(f"Error al buscar '{query}' en Confluence: {str(e)}")
            return []
    
    def get_page_by_id(self, page_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Obtiene una página por su ID.
        
        Args:
            page_id: ID de la página.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            dict: Información de la página o None si no se encuentra.
        """
        cache_key = f"page_{page_id}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            page = self.confluence.get_page_by_id(page_id=page_id, expand="body.storage,version")
            # Añadir URL completa
            if '_links' in page and 'webui' in page['_links']:
                page['_links']['webui_full'] = self._get_full_url(page['_links']['webui'])
            
            logger.info(f"Obtenida página con ID: {page_id}")
            self._cache_set(cache_key, page)
            return page
        except Exception as e:
            logger.error(f"Error al obtener página con ID {page_id}: {str(e)}")
            return None
    
    def get_page_by_title(self, space_key: str, title: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Obtiene una página por su título dentro de un espacio.
        
        Args:
            space_key: Clave del espacio.
            title: Título de la página.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            dict: Información de la página o None si no se encuentra.
        """
        cache_key = f"page_{space_key}_{title}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        
        try:
            page = self.confluence.get_page_by_title(space=space_key, title=title, expand="body.storage,version")
            if page:
                # Añadir URL completa
                if '_links' in page and 'webui' in page['_links']:
                    page['_links']['webui_full'] = self._get_full_url(page['_links']['webui'])
                
                logger.info(f"Obtenida página '{title}' en el espacio {space_key}")
                self._cache_set(cache_key, page)
                return page
            else:
                logger.warning(f"No se encontró la página '{title}' en el espacio {space_key}")
                return None
        except Exception as e:
            logger.error(f"Error al obtener página '{title}' del espacio {space_key}: {str(e)}")
            return None
    
    def extract_content_from_page(self, page: Dict[str, Any]) -> str:
        """
        Extrae el contenido en texto plano de una página de Confluence.
        
        Args:
            page: Información de la página con el campo body.storage.
        
        Returns:
            str: Contenido de la página en texto plano o cadena vacía si no se puede extraer.
        """
        try:
            if 'body' in page and 'storage' in page['body'] and 'value' in page['body']['storage']:
                html_content = page['body']['storage']['value']
                # Aquí podrías implementar un parser HTML para extraer texto,
                # por ahora simplemente quitamos las etiquetas más comunes
                import re
                text_content = re.sub(r'<[^>]+>', ' ', html_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                return text_content
            else:
                logger.warning(f"No se pudo extraer contenido de la página: estructura inesperada")
                return ""
        except Exception as e:
            logger.error(f"Error al extraer contenido de la página: {str(e)}")
            return ""
    
    def smart_search(self, query: str, spaces: Optional[List[str]] = None, max_results: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Realiza una búsqueda inteligente combinando CQL y análisis de contenido.
        
        Args:
            query: Término de búsqueda.
            spaces: Lista de espacios donde buscar. Si es None, usa los espacios objetivo por defecto.
            max_results: Número máximo de resultados.
            use_cache: Si se debe usar la caché (por defecto True).
        
        Returns:
            list: Lista de resultados de la búsqueda con información adicional.
        """
        # Realizar búsqueda básica
        results = self.search_content(query, spaces, max_results, use_cache)
        
        # Procesar y enriquecer los resultados
        enriched_results = []
        for result in results:
            try:
                # Obtener más detalles si es necesario
                content_id = result.get('content', {}).get('id')
                if content_id:
                    # Si es una página, obtener contenido completo
                    page = self.get_page_by_id(content_id, use_cache)
                    if page:
                        # Extraer texto plano para facilitar el procesamiento
                        extracted_text = self.extract_content_from_page(page)
                        
                        # Obtener URL completa
                        url = result.get('url', '')
                        full_url = result.get('full_url', self._get_full_url(url))
                        
                        # Crear objeto de resultado enriquecido
                        enriched_result = {
                            'id': content_id,
                            'title': result.get('content', {}).get('title', 'Sin título'),
                            'url': url,
                            'full_url': full_url,
                            'content_type': result.get('content', {}).get('type', 'unknown'),
                            'excerpt': result.get('excerpt', ''),
                            'space_name': result.get('content', {}).get('space', {}).get('name', 'Espacio desconocido'),
                            'space_key': result.get('content', {}).get('space', {}).get('key', ''),
                            'last_modified': result.get('lastModified', ''),
                            'extracted_text': extracted_text[:1000] + ('...' if len(extracted_text) > 1000 else '')
                        }
                        
                        enriched_results.append(enriched_result)
            except Exception as e:
                logger.error(f"Error al enriquecer resultado de búsqueda: {str(e)}")
        
        logger.info(f"Búsqueda inteligente '{query}': Procesados {len(enriched_results)} resultados")
        return enriched_results
    
    def clear_cache(self) -> None:
        """
        Limpia toda la caché almacenada.
        """
        self._cache = {}
        logger.info("Caché limpiada")
        
    def create_incident_page(self, incident_data: Dict[str, Any], space_key: str = "PSIMDESASW") -> Dict[str, Any]:
        """
        Crea una nueva página de incidente en Confluence con formato de tabla.
        
        Args:
            incident_data: Diccionario con los datos del incidente (recopilados por el agente ATI)
            space_key: Clave del espacio donde crear la página (por defecto PSIMDESASW)
            
        Returns:
            Dict[str, Any]: Información de la página creada, incluyendo ID y URL
        """
        try:
            # Extraer datos del incidente
            fecha_incidente = incident_data.get('fecha_incidente', datetime.now().strftime('%Y-%m-%d'))
            tipo_incidente = incident_data.get('tipo_incidente', 'N/A')
            impacto = incident_data.get('impacto', 'N/A')
            prioridad = incident_data.get('prioridad', 'N/A')
            estado_actual = incident_data.get('estado_actual', 'N/A')
            unidad_negocio = incident_data.get('unidad_negocio', 'N/A')
            usuarios_soporte = incident_data.get('usuarios_soporte', [])
            descripcion_problema = incident_data.get('descripcion_problema', 'N/A')
            acciones_realizadas = incident_data.get('acciones_realizadas', [])
            fecha_resolucion = incident_data.get('fecha_resolucion', 'N/A')
            observaciones = incident_data.get('observaciones', 'N/A')
            
            # Formatear fecha para el título (formato legible)
            fecha_formateada = datetime.strptime(fecha_incidente, '%Y-%m-%d').strftime('%d/%m/%Y')
            
            # Crear título de la página (fecha primero, luego tipo de incidente)
            page_title = f"{fecha_formateada} - {tipo_incidente}"
            
            # Crear contenido de la página con formato HTML
            content = self._generate_incident_table_html(
                fecha_incidente=fecha_incidente,
                tipo_incidente=tipo_incidente,
                impacto=impacto,
                prioridad=prioridad,
                estado_actual=estado_actual,
                unidad_negocio=unidad_negocio,
                usuarios_soporte=usuarios_soporte,
                descripcion_problema=descripcion_problema,
                acciones_realizadas=acciones_realizadas,
                fecha_resolucion=fecha_resolucion,
                observaciones=observaciones
            )
            
            # Crear la página en Confluence
            result = self.confluence.create_page(
                space=space_key,
                title=page_title,
                body=content,
                representation='storage',
                parent_id=None  # Si se desea crear como página principal (ajustar si necesita estar dentro de una sección)
            )
            
            # Agregar la URL completa al resultado
            if '_links' in result and 'webui' in result['_links']:
                result['_links']['webui_full'] = self._get_full_url(result['_links']['webui'])
            
            logger.info(f"Página de incidente creada: {page_title} - ID: {result.get('id')}")
            
            return {
                "id": result.get('id'),
                "title": page_title,
                "url": result.get('_links', {}).get('webui_full', ''),
                "space_key": space_key,
                "success": True,
                "message": f"Página de incidente creada exitosamente: {page_title}"
            }
        
        except Exception as e:
            error_msg = f"Error al crear página de incidente: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }
    
    def _generate_incident_table_html(self, 
                                     fecha_incidente: str,
                                     tipo_incidente: str,
                                     impacto: str,
                                     prioridad: str,
                                     estado_actual: str,
                                     unidad_negocio: str,
                                     usuarios_soporte: List[str],
                                     descripcion_problema: str,
                                     acciones_realizadas: List[str],
                                     fecha_resolucion: str,
                                     observaciones: str) -> str:
        """
        Genera el contenido HTML con formato de tabla para la página de incidente.
        
        Args:
            Los campos del incidente
            
        Returns:
            str: Contenido HTML para la página de Confluence
        """
        # Fecha en formato legible
        fecha_formateada = datetime.strptime(fecha_incidente, '%Y-%m-%d').strftime('%d/%m/%Y')
        
        # Formatear usuarios de soporte como lista HTML
        usuarios_html = ""
        if usuarios_soporte:
            usuarios_html = "<ul>"
            for usuario in usuarios_soporte:
                usuarios_html += f"<li>{usuario}</li>"
            usuarios_html += "</ul>"
        else:
            usuarios_html = "N/A"
        
        # Procesar acciones realizadas
        acciones_rows = ""
        if acciones_realizadas:
            for i, accion in enumerate(acciones_realizadas, 1):
                # Intentar extraer fecha, detalle y área (formato esperado: "fecha - detalle - área")
                partes = []
                if " - " in accion:
                    partes = accion.split(" - ", 2)
                
                if len(partes) >= 3:
                    fecha_accion, detalle_accion, area_accion = partes
                    acciones_rows += f"""
                    <tr>
                        <td>Fecha de acción {i}</td>
                        <td>{detalle_accion}</td>
                        <td>{area_accion}</td>
                    </tr>
                    """
                else:
                    # Si no tiene el formato esperado, mostrarlo completo
                    acciones_rows += f"""
                    <tr>
                        <td>Acción {i}</td>
                        <td colspan="2">{accion}</td>
                    </tr>
                    """
        
        # Crear tabla HTML
        html_content = f"""
        <h1>Incidente Mayor: {tipo_incidente}</h1>
        
        <table class="confluenceTable">
            <tbody>
                <tr>
                    <th class="confluenceTh">Fecha de Incidente</th>
                    <td class="confluenceTd">{fecha_formateada}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Tipo de Incidente</th>
                    <td class="confluenceTd">{tipo_incidente}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Impacto</th>
                    <td class="confluenceTd">{impacto}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Prioridad</th>
                    <td class="confluenceTd">{prioridad}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Estado Actual</th>
                    <td class="confluenceTd">{estado_actual}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Unidad de Negocio Solicitante</th>
                    <td class="confluenceTd">{unidad_negocio}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Usuario de soporte</th>
                    <td class="confluenceTd">{usuarios_html}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Descripción del Problema</th>
                    <td class="confluenceTd">{descripcion_problema}</td>
                </tr>
            </tbody>
        </table>
        
        <h2>Acciones Realizadas</h2>
        <table class="confluenceTable">
            <thead>
                <tr>
                    <th class="confluenceTh">Fecha</th>
                    <th class="confluenceTh">Acciones Realizadas</th>
                    <th class="confluenceTh">Área Encargada de la acción</th>
                </tr>
            </thead>
            <tbody>
                {acciones_rows}
            </tbody>
        </table>
        
        <h2>Resolución</h2>
        <table class="confluenceTable">
            <tbody>
                <tr>
                    <th class="confluenceTh">Fecha de Resolución</th>
                    <td class="confluenceTd">{fecha_resolucion}</td>
                </tr>
                <tr>
                    <th class="confluenceTh">Observaciones</th>
                    <td class="confluenceTd">{observaciones}</td>
                </tr>
            </tbody>
        </table>
        """
        
        return html_content 
import os
import atexit
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import re

from pydantic_ai import Agent, RunContext, Tool
from pydantic import BaseModel, Field

from app.utils.confluence_client import ConfluenceClient
from app.utils.logger import get_logger
from app.agents.models import ConfluenceSpace, ConfluencePage, SearchResult, AgentResponse
from app.config.config import OPENAI_API_KEY, LOGFIRE_TOKEN, USE_LOGFIRE

# Importar logfire para instrumentación
try:
    import logfire
    has_logfire = True
except ImportError:
    has_logfire = False

# Forward reference para type hint
if TYPE_CHECKING:
    from .confluence_agent import ConfluenceAgent

# Configurar logger
logger = get_logger("confluence_agent")

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

@dataclass
class ConfluenceAgentDependencies:
    """Dependencias para el agente de Confluence."""
    confluence_client: ConfluenceClient
    context: Dict[str, Any]  # Contexto para almacenar información entre interacciones
    agent_instance: 'ConfluenceAgent'

class ConfluenceAgent:
    """Agente para interactuar con Confluence de forma conversacional."""
    
    def __init__(self):
        """Inicializa el agente de Confluence."""
        try:
            # Iniciar cliente Confluence
            confluence_client = ConfluenceClient()
            
            # Crear diccionario de contexto para almacenar estado entre interacciones
            context = {
                "conversation_history": [],
                "last_search_results": [],
                "current_page": None
            }
            
            # Crear dependencias para el agente
            self._deps = ConfluenceAgentDependencies(
                confluence_client=confluence_client,
                context=context,
                agent_instance=self
            )
            
            # Preparar las herramientas para el agente
            agent_tools = [
                Tool(self.get_conversation_history, takes_ctx=True, 
                    name="get_conversation_history",
                    description="Obtiene el historial reciente de la conversación entre el usuario y el agente."),
                Tool(self.remember_current_page, takes_ctx=True, 
                    name="remember_current_page",
                    description="Guarda la página actual en la memoria para futuras referencias. Usa esta herramienta cada vez que el usuario seleccione una página específica."),
                Tool(self.get_current_page, takes_ctx=True, 
                    name="get_current_page",
                    description="Obtiene la página actualmente guardada en memoria, si existe. Útil cuando el usuario hace referencia a 'la página actual', 'esta página', etc."),
                Tool(self.get_spaces, takes_ctx=True, 
                    name="get_spaces",
                    description="Obtiene los espacios disponibles en Confluence. Útil para mostrar al usuario los espacios a los que puede acceder."),
                Tool(self.get_space_content, takes_ctx=True, 
                    name="get_space_content",
                    description="Obtiene el contenido de un espacio específico de Confluence. Muestra las páginas con su título y URL."),
                Tool(self.search_content, takes_ctx=True, 
                    name="search_content",
                    description="Busca contenido en Confluence basado en un término de búsqueda. Útil para encontrar páginas específicas por título, descripción o palabra clave."),
                Tool(self.smart_search, takes_ctx=True, 
                    name="smart_search",
                    description="Realiza una búsqueda inteligente en Confluence combinando búsqueda por términos y análisis del contenido. Esta es la herramienta principal para buscar información. Usa esta herramienta en lugar de search_content."),
                Tool(self.get_page_by_reference, takes_ctx=True, 
                    name="get_page_by_reference",
                    description="Obtiene el ID de una página basada en una referencia del usuario (como 'opción 1', 'la primera', etc.). Usa esta herramienta antes de realizar acciones sobre una página mencionada por el usuario."),
                Tool(self.get_page_details, takes_ctx=True, 
                    name="get_page_details",
                    description="Obtiene detalles completos de una página específica de Confluence, incluyendo su contenido."),
                Tool(self.get_page_by_title, takes_ctx=True, 
                    name="get_page_by_title",
                    description="Busca una página por su título en un espacio específico. Útil cuando el usuario menciona un título exacto de una página.")
            ]
            
            # Inicializar el agente de PydanticAI
            self.agent = Agent(
                "openai:gpt-4o",  # Usa GPT-4o para mejor procesamiento de contexto
                deps_type=ConfluenceAgentDependencies,
                tools=agent_tools,  # Usar la lista de herramientas preparada
                # Habilitar memoria para mantener contexto de conversación
                system_prompt=(
                    "Eres un asistente experto en Confluence que ayuda a los usuarios a encontrar y consultar información. "
                    "Puedes proporcionar información sobre espacios, buscar contenido, y obtener detalles de páginas en Confluence. "
                    "Sé conciso, claro y siempre útil. Cuando necesites más información, pregunta al usuario. "
                    "\n\n"
                    "DIRECTRICES IMPORTANTES DE CONTEXTO Y MEMORIA: "
                    "- SIEMPRE usa la herramienta get_conversation_history al inicio de tu respuesta para recordar el contexto de la conversación. "
                    "  Esto te permitirá mantener la coherencia y recordar referencias a páginas, búsquedas previas y preferencias del usuario. "
                    "- Cuando el usuario seleccione una página, SIEMPRE usa remember_current_page para guardarla para futuras referencias. "
                    "- Si el usuario hace referencia a 'la página actual', 'esta página', 'la misma página', etc., usa get_current_page para obtener la página actual. "
                    "- Si el usuario hace referencia a algo mencionado previamente, consulta el historial para recordar el contexto. "
                    "\n\n"
                    "DIRECTRICES PARA BÚSQUEDA DE CONTENIDO: "
                    "- Para buscar contenido, SIEMPRE utiliza la herramienta smart_search. "
                    "- Cuando el usuario haga referencia a una página por un número de opción o descripción (como 'opción 1', 'la primera', 'opción 3', 'esa página', 'la guía de VPN'), "
                    "DEBES utilizar la herramienta get_page_by_reference para obtener el ID correcto de la página antes de proceder con otras acciones (como get_page_details). "
                    "- No intentes adivinar el ID de la página basándote en el número de opción. Usa siempre get_page_by_reference."
                    "\n\n"
                    "DIRECTRICES PARA RESPONDER PREGUNTAS: "
                    "- Cuando los usuarios pregunten sobre procedimientos específicos como 'Cómo configuro la VPN' o 'Cómo instalo IntelliJ Idea', usa smart_search para encontrar documentación relevante. "
                    "- Utiliza get_page_details para obtener el contenido completo del documento más relevante. "
                    "- Resume la información de manera clara y concisa, destacando los pasos principales. "
                    "- Si el contenido está en inglés y el usuario pregunta en español (o viceversa), traduce la información a la misma lengua en la que preguntó el usuario. "
                    "- Siempre incluye un enlace a la documentación original para que el usuario pueda consultarla directamente si lo desea."
                    "\n\n"
                    "ESPACIOS DISPONIBLES: "
                    "- Este agente está configurado para buscar en los espacios: PSIMDESASW, ITIndustrial. "
                    "- Si el usuario quiere buscar en un espacio diferente, infórmale que por ahora solo puedes buscar en estos espacios específicos."
                ),
                instrument=use_logfire  # Habilitar instrumentación para monitoreo con logfire solo si está disponible
            )
            
            logger.info("Agente de Confluence inicializado correctamente")
            
        except Exception as e:
            logger.error(f"Error al inicializar el agente de Confluence: {e}")
            raise
    
    async def process_message(self, message: str) -> str:
        """
        Procesa un mensaje del usuario y devuelve una respuesta.
        
        Args:
            message: Mensaje del usuario.
            
        Returns:
            str: Respuesta al usuario.
        """
        try:
            # Guardar mensaje en el historial
            if "conversation_history" in self._deps.context:
                self._deps.context["conversation_history"].append({
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Ejecutar el agente
            result = await self.agent.run(message, deps=self._deps)
            
            # Capturar la respuesta del agente
            agent_response = result.data
            
            # Guardar respuesta en el historial
            if "conversation_history" in self._deps.context:
                self._deps.context["conversation_history"].append({
                    "role": "assistant",
                    "content": agent_response,
                    "timestamp": datetime.now().isoformat()
                })
            
            return agent_response
        except Exception as e:
            error_msg = f"Error al procesar mensaje: {str(e)}"
            logger.error(error_msg)
            return f"Lo siento, ocurrió un error al procesar tu mensaje. Por favor intenta de nuevo más tarde. Detalles: {str(e)}"
    
    def process_message_sync(self, message: str) -> str:
        """
        Versión síncrona de process_message.
        
        Args:
            message: Mensaje del usuario.
            
        Returns:
            str: Respuesta al usuario.
        """
        try:
            # Guardar mensaje en el historial
            if "conversation_history" in self._deps.context:
                self._deps.context["conversation_history"].append({
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Ejecutar el agente
            result = self.agent.run_sync(message, deps=self._deps)
            
            # Capturar la respuesta del agente
            agent_response = result.data
            
            # Guardar respuesta en el historial
            if "conversation_history" in self._deps.context:
                self._deps.context["conversation_history"].append({
                    "role": "assistant",
                    "content": agent_response,
                    "timestamp": datetime.now().isoformat()
                })
            
            return agent_response
        except Exception as e:
            error_msg = f"Error al procesar mensaje: {str(e)}"
            logger.error(error_msg)
            return f"Lo siento, ocurrió un error al procesar tu mensaje. Por favor intenta de nuevo más tarde. Detalles: {str(e)}"
    
    async def get_conversation_history(self, ctx: RunContext[ConfluenceAgentDependencies]) -> List[Dict[str, str]]:
        """
        Obtiene el historial reciente de la conversación.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            
        Returns:
            List[Dict[str, str]]: Historial de conversación reciente.
        """
        # Obtener los últimos 10 mensajes del historial (o menos si hay menos)
        history = ctx.deps.context.get("conversation_history", [])
        recent_history = history[-10:] if len(history) > 10 else history
        return recent_history
    
    async def remember_current_page(self, ctx: RunContext[ConfluenceAgentDependencies], page_id: str, title: str, url: str) -> Dict[str, Any]:
        """
        Guarda la página actual en la memoria para futuras referencias.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            page_id: ID de la página.
            title: Título de la página.
            url: URL de la página.
            
        Returns:
            Dict[str, Any]: Información de la página guardada.
        """
        current_page = {
            "id": page_id,
            "title": title,
            "url": url
        }
        ctx.deps.context["current_page"] = current_page
        logger.info(f"Página actual guardada en memoria: {title} (ID: {page_id})")
        return {"success": True, "message": f"Página '{title}' guardada como referencia actual", "page": current_page}
    
    async def get_current_page(self, ctx: RunContext[ConfluenceAgentDependencies]) -> Dict[str, Any]:
        """
        Obtiene la página actualmente guardada en memoria, si existe.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            
        Returns:
            Dict[str, Any]: Información de la página actual o mensaje de error.
        """
        current_page = ctx.deps.context.get("current_page")
        if current_page:
            logger.info(f"Obtenida página actual de la memoria: {current_page.get('title')}")
            return {"success": True, "message": "Página actual recuperada", "page": current_page}
        else:
            logger.warning("No hay página actual en memoria")
            return {"success": False, "message": "No hay ninguna página seleccionada actualmente", "page": None}
    
    async def get_spaces(self, ctx: RunContext[ConfluenceAgentDependencies]) -> Dict[str, Any]:
        """
        Obtiene los espacios disponibles en Confluence.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            
        Returns:
            Dict[str, Any]: Lista de espacios disponibles.
        """
        try:
            spaces = ctx.deps.confluence_client.get_all_spaces()
            if spaces:
                # Filtrar y formatear la información de los espacios
                formatted_spaces = []
                for i, space in enumerate(spaces, 1):
                    formatted_space = {
                        "index": i,
                        "key": space.get("key", ""),
                        "name": space.get("name", ""),
                        "description": space.get("description", {}).get("plain", {}).get("value", "") if space.get("description") else ""
                    }
                    formatted_spaces.append(formatted_space)
                
                logger.info(f"Obtenidos {len(formatted_spaces)} espacios")
                return {"success": True, "message": f"Se encontraron {len(formatted_spaces)} espacios", "spaces": formatted_spaces}
            else:
                logger.warning("No se encontraron espacios")
                return {"success": False, "message": "No se encontraron espacios disponibles", "spaces": []}
        except Exception as e:
            error_msg = f"Error al obtener espacios: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "spaces": []}
    
    async def get_space_content(self, ctx: RunContext[ConfluenceAgentDependencies], space_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene el contenido de un espacio específico.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            space_key: Clave del espacio.
            content_type: Tipo de contenido (page, blogpost, etc).
            
        Returns:
            Dict[str, Any]: Lista de contenido en el espacio.
        """
        try:
            content = ctx.deps.confluence_client.get_space_content(space_key, content_type)
            if content:
                # Formatear la información del contenido
                formatted_content = []
                for i, item in enumerate(content, 1):
                    formatted_item = {
                        "index": i,
                        "id": item.get("id", ""),
                        "title": item.get("title", ""),
                        "url": item.get("_links", {}).get("webui", "")
                    }
                    formatted_content.append(formatted_item)
                
                logger.info(f"Obtenidos {len(formatted_content)} elementos de contenido en el espacio {space_key}")
                return {
                    "success": True, 
                    "message": f"Se encontraron {len(formatted_content)} elementos en el espacio {space_key}", 
                    "content": formatted_content
                }
            else:
                logger.warning(f"No se encontró contenido en el espacio {space_key}")
                return {"success": False, "message": f"No se encontró contenido en el espacio {space_key}", "content": []}
        except Exception as e:
            error_msg = f"Error al obtener contenido del espacio {space_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "content": []}
    
    async def search_content(self, ctx: RunContext[ConfluenceAgentDependencies], query: str, spaces: Optional[List[str]] = None, max_results: int = 10) -> Dict[str, Any]:
        """
        Busca contenido en Confluence.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            query: Término de búsqueda.
            spaces: Lista de espacios donde buscar. Si es None, usa los espacios objetivo por defecto.
            max_results: Número máximo de resultados.
            
        Returns:
            Dict[str, Any]: Resultados de la búsqueda.
        """
        try:
            # Si no se proporcionan espacios, usar los espacios objetivo
            if spaces is None:
                spaces = ctx.deps.confluence_client.target_spaces
            
            results = ctx.deps.confluence_client.search_content(query, spaces, max_results)
            
            if results:
                # Formatear los resultados
                formatted_results = []
                for i, result in enumerate(results, 1):
                    formatted_result = {
                        "index": i,
                        "id": result.get("content", {}).get("id", ""),
                        "title": result.get("content", {}).get("title", ""),
                        "url": result.get("url", ""),
                        "space_key": result.get("content", {}).get("space", {}).get("key", ""),
                        "space_name": result.get("content", {}).get("space", {}).get("name", ""),
                        "excerpt": result.get("excerpt", "")
                    }
                    formatted_results.append(formatted_result)
                
                # Guardar resultados en el contexto para referencia futura
                ctx.deps.context["last_search_results"] = formatted_results
                
                logger.info(f"Búsqueda '{query}': Encontrados {len(formatted_results)} resultados")
                return {
                    "success": True, 
                    "message": f"Se encontraron {len(formatted_results)} resultados para '{query}'", 
                    "results": formatted_results
                }
            else:
                logger.warning(f"No se encontraron resultados para la búsqueda '{query}'")
                return {"success": False, "message": f"No se encontraron resultados para '{query}'", "results": []}
        except Exception as e:
            error_msg = f"Error al buscar '{query}': {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "results": []}
    
    async def smart_search(self, ctx: RunContext[ConfluenceAgentDependencies], query: str, spaces: Optional[List[str]] = None, max_results: int = 10) -> Dict[str, Any]:
        """
        Realiza una búsqueda inteligente en Confluence.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            query: Término de búsqueda.
            spaces: Lista de espacios donde buscar. Si es None, usa los espacios objetivo por defecto.
            max_results: Número máximo de resultados.
            
        Returns:
            Dict[str, Any]: Resultados enriquecidos de la búsqueda.
        """
        try:
            # Si no se proporcionan espacios, usar los espacios objetivo
            if spaces is None:
                spaces = ctx.deps.confluence_client.target_spaces
            
            results = ctx.deps.confluence_client.smart_search(query, spaces, max_results)
            
            if results:
                # Formatear los resultados
                formatted_results = []
                for i, result in enumerate(results, 1):
                    formatted_result = {
                        "index": i,
                        "id": result.get("id", ""),
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "space_key": result.get("space_key", ""),
                        "space_name": result.get("space_name", ""),
                        "excerpt": result.get("excerpt", ""),
                        "content_type": result.get("content_type", ""),
                        "extracted_text": result.get("extracted_text", "")
                    }
                    formatted_results.append(formatted_result)
                
                # Guardar resultados en el contexto para referencia futura
                ctx.deps.context["last_search_results"] = formatted_results
                
                logger.info(f"Búsqueda inteligente '{query}': Encontrados {len(formatted_results)} resultados")
                return {
                    "success": True, 
                    "message": f"Se encontraron {len(formatted_results)} resultados para '{query}'", 
                    "results": formatted_results
                }
            else:
                logger.warning(f"No se encontraron resultados para la búsqueda inteligente '{query}'")
                return {"success": False, "message": f"No se encontraron resultados para '{query}'", "results": []}
        except Exception as e:
            error_msg = f"Error al realizar búsqueda inteligente de '{query}': {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "results": []}
    
    async def get_page_by_reference(self, ctx: RunContext[ConfluenceAgentDependencies], reference: str) -> Dict[str, Any]:
        """
        Obtiene una página basada en una referencia del usuario.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            reference: Referencia a la página (como 'opción 1', 'la primera', etc.).
            
        Returns:
            Dict[str, Any]: Información de la página o mensaje de error.
        """
        try:
            # Obtener los resultados de la última búsqueda
            last_results = ctx.deps.context.get("last_search_results", [])
            
            if not last_results:
                logger.warning("No hay resultados de búsqueda previos para obtener referencia")
                return {"success": False, "message": "No hay resultados de búsqueda previos para obtener referencia", "page": None}
            
            # Intentar extraer un número de la referencia
            index = None
            
            # Patrón para 'opción X', 'número X', etc.
            option_match = re.search(r'(?:opci[oó]n|numero|número|#|item|ítem)\s*(\d+)', reference.lower())
            if option_match:
                index = int(option_match.group(1))
            
            # Patrón para 'la primera', 'la segunda', etc.
            ordinal_map = {'primer': 1, 'segund': 2, 'tercer': 3, 'cuart': 4, 'quint': 5, 
                          'sext': 6, 'séptim': 7, 'septim': 7, 'octav': 8, 'noven': 9, 'décim': 10}
            for ordinal, value in ordinal_map.items():
                if ordinal in reference.lower():
                    index = value
                    break
            
            # Patrón para simplemente un número
            if index is None:
                num_match = re.search(r'^(\d+)$', reference.strip())
                if num_match:
                    index = int(num_match.group(1))
            
            # Si se encontró un índice y está dentro del rango de resultados
            if index is not None and 1 <= index <= len(last_results):
                selected_page = last_results[index - 1]
                logger.info(f"Página seleccionada por referencia '{reference}': {selected_page.get('title')} (ID: {selected_page.get('id')})")
                return {"success": True, "message": f"Página seleccionada: {selected_page.get('title')}", "page": selected_page}
            else:
                # Si no se encontró por índice, intentar buscar por coincidencia de título
                for result in last_results:
                    if result.get("title", "").lower() in reference.lower() or reference.lower() in result.get("title", "").lower():
                        logger.info(f"Página seleccionada por título '{reference}': {result.get('title')} (ID: {result.get('id')})")
                        return {"success": True, "message": f"Página seleccionada: {result.get('title')}", "page": result}
                
                logger.warning(f"No se encontró página para la referencia '{reference}'")
                return {"success": False, "message": f"No se encontró página para la referencia '{reference}'", "page": None}
        except Exception as e:
            error_msg = f"Error al obtener página por referencia '{reference}': {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "page": None}
    
    async def get_page_details(self, ctx: RunContext[ConfluenceAgentDependencies], page_id: str) -> Dict[str, Any]:
        """
        Obtiene detalles completos de una página específica.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            page_id: ID de la página.
            
        Returns:
            Dict[str, Any]: Detalles de la página o mensaje de error.
        """
        try:
            page = ctx.deps.confluence_client.get_page_by_id(page_id)
            
            if page:
                # Extraer texto plano del contenido
                extracted_text = ctx.deps.confluence_client.extract_content_from_page(page)
                
                # Formatear la información de la página
                formatted_page = {
                    "id": page.get("id", ""),
                    "title": page.get("title", ""),
                    "url": page.get("_links", {}).get("webui", "") if "_links" in page else "",
                    "space_key": page.get("space", {}).get("key", "") if "space" in page else "",
                    "space_name": page.get("space", {}).get("name", "") if "space" in page else "",
                    "content": extracted_text,
                    "version": page.get("version", {}).get("number", "") if "version" in page else "",
                    "last_modified": page.get("version", {}).get("when", "") if "version" in page else ""
                }
                
                logger.info(f"Obtenidos detalles de la página: {formatted_page.get('title')} (ID: {page_id})")
                
                # Guardar la página actual en el contexto
                await self.remember_current_page(ctx, page_id, formatted_page.get("title"), formatted_page.get("url"))
                
                return {"success": True, "message": f"Detalles de la página '{formatted_page.get('title')}'", "page": formatted_page}
            else:
                logger.warning(f"No se encontró la página con ID {page_id}")
                return {"success": False, "message": f"No se encontró la página con ID {page_id}", "page": None}
        except Exception as e:
            error_msg = f"Error al obtener detalles de la página con ID {page_id}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "page": None}
    
    async def get_page_by_title(self, ctx: RunContext[ConfluenceAgentDependencies], space_key: str, title: str) -> Dict[str, Any]:
        """
        Busca una página por su título en un espacio específico.
        
        Args:
            ctx: Contexto de ejecución con dependencias.
            space_key: Clave del espacio.
            title: Título de la página.
            
        Returns:
            Dict[str, Any]: Detalles de la página o mensaje de error.
        """
        try:
            page = ctx.deps.confluence_client.get_page_by_title(space_key, title)
            
            if page:
                # Extraer texto plano del contenido
                extracted_text = ctx.deps.confluence_client.extract_content_from_page(page)
                
                # Formatear la información de la página
                formatted_page = {
                    "id": page.get("id", ""),
                    "title": page.get("title", ""),
                    "url": page.get("_links", {}).get("webui", "") if "_links" in page else "",
                    "space_key": page.get("space", {}).get("key", "") if "space" in page else "",
                    "space_name": page.get("space", {}).get("name", "") if "space" in page else "",
                    "content": extracted_text,
                    "version": page.get("version", {}).get("number", "") if "version" in page else "",
                    "last_modified": page.get("version", {}).get("when", "") if "version" in page else ""
                }
                
                logger.info(f"Obtenida página por título: {title} en el espacio {space_key}")
                
                # Guardar la página actual en el contexto
                await self.remember_current_page(ctx, formatted_page.get("id"), formatted_page.get("title"), formatted_page.get("url"))
                
                return {"success": True, "message": f"Página encontrada: '{title}'", "page": formatted_page}
            else:
                logger.warning(f"No se encontró la página con título '{title}' en el espacio {space_key}")
                return {"success": False, "message": f"No se encontró la página con título '{title}' en el espacio {space_key}", "page": None}
        except Exception as e:
            error_msg = f"Error al obtener página con título '{title}' en el espacio {space_key}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg, "page": None} 
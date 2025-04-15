# jira_agent/jira_tool_agent.py
import os
from dotenv import load_dotenv
import logging # Añadir import de logging
from pydantic_ai.models.openai import OpenAIModel
# Si usas otro proveedor, importa el modelo correspondiente
# from pydantic_ai.models.anthropic import AnthropicModel
# from pydantic_ai.models.litellm import LiteLLM
from utils.utils import setup_logger, parse_time_string_to_seconds, format_iso_datetime # <-- Añadir imports
from datetime import datetime, timezone # <-- Añadir imports de datetime
from openai import AsyncOpenAI
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from atlassian import Jira # Importamos el cliente Jira
from atlassian.errors import ApiError
from pydantic_ai.messages import ModelMessage

from .agent_prompts import jira_system_prompt # Importamos el prompt
from utils.utils import setup_logger
from .agent_prompts import jira_system_prompt
from utils.utils import setup_logger, parse_time_string_to_seconds, format_iso_datetime, escape_jql_string

from typing import List, Dict, Any, Optional # Añadir Optional y Dict si no están
import json # Para formatear la salida

# Configurar el logger para este módulo
logger = setup_logger(__name__)

# Cargar variables de entorno desde .env
load_dotenv()

def get_llm_client():
    """Crea y configura el cliente LLM basado en las variables de entorno."""
    base_url = os.getenv('BASE_URL', 'https://api.openai.com/v1')
    api_key = os.getenv('LLM_API_KEY', 'no-llm-api-key-provided') # Clave genérica o para otros proveedores
    openai_specific_key = os.getenv('OPENAI_API_KEY') # Clave específica de OpenAI
    model_name = os.getenv('PRIMARY_MODEL', 'gpt-4o-mini')

    # ---- Adaptar esta sección según tu proveedor ----
    # Ejemplo para OpenAI
    if "api.openai.com" in base_url:
        # print(f"Configurando OpenAI con modelo: {model_name}")
        # ¡IMPORTANTE! Asegúrate de que la variable OPENAI_API_KEY esté definida en tu .env
        # if not openai_specific_key:
        #     print("ADVERTENCIA: OPENAI_API_KEY no encontrada en .env. La biblioteca openai intentará buscarla.")
             # Alternativamente, podrías lanzar un error si es estrictamente necesaria:
             # raise ValueError("OPENAI_API_KEY es requerida en .env para usar OpenAI directamente.")

        # Corrección: NO pasar api_key explícitamente.
        # La biblioteca 'openai' buscará la variable de entorno OPENAI_API_KEY.
        return OpenAIModel(model_name) # <--- SOLO pasamos el nombre del modelo

    # Ejemplo para OpenRouter
    elif "openrouter.ai" in base_url:
        # print(f"Configurando OpenRouter con modelo: {model_name}")
        # OpenRouter SÍ necesita api_key explícito
        return OpenAIModel(model_name, base_url=base_url, api_key=api_key)

    # Ejemplo para Ollama
    elif "localhost" in base_url or "ollama" in base_url:
        # print(f"Configurando Ollama con modelo: {model_name}")
        ollama_key = api_key if api_key != 'no-llm-api-key-provided' else 'ollama'
        # Ollama necesita el cliente preconfigurado
        client = AsyncOpenAI(base_url=base_url, api_key=ollama_key)
        return OpenAIModel(model_name, openai_client=client)

    # Ejemplo para Anthropic (Descomentar si lo usas)
    # elif "api.anthropic.com" in base_url:
    #     print(f"Configurando Anthropic con modelo: {model_name}")
    #     from pydantic_ai.models.anthropic import AnthropicModel
    #     # Anthropic SÍ necesita api_key explícito
    #     return AnthropicModel(model_name, api_key=api_key)

    else:
        # Configuración genérica (puede que necesite api_key o no, dependiendo del endpoint)
        # print(f"Configurando LLM genérico ({base_url}) con modelo: {model_name}")
        # Asumimos que podría necesitar la clave genérica
        return OpenAIModel(model_name, base_url=base_url, api_key=api_key)
    # -------------------------------------------------


# Instancia global del modelo (o podrías pasarla como dependencia)
llm_model = get_llm_client()

@dataclass
class JiraAgentDeps:
    """Dependencias necesarias para el agente Jira."""
    jira_client: Jira

# Crear la instancia del Agente Pydantic AI
# Pasamos el modelo LLM, el prompt del sistema y el tipo de dependencias
jira_agent = Agent(
    llm_model,
    system_prompt=jira_system_prompt,
    deps_type=JiraAgentDeps,
    retries=2 # Intentar 2 veces si falla una llamada al LLM o herramienta
)

# --- Las herramientas (@jira_agent.tool) irán aquí debajo ---
@jira_agent.tool()
async def jira_search_assigned_issues(ctx: RunContext[JiraAgentDeps], max_results: int = 10) -> str:
    """
    Busca y devuelve una lista de issues de Jira asignados actualmente al usuario que ejecuta esta herramienta.

    Args:
        max_results (int): El número máximo de issues a devolver (por defecto 10, máximo 50).

    Returns:
        str: Una cadena JSON formateada con la lista de issues encontrados (clave, resumen, estado)
             o un mensaje indicando que no se encontraron issues.
    """
    logger.info(f"Ejecutando herramienta: jira_search_assigned_issues (max_results={max_results})")
    try:
        # Asegurarse que max_results esté dentro de límites razonables
        limit = max(1, min(max_results, 50))
        # Usamos la instancia del cliente Jira desde las dependencias (ctx.deps)
        jira_client: Jira = ctx.deps.jira_client
        # JQL para buscar issues asignados al usuario actual
        jql_query = f'assignee = currentUser() ORDER BY updated DESC'
        logger.debug(f"Ejecutando JQL: {jql_query} con límite {limit}")

        issues = jira_client.jql(
            jql_query,
            limit=limit,
            fields="key,summary,status" # Pedimos solo los campos necesarios
        )

        if not issues or not issues.get('issues'):
            logger.info("No se encontraron issues asignados para el usuario.")
            return "No tienes issues asignados actualmente."

        # Formatear la salida como una lista de diccionarios simples
        results_list = [
            {
                "key": issue.get('key'),
                "summary": issue.get('fields', {}).get('summary', 'N/A'),
                "status": issue.get('fields', {}).get('status', {}).get('name', 'N/A')
            }
            for issue in issues.get('issues', [])
        ]

        logger.info(f"Encontrados {len(results_list)} issues asignados.")
        # Devolver como JSON string formateado
        return json.dumps(results_list, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.exception("Error al buscar issues asignados en Jira.")
        # Devolvemos el error al LLM para que pueda informar al usuario
        return f"Error al buscar issues asignados: {e}"
    
@jira_agent.tool()
async def jira_get_issue_details(ctx: RunContext[JiraAgentDeps], issue_key: str) -> str:
    """
    Obtiene y devuelve los detalles completos de un issue específico de Jira usando su clave.

    Args:
        issue_key (str): La clave única del issue (ej. 'PROJ-123').

    Returns:
        str: Una cadena JSON formateada con los detalles del issue (incluyendo resumen, descripción, estado,
             asignado, informador, etiquetas, prioridad, fechas, etc.) o un mensaje de error si no se encuentra.
    """
    logger.info(f"Ejecutando herramienta: jira_get_issue_details (issue_key={issue_key})")
    if not issue_key:
        logger.warning("Intento de llamar a jira_get_issue_details sin issue_key.")
        return "Por favor, proporciona la clave del issue (ej. PSISDW-123)."
    try:
        jira_client: Jira = ctx.deps.jira_client
        logger.debug(f"Solicitando detalles para el issue: {issue_key}")

        # Usamos get_issue que devuelve más detalles que una búsqueda JQL simple
        issue_data = jira_client.get_issue(issue_key, fields="*all") # Pedimos todos los campos

        if not issue_data:
            logger.warning(f"Issue {issue_key} no encontrado.")
            return f"No se pudo encontrar el issue con clave '{issue_key}'."

        # Simplificar un poco la estructura para el LLM (opcional, pero útil)
        simplified_details = {
            "key": issue_data.get('key'),
            "url": issue_data.get('self', '').replace('/rest/api/2/issue/', '/browse/'), # Crear URL navegable
            "summary": issue_data.get('fields', {}).get('summary'),
            "description": issue_data.get('fields', {}).get('description', 'Sin descripción.'),
            "status": issue_data.get('fields', {}).get('status', {}).get('name'),
            "assignee": issue_data.get('fields', {}).get('assignee', {}).get('displayName', 'Sin asignar') if issue_data.get('fields', {}).get('assignee') else 'Sin asignar',
            "reporter": issue_data.get('fields', {}).get('reporter', {}).get('displayName', 'N/A'),
            "priority": issue_data.get('fields', {}).get('priority', {}).get('name', 'N/A'),
            "labels": issue_data.get('fields', {}).get('labels', []),
            "created": issue_data.get('fields', {}).get('created'),
            "updated": issue_data.get('fields', {}).get('updated'),
            "issue_type": issue_data.get('fields', {}).get('issuetype', {}).get('name'),
            # Podríamos añadir más campos si fueran necesarios (versiones, componentes, etc.)
        }
        # Eliminar campos None para una salida más limpia
        simplified_details = {k: v for k, v in simplified_details.items() if v is not None}

        logger.info(f"Detalles obtenidos para {issue_key}.")
        return json.dumps(simplified_details, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.exception(f"Error al obtener detalles del issue {issue_key}.")
        return f"Error al obtener detalles para '{issue_key}': {e}"
    
@jira_agent.tool()
async def jira_add_worklog(ctx: RunContext[JiraAgentDeps], issue_key: str, time_spent: str, comment: Optional[str] = None, started_str: Optional[str] = None) -> str:
    """
    Registra tiempo trabajado (worklog) en un issue específico de Jira.

    Args:
        issue_key (str): La clave única del issue (ej. 'PROJ-123').
        time_spent (str): El tiempo dedicado, en formato Jira (ej. '1h 30m', '2d', '45m').
        comment (Optional[str]): Un comentario opcional para describir el trabajo realizado.
        started_str (Optional[str]): La fecha y hora de inicio del trabajo como string ISO 8601
                                    (ej. '2025-04-13T10:00:00') o None para usar la hora actual.
                                    La zona horaria se asumirá como UTC si no se especifica.

    Returns:
        str: Un mensaje de confirmación si el registro fue exitoso, o un mensaje de error.
    """
    logger.info(f"Ejecutando herramienta: jira_add_worklog (issue_key={issue_key}, time_spent='{time_spent}')")
    if not issue_key or not time_spent:
        logger.warning("Intento de llamar a jira_add_worklog sin issue_key o time_spent.")
        return "Por favor, proporciona la clave del issue y el tiempo dedicado (ej. '1h 30m')."

    # Convertir el string de tiempo a segundos
    time_spent_seconds = parse_time_string_to_seconds(time_spent)
    if time_spent_seconds is None:
        logger.warning(f"Formato de time_spent inválido: '{time_spent}'")
        return f"El formato del tiempo dedicado '{time_spent}' no es válido. Usa 'Xd', 'Xh' o 'Xm' (ej. '1d 2h 30m')."

    # Formatear la fecha de inicio si se proporciona, sino usar ahora en UTC
    started_formatted = None
    if started_str:
        try:
            # Intentar parsear la fecha (puede necesitar ajustes si el formato de entrada varía)
            dt_start = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
            # Asegurarse que tenga timezone, si no, asumir UTC
            if dt_start.tzinfo is None:
                dt_start = dt_start.replace(tzinfo=timezone.utc)
            started_formatted = format_iso_datetime(dt_start)
        except ValueError:
            logger.warning(f"Formato de fecha 'started_str' inválido: '{started_str}'. Usando hora actual.")
            started_formatted = format_iso_datetime() # Usar ahora si el formato es malo
    else:
        started_formatted = format_iso_datetime() # Usar ahora si no se proporcionó

    logger.debug(f"Datos para issue_worklog: issue='{issue_key}', started='{started_formatted}', timeSeconds={time_spent_seconds}, comment='{comment}'")

    try:
        jira_client: Jira = ctx.deps.jira_client

        # --- Usar issue_worklog según documentación ---
        # La documentación muestra: issue_worklog(issue_key, started, time_in_sec)
        # Pero la biblioteca `atlassian-python-api` en realidad tiene:
        # issue_worklog(self, issue_key, timeSpentSeconds, started=None, comment=None, ...)
        # Así que usaremos los nombres de argumento de la biblioteca real.

        logger.debug(f"Datos para issue_worklog: issue='{issue_key}', started='{started_formatted}', timeSeconds={time_spent_seconds}, comment='{comment}'")
        response = jira_client.issue_worklog(
                issue_key,          # 1er: issue_key
                started_formatted,  # 2do: started (formato ISO)
                time_spent_seconds, # 3ro: time_in_sec
                comment=comment     # 4to: Intentamos pasar comment como kwarg
        )
        # ----------------------------------------------

        if response:
            logger.info(f"Worklog añadido exitosamente a {issue_key}.")
            return f"Tiempo '{time_spent}' (equivalente a {time_spent_seconds}s) registrado exitosamente en el issue {issue_key}."
        else:
            logger.info(f"Worklog añadido a {issue_key} (sin respuesta detallada de la API).")
            return f"Tiempo '{time_spent}' registrado exitosamente en el issue {issue_key}."

    except ApiError as e:
        logger.exception(f"Error de API Jira al añadir worklog a {issue_key}: {e.status_code} - {e.response.text}")
        error_text = e.response.text
        try:
            error_json = json.loads(error_text)
            error_messages = error_json.get("errorMessages", [])
            errors = error_json.get("errors", {})
            if error_messages:
                error_text = " ".join(error_messages)
            elif errors:
                error_text = json.dumps(errors)
        except json.JSONDecodeError:
            pass
        return f"Error de API al registrar tiempo en '{issue_key}': {error_text}"
    except TypeError as e: # <-- Capturar específicamente TypeError
        logger.exception(f"TypeError al llamar a issue_worklog para {issue_key}. ¿Argumentos incorrectos?")
        # Si el TypeError es sobre 'comment', intentamos sin él
        if 'comment' in str(e):
            logger.warning("Reintentando issue_worklog sin el argumento 'comment'.")
            try:
                response = jira_client.issue_worklog(
                    issue_key,
                    started_formatted,
                    time_spent_seconds
                    # Sin comment
                )
                if response:
                     logger.info(f"Worklog añadido (sin comentario) a {issue_key}.")
                     return f"Tiempo '{time_spent}' registrado en {issue_key} (no se pudo añadir comentario por posible incompatibilidad)."
                else:
                     logger.info(f"Worklog añadido (sin comentario) a {issue_key} (sin respuesta detallada).")
                     return f"Tiempo '{time_spent}' registrado exitosamente en {issue_key} (sin comentario)."
            except Exception as inner_e:
                logger.exception(f"Error en reintento de issue_worklog sin comentario para {issue_key}.")
                return f"Error al registrar tiempo en '{issue_key}' incluso sin comentario: {inner_e}"
        else:
            # Si el TypeError es por otro argumento, devolvemos el error
             return f"Error de tipo en los argumentos al registrar tiempo en '{issue_key}': {e}"
    except Exception as e:
        logger.exception(f"Error inesperado al añadir worklog a {issue_key}.")
        return f"Error inesperado al registrar tiempo en '{issue_key}': {e}"
    
@jira_agent.tool()
async def jira_add_comment(ctx: RunContext[JiraAgentDeps], issue_key: str, comment: str) -> str:
    """
    Añade un comentario a un issue específico de Jira.

    Args:
        issue_key (str): La clave única del issue donde añadir el comentario (ej. 'PROJ-123').
        comment (str): El texto del comentario a añadir (se permite formato Markdown básico).

    Returns:
        str: Un mensaje de confirmación si el comentario fue añadido exitosamente, o un mensaje de error.
    """
    logger.info(f"Ejecutando herramienta: jira_add_comment (issue_key={issue_key})")
    if not issue_key or not comment:
        logger.warning("Intento de llamar a jira_add_comment sin issue_key o comment.")
        return "Por favor, proporciona la clave del issue y el texto del comentario."

    try:
        jira_client: Jira = ctx.deps.jira_client
        logger.debug(f"Añadiendo comentario a {issue_key}: '{comment[:50]}...'")

        # Convertir Markdown básico a formato ADF de Jira si es posible
        # (Usaremos texto plano por ahora, como en add_worklog)
        # adf_comment = markdown_to_adf(comment) # Función hipotética
        comment_body = comment # Usamos texto plano

        # Usar el método add_comment de la biblioteca
        response = jira_client.issue_add_comment(
            issue_key,
            comment_body
        )

        # Verificar la respuesta (la biblioteca podría devolver el objeto comentario o True/None)
        if response: # Asumiendo que devuelve algo en éxito
            logger.info(f"Comentario añadido exitosamente a {issue_key}.")
            # Podríamos incluir el ID del comentario si la respuesta lo tuviera: response.get('id')
            return f"Comentario añadido exitosamente al issue {issue_key}."
        else:
            # Si no devuelve nada pero no lanzó error, asumimos éxito
            logger.info(f"Comentario añadido exitosamente a {issue_key} (sin respuesta detallada de la API).")
            return f"Comentario añadido exitosamente al issue {issue_key}."


    except ApiError as e:
         logger.exception(f"Error de API Jira al añadir comentario a {issue_key}: {e.status_code} - {e.response.text}")
         # Inicializar error_text con la respuesta cruda
         error_text = e.response.text # <--- INICIALIZAR AQUÍ
         try:
             # Intentar parsear y extraer mensajes más específicos
             error_json = json.loads(e.response.text) # Usar e.response.text aquí también
             error_messages = error_json.get("errorMessages", [])
             errors = error_json.get("errors", {})
             if error_messages:
                 error_text = " ".join(error_messages) # Sobrescribir si encontramos algo mejor
             elif errors:
                 error_text = json.dumps(errors) # Sobrescribir si encontramos algo mejor
         except json.JSONDecodeError:
             # Si no es JSON, error_text ya tiene el valor original
             pass
         # Ahora error_text siempre tiene un valor asignado antes del return
         return f"Error de API al añadir comentario a '{issue_key}': {error_text}"
    except Exception as e:
        logger.exception(f"Error inesperado al añadir comentario a {issue_key}.")
        return f"Error inesperado al añadir comentario a '{issue_key}': {e}"


# --- Lógica principal para ejecutar el agente (ejemplo) ---
async def run_jira_conversation(user_input: str, message_history: list[ModelMessage] | None = None) -> tuple[list[ModelMessage], str]:
    """Ejecuta una ronda de conversación con el agente Jira."""
    if message_history is None:
        message_history = []

    # --- Configuración del cliente Jira ---
    logger.info("Iniciando configuración del cliente Jira...") # <--- LOG
    jira_url = os.getenv("JIRA_URL")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API_TOKEN")
    jira_personal_token = os.getenv("JIRA_PERSONAL_TOKEN")
    jira_ssl_verify_str = os.getenv("JIRA_SSL_VERIFY", "true")
    jira_ssl_verify = jira_ssl_verify_str.lower() == "true"

    if not jira_url:
        logger.error("JIRA_URL no está configurado en el archivo .env") # <--- LOG
        raise ValueError("JIRA_URL no está configurado en el archivo .env")

    jira_client = None
    auth_method = "Ninguno" # <--- Para loguear
    if jira_personal_token:
        auth_method = "Token Personal (Server/DC)" # <--- Para loguear
        logger.info(f"Usando autenticación Jira con {auth_method}") # <--- LOG
        jira_client = Jira(
            url=jira_url,
            token=jira_personal_token,
            verify_ssl=jira_ssl_verify
        )
    elif jira_username and jira_api_token:
        auth_method = "Email/Token API (Cloud)" # <--- Para loguear
        logger.info(f"Usando autenticación Jira con {auth_method}") # <--- LOG
        jira_client = Jira(
            url=jira_url,
            username=jira_username,
            password=jira_api_token,
            cloud=True
        )
    else:
        logger.error("No se proporcionaron credenciales válidas de Jira en .env") # <--- LOG
        raise ValueError("No se proporcionaron credenciales válidas de Jira en .env (ni Cloud ni Server/DC)")

    logger.info(f"Cliente Jira ({auth_method}) configurado para URL: {jira_url}") # <--- LOG
    deps = JiraAgentDeps(jira_client=jira_client)

    # Logueamos la entrada del usuario ANTES de pasarla al agente
    logger.info(f"Input del Usuario: {user_input}")
    # No logueamos el historial completo por brevedad, pero podríamos hacerlo si fuera necesario
    # logger.debug(f"Historial de entrada: {message_history}")

    # print(f"\nUsuario: {user_input}") # Mantenemos el print para la interacción en consola
    # print("Agente Jira pensando...")

    try: # <--- Añadir try...except para loguear errores del agente
        result = await jira_agent.run(
            user_input,
            deps=deps,
            message_history=message_history
        )
        agent_response_text = result.data
        new_messages_this_round = result.new_messages()

        # Logueamos la respuesta ANTES de devolverla
        logger.info(f"Respuesta del Agente: {agent_response_text}")
        # Podríamos loguear los mensajes completos si necesitamos depurar ToolCalls, etc.
        # logger.debug(f"Nuevos mensajes de la ronda: {new_messages_this_round}")

        # print(f"Agente Jira: {agent_response_text}") # Mantenemos print para consola
        return new_messages_this_round, agent_response_text

    except Exception as e:
        logger.exception("Ocurrió un error durante la ejecución de jira_agent.run()") # <--- LOG con traceback
        # Relanzamos la excepción para que sea manejada por el bucle `chat`
        raise

@jira_agent.tool()
async def jira_get_transitions(ctx: RunContext[JiraAgentDeps], issue_key: str) -> str:
    """
    Obtiene las transiciones de estado posibles para un issue específico de Jira.
    Esto muestra a qué estados se puede mover el issue desde su estado actual.

    Args:
        issue_key (str): La clave única del issue (ej. 'PROJ-123').

    Returns:
        str: Una cadena JSON formateada con la lista de transiciones disponibles.
             Cada transición tiene un 'id' (necesario para cambiar el estado) y un 'name' (nombre del estado destino).
             Ejemplo: '[{"id": "11", "name": "To Do"}, {"id": "21", "name": "In Progress"}]'
             Devuelve un mensaje de error si falla.
    """
    logger.info(f"Ejecutando herramienta: jira_get_transitions (issue_key={issue_key})")
    if not issue_key:
        logger.warning("Intento de llamar a jira_get_transitions sin issue_key.")
        return "Por favor, proporciona la clave del issue."

    try:
        jira_client: Jira = ctx.deps.jira_client
        logger.debug(f"Obteniendo transiciones para {issue_key}")

        # La documentación indica jira.get_issue_transitions(issue_key)
        transitions_data = jira_client.get_issue_transitions(issue_key)

        if not transitions_data or "transitions" not in transitions_data:
            logger.warning(f"No se encontraron transiciones para {issue_key}.")
            return f"No se encontraron transiciones disponibles para el issue {issue_key}."

        # Simplificar la salida para el LLM, incluyendo solo id y nombre del estado destino
        simplified_transitions = [
            {"id": t.get("id"), "name": t.get("to", {}).get("name", "Estado Desconocido")}
            for t in transitions_data.get("transitions", [])
        ]

        logger.info(f"Encontradas {len(simplified_transitions)} transiciones para {issue_key}.")
        return json.dumps(simplified_transitions, indent=2, ensure_ascii=False)

    except ApiError as e:
        logger.exception(f"Error de API Jira al obtener transiciones para {issue_key}: {e.status_code} - {e.response.text}")
        # ... (extracción de mensaje de error) ...
        error_text = e.response.text
        try:
            error_json = json.loads(error_text); error_messages = error_json.get("errorMessages", []); errors = error_json.get("errors", {})
            if error_messages: error_text = " ".join(error_messages)
            elif errors: error_text = json.dumps(errors)
        except json.JSONDecodeError: pass
        return f"Error de API al obtener transiciones para '{issue_key}': {error_text}"
    except Exception as e:
        logger.exception(f"Error inesperado al obtener transiciones para {issue_key}.")
        return f"Error inesperado al obtener transiciones para '{issue_key}': {e}"

@jira_agent.tool()
async def jira_transition_issue(ctx: RunContext[JiraAgentDeps], issue_key: str, transition_id: str, comment: Optional[str] = None, fields: Optional[str] = None) -> str:
    """
    Realiza una transición de estado en un issue de Jira usando el ID de la transición.
    Obtén primero los IDs disponibles con la herramienta 'jira_get_transitions'.

    Args:
        issue_key (str): La clave única del issue (ej. 'PROJ-123').
        transition_id (str): El ID de la transición a ejecutar (obtenido de 'jira_get_transitions').
        comment (Optional[str]): Un comentario opcional a añadir durante la transición.
        fields (Optional[str]): Un JSON string con campos adicionales requeridos por la transición
                                 (ej. '{"resolution": {"name": "Fixed"}}'). A menudo no es necesario.

    Returns:
        str: Mensaje de confirmación o error.
    """
    logger.info(f"Ejecutando herramienta: jira_transition_issue (issue_key={issue_key}, transition_id={transition_id})")
    if not issue_key or not transition_id:
        logger.warning("Intento de llamar a jira_transition_issue sin issue_key o transition_id.")
        return "Por favor, proporciona la clave del issue y el ID de la transición."

    try:
        jira_client: Jira = ctx.deps.jira_client

        # Parsear los campos adicionales si se proporcionan
        update_fields = {}
        if fields:
            try:
                update_fields = json.loads(fields)
                if not isinstance(update_fields, dict):
                    raise ValueError("El argumento 'fields' debe ser un objeto JSON válido.")
            except (json.JSONDecodeError, ValueError) as json_error:
                logger.error(f"Error al parsear el JSON de 'fields': {fields} - {json_error}")
                return f"Error: El argumento 'fields' no es un JSON válido: {json_error}"

        logger.debug(f"Transicionando {issue_key} con ID {transition_id}. Campos adicionales: {update_fields}, Comentario: {comment}")

        # La documentación indica issue_transition(issue_key, status), donde status es el ID.
        # La biblioteca real espera: issue_transition(issue_key, transition_id, comment=None, fields=None, ...)
        response = jira_client.issue_transition(
            issue_key=issue_key,
            transition_id=transition_id,
            comment=comment,
            fields=update_fields if update_fields else None # Pasar None si está vacío
        )

        # La llamada issue_transition a menudo no devuelve nada en éxito, solo lanza error si falla.
        # La documentación de la lib indica que devuelve True/False, pero puede variar.
        # Asumimos éxito si no hay excepción.
        logger.info(f"Transición {transition_id} aplicada exitosamente a {issue_key}.")
        return f"Issue {issue_key} transicionado exitosamente usando ID {transition_id}."

    except ApiError as e:
        logger.exception(f"Error de API Jira al transicionar {issue_key}: {e.status_code} - {e.response.text}")
        error_text = e.response.text
        try:
            error_json = json.loads(error_text); error_messages = error_json.get("errorMessages", []); errors = error_json.get("errors", {})
            if error_messages: error_text = " ".join(error_messages)
            elif errors: error_text = json.dumps(errors)
        except json.JSONDecodeError: pass
        return f"Error de API al transicionar '{issue_key}': {error_text}"
    except Exception as e:
        logger.exception(f"Error inesperado al transicionar {issue_key}.")
        return f"Error inesperado al transicionar '{issue_key}': {e}"

if __name__ == '__main__':
    import asyncio

    async def chat():
        logger.info("Iniciando bucle de chat interactivo.") # <--- LOG
        # print("Iniciando chat con Jira Assistant (escribe 'salir' para terminar)")
        history: list[ModelMessage] = []
        while True:
            try:
                user_message = input("Tú: ")
                if user_message.lower() == 'salir':
                    logger.info("Usuario solicitó salir del chat.") # <--- LOG
                    break

                new_messages, agent_response = await run_jira_conversation(user_message, history)
                history.extend(new_messages)

            except Exception as e:
                # El error ya se logueó en run_jira_conversation
                # print(f"\nError en la conversación: {e}. Intenta de nuevo o escribe 'salir'.")
                # Considera qué hacer con el historial aquí si es un error grave
                logger.exception("Ocurrió un error durante la ejecución de jira_agent.run()",e)

@jira_agent.tool()
async def jira_search_issues_by_text(ctx: RunContext[JiraAgentDeps], search_text: str, project_key: Optional[str] = None, max_results: int = 5) -> str:
    """
    Busca issues en Jira cuyo resumen o descripción contengan el texto proporcionado.
    Es útil cuando no se conoce la clave exacta del issue.

    Args:
        search_text (str): El texto a buscar en el resumen o descripción de los issues (ej. "Reunión diaria", "Error login").
        project_key (Optional[str]): Limita la búsqueda a un proyecto específico (ej. 'PROJ'). Si es None, busca en todos los proyectos visibles.
        max_results (int): Número máximo de issues a devolver (por defecto 5, máximo 20).

    Returns:
        str: Una cadena JSON formateada con la lista de issues encontrados (clave, resumen, estado)
             o un mensaje indicando que no se encontraron issues.
    """
    logger.info(f"Ejecutando herramienta: jira_search_issues_by_text (texto='{search_text}', proyecto='{project_key}')")
    if not search_text:
        return "Por favor, proporciona el texto que quieres buscar."

    try:
        jira_client: Jira = ctx.deps.jira_client
        limit = max(1, min(max_results, 20))

        # Construir la consulta JQL
        # Usamos el operador ~ que busca texto (case-insensitive, stemming)
        # Buscamos en summary y description
        jql_parts = [f'(summary ~ "{escape_jql_string(search_text)}" OR description ~ "{escape_jql_string(search_text)}")']

        if project_key:
            jql_parts.append(f'project = "{escape_jql_string(project_key)}"')

        # Podríamos añadir un filtro de estado si quisiéramos, ej: AND status != Done
        # jql_parts.append("statusCategory != Done")

        jql_query = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        logger.debug(f"Ejecutando JQL por texto: {jql_query} con límite {limit}")

        issues = jira_client.jql(
            jql_query,
            limit=limit,
            fields="key,summary,status,assignee" # Incluir assignee para la Mejora 2
        )

        if not issues or not issues.get('issues'):
            logger.info(f"No se encontraron issues con el texto '{search_text}' (proyecto: {project_key}).")
            return f"No se encontraron issues que contengan '{search_text}'" + (f" en el proyecto {project_key}." if project_key else ".")

        results_list = [
            {
                "key": issue.get('key'),
                "summary": issue.get('fields', {}).get('summary', 'N/A'),
                "status": issue.get('fields', {}).get('status', {}).get('name', 'N/A'),
                "assignee": issue.get('fields', {}).get('assignee', {}).get('displayName', 'Sin asignar') if issue.get('fields', {}).get('assignee') else 'Sin asignar'
            }
            for issue in issues.get('issues', [])
        ]

        logger.info(f"Encontrados {len(results_list)} issues con el texto '{search_text}'.")
        return json.dumps(results_list, indent=2, ensure_ascii=False)

    except ApiError as e:
        logger.exception(f"Error de API Jira al buscar issues por texto '{search_text}'.")
        error_text = e.response.text # ... (mismo manejo de ApiError que antes) ...
        try:
            error_json = json.loads(error_text); error_messages = error_json.get("errorMessages", []); errors = error_json.get("errors", {})
            if error_messages: error_text = " ".join(error_messages)
            elif errors: error_text = json.dumps(errors)
        except json.JSONDecodeError: pass
        return f"Error de API al buscar issues por texto: {error_text}"
    except Exception as e:
        logger.exception(f"Error inesperado al buscar issues por texto '{search_text}'.")
        return f"Error inesperado al buscar issues por texto: {e}"

    asyncio.run(chat())

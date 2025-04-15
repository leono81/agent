# mcp/mcp_server_jira.py
import asyncio
import logging
import os
import sys
import uuid
from typing import Any, List, Dict

# --- Añadir ruta del proyecto al sys.path ---
# Esto es crucial para que 'mcp dev' pueda importar desde otros directorios
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# -------------------------------------------

# --- Usar FastMCP de mcp.server.fastmcp ---
# La documentación oficial y ejemplos usan esta ruta.
# Aunque 'from mcp import FastMCP' funcionó antes, esta es más explícita.
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent
from utils.utils import setup_logger
from jira_agent.jira_tool_agent import run_jira_conversation
from pydantic_ai.messages import ModelMessage

# Configurar logger para el servidor MCP
# Usar el nombre del módulo es una buena práctica
logger = setup_logger(__name__) # logger = setup_logger("mcp_jira") es otra opción

# Inicializar FastMCP con un nombre descriptivo
mcp = FastMCP("jira_assistant_server") # Cambiado para evitar posible colisión con el nombre del módulo si es importado

@mcp.tool()
async def ping() -> List[TextContent]:
    """
    Herramienta simple para verificar que el servidor MCP está respondiendo.
    No requiere argumentos.
    Devuelve: Un mensaje 'pong'.
    """
    logger.info("Ejecutando herramienta 'ping'")
    return [TextContent(text="pong")]

@mcp.tool()
async def ask_jira_agent(query: str) -> List[TextContent]:
    """
    Envía una consulta al agente conversacional de Jira y devuelve su respuesta.
    El agente puede buscar issues, registrar tiempo, cambiar estados, etc.

    Args:
        query (str): La pregunta o comando del usuario para el agente Jira.

    Returns:
        List[TextContent]: La respuesta del agente como texto.
    """
    logger.info(f"Ejecutando herramienta 'ask_jira_agent' con query: '{query}'")
    try:
        # Por ahora, sin historial persistente entre llamadas MCP
        message_history_input = None

        # Llamamos a la función principal de nuestro agente
        new_messages, agent_response_text = await run_jira_conversation(
            user_input=query,
            message_history=message_history_input
        )

        logger.info(f"Respuesta recibida del agente: '{agent_response_text[:100]}...'")
        # Corrección: Devolver una lista con un objeto TextContent válido, incluyendo el campo 'type'
        return [TextContent(type="text", text=agent_response_text)] # <--- Añadido type="text"

    except Exception as e:
        logger.exception(f"Error al ejecutar 'ask_jira_agent' con query: '{query}'")
        error_message = f"Hubo un error procesando tu solicitud para Jira: {e}"
        # Ya habíamos corregido este:
        return [TextContent(type="text", text=error_message)]

# --- NO INCLUIR el bloque if __name__ == "__main__": mcp.run() ---
# Esto permite que 'mcp dev' y 'mcp run' funcionen correctamente,
# ya que ellos se encargan de ejecutar el servidor definido en este script.
# Si necesitaras ejecutarlo directamente con 'python mcp/mcp_jira.py',
# entonces sí descomentarías ese bloque.
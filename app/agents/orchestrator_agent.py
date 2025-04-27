import os
from typing import Optional, Dict, Any, List
import logfire
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from app.agents.jira_agent import JiraAgent
from app.agents.confluence_agent import ConfluenceAgent
from app.agents.incident_template_agent import IncidentTemplateAgent
from datetime import datetime, date, timedelta

class SharedContext(BaseModel):
    """Shared context that maintains conversation state between agents."""
    conversation_history: List[Dict[str, str]] = []
    active_agent: Optional[str] = None
    last_query: Optional[str] = None
    metadata: Dict[str, Any] = {}
    current_date: str = datetime.now().strftime("%Y-%m-%d")  # Fecha actual en formato ISO

    def add_user_message(self, content: str):
        """Add a user message to the conversation history."""
        self.conversation_history.append({"role": "user", "content": content})
        self.last_query = content

    def add_assistant_message(self, content: str, agent_type: str):
        """Add an assistant message to the conversation history."""
        self.conversation_history.append({
            "role": "assistant", 
            "content": content,
            "agent_type": agent_type
        })
        
    def update_current_date(self):
        """Update the current date in the context."""
        now = datetime.now()
        self.current_date = now.strftime("%Y-%m-%d")
        
        # Formato de fecha estándar
        self.metadata["current_date"] = self.current_date
        
        # Intentar obtener los nombres en español
        try:
            import locale
            saved_locale = locale.getlocale(locale.LC_TIME)
            try:
                locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
                self.metadata["current_date_human"] = now.strftime("%d de %B de %Y")
                self.metadata["weekday"] = now.strftime("%A")
            except locale.Error:
                # Si falla, usar un mapeo manual
                self.metadata["current_date_human"] = now.strftime("%d de %B de %Y")
                
                # Mapeo manual de meses
                month_names = {
                    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 
                    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
                    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
                }
                
                # Mapeo manual de días de la semana
                weekday_names = {
                    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
                    4: "viernes", 5: "sábado", 6: "domingo"
                }
                
                # Aplicar mapeo manual
                self.metadata["current_date_human"] = f"{now.day} de {month_names[now.month]} de {now.year}"
                self.metadata["weekday"] = weekday_names[now.weekday()]
            finally:
                # Restaurar el locale original
                locale.setlocale(locale.LC_TIME, saved_locale)
        except (ImportError, ValueError) as e:
            # Fallback si hay problemas con locale
            self.metadata["current_date_human"] = now.strftime("%d de %B de %Y")
            self.metadata["weekday"] = now.strftime("%A")
            logfire.warning(f"Error al formatear fecha: {e}")
        
        # Agregar otros formatos útiles
        self.metadata["iso_date"] = now.strftime("%Y-%m-%d")
        self.metadata["date_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.metadata["time"] = now.strftime("%H:%M")
        
        # Para casos especiales como 3 de noviembre de 2023
        special_date = datetime(2023, 11, 3)
        self.metadata["is_special_date"] = False  # Siempre falso, la fecha es actual

class OrchestratorAgent:
    """
    Orchestrator agent that delegates queries to specialized agents.
    
    This agent determines whether a query should be handled by the Jira agent
    or the Confluence agent, and maintains conversation context between them.
    """
    
    def __init__(self):
        """Initialize the orchestrator agent and its specialized sub-agents."""
        logfire.info("Initializing OrchestratorAgent")
        
        # Initialize shared context
        self.context = SharedContext()
        self.context.update_current_date()
        
        # Initialize the specialized agents
        self.jira_agent = JiraAgent()
        self.confluence_agent = ConfluenceAgent()
        self.incident_template_agent = IncidentTemplateAgent()
        
        # Add fecha actual to all agent contexts for proper date handling
        if "context" in self.jira_agent._deps.__dict__:
            self.jira_agent._deps.context["current_date"] = self.context.current_date
            self.jira_agent._deps.context["current_date_human"] = self.context.metadata["current_date_human"]
            self.jira_agent._deps.context["weekday"] = self.context.metadata["weekday"]
            
        if "context" in self.confluence_agent._deps.__dict__:
            self.confluence_agent._deps.context["current_date"] = self.context.current_date
            self.confluence_agent._deps.context["current_date_human"] = self.context.metadata["current_date_human"]
            self.confluence_agent._deps.context["weekday"] = self.context.metadata["weekday"]
        
        # Define classifier prompt
        self.classifier_prompt = f"""
        Determine whether the following query is related to Jira, Confluence, or Incident Templates:
        
        - Jira: Issues, tickets, stories, tasks, sprints, boards, projects, assignments, worklog, time tracking, transitions
        - Confluence: Documents, documentation, wiki pages, spaces, knowledge base, articles
        - Incident Templates: Registrar incidente, registrar problema, crear incidente, template de incidente, incidente mayor
        
        Today's date is {self.context.current_date} ({self.context.metadata["current_date_human"]}).
        
        Only respond with "jira", "confluence", "incident" or "unsure".
        """
        
        # Initialize the classifier agent
        self.classifier = Agent(
            model="openai:gpt-4o",
            system_prompt=self.classifier_prompt
        )
        
        logfire.info("OrchestratorAgent initialized successfully")

    def classify_query(self, query: str) -> str:
        """
        Classify the query as related to Jira, Confluence, Incident Templates, or unsure.
        
        Args:
            query: The user's query to classify
            
        Returns:
            str: "jira", "confluence", "incident", or "unsure"
        """
        logfire.info(f"Classifying query: {query}")
        
        try:
            # Get classification from the agent
            result = self.classifier.run_sync(query)
            classification = result.data.lower().strip()
            
            # Validate and normalize the result
            if "jira" in classification:
                return "jira"
            elif "confluence" in classification:
                return "confluence"
            elif "incident" in classification:
                return "incident"
            else:
                return "unsure"
        except Exception as e:
            logfire.error(f"Error classifying query: {e}")
            return "unsure"

    def determine_agent_with_context(self, query: str) -> str:
        """
        Determine which agent to use based on the query and conversation context.
        
        Args:
            query: The user's query
            
        Returns:
            str: "jira", "confluence", or "incident"
        """
        # If we have an active agent from previous conversation, use that
        # unless the query seems clearly related to the other agent
        if self.context.active_agent:
            classification = self.classify_query(query)
            
            # If the classification is clear and different from the active agent,
            # switch agents
            if classification != "unsure" and classification != self.context.active_agent:
                logfire.info(f"Switching from {self.context.active_agent} to {classification}")
                return classification
            
            # Otherwise stick with the active agent
            return self.context.active_agent
        
        # No active agent, classify the query
        classification = self.classify_query(query)
        
        # If classification is unsure, default to Jira as it's more common
        if classification == "unsure":
            logfire.info("Classification unsure, defaulting to Jira")
            return "jira"
        
        return classification

    def process_message_sync(self, message: str) -> str:
        """
        Process a message from the user and return a response.
        
        Args:
            message: The user's message
            
        Returns:
            str: The response from the appropriate agent
        """
        logfire.info(f"Processing message: {message}")
        
        try:
            # Add the user message to the conversation history
            self.context.add_user_message(message)
            
            # Check if we're in incident creation flow
            if "incident_flow" in self.context.metadata and self.context.metadata["incident_flow"]["active"]:
                return self._handle_incident_flow(message)
            
            # Determine which agent to use
            agent_type = self.determine_agent_with_context(message)
            self.context.active_agent = agent_type
            
            # Handle based on agent type
            response = ""
            if agent_type == "jira":
                logfire.info("Using Jira agent")
                response = self.jira_agent.process_message_sync(message)
            elif agent_type == "confluence":
                logfire.info("Using Confluence agent")
                response = self.confluence_agent.process_message_sync(message)
            elif agent_type == "incident":
                logfire.info("Using Incident Template agent")
                
                # Iniciar el flujo de creación de incidentes
                # Primero configuramos el estado del flujo
                self.context.metadata["incident_flow"] = {
                    "active": True,
                    "current_step": 0,
                    "collected_data": {
                        "fecha_incidente": datetime.now().strftime("%Y-%m-%d")  # Fecha actual por defecto
                    },
                    "temp_list_items": []
                }
                
                # Obtener la primera pregunta del template
                first_question = self.incident_template_agent.template_config[0]
                
                # Crear la respuesta inicial
                response = (
                    "Entendido. Voy a ayudarte a registrar un incidente mayor. "
                    "Te guiaré paso a paso para recopilar toda la información necesaria.\n\n"
                    f"{first_question['question']}"
                )
                
                # Si hay texto de ayuda, incluirlo
                if 'help_text' in first_question:
                    response += f"\n\n{first_question['help_text']}"
                
                # Si es un campo de selección, mostrar opciones
                if first_question['type'] == 'choice' and 'options' in first_question:
                    options_text = "\n".join([f"- {option}" for option in first_question['options']])
                    response += f"\n\nOpciones disponibles:\n{options_text}"
                
                # Indicar cómo cancelar
                response += "\n\n(Puedes escribir 'cancelar' en cualquier momento para detener el proceso)"
                
            else:
                logfire.warning(f"Unknown agent type: {agent_type}")
                response = "Lo siento, no puedo determinar qué agente debe manejar esta consulta."
            
            # Add the response to the conversation history
            self.context.add_assistant_message(response, agent_type)
            
            return response
            
        except Exception as e:
            logfire.exception(f"Error processing message: {e}")
            return f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"
    
    def _handle_incident_flow(self, message: str) -> str:
        """
        Maneja el flujo de creación de incidentes una vez iniciado.
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            str: Respuesta al usuario
        """
        # Obtener estado actual del flujo
        flow_data = self.context.metadata["incident_flow"]
        current_step = flow_data["current_step"]
        template_config = self.incident_template_agent.template_config
        
        # Verificar si se quiere cancelar el proceso
        if message.lower() in ["cancelar", "salir", "cancel", "exit", "detener"]:
            # Limpiar el estado del flujo de incidentes
            self.context.metadata["incident_flow"]["active"] = False
            response = "Proceso de creación de incidente cancelado. ¿En qué más puedo ayudarte?"
            self.context.add_assistant_message(response, "incident")
            return response
        
        # Verificar si estamos en el paso de confirmación
        if flow_data.get("confirmation_step", False):
            if message.lower() in ["sí", "si", "yes", "confirmar", "confirmo"]:
                # El usuario ha confirmado, crear la página de incidente
                return self._create_incident_page()
            elif message.lower() in ["no", "corregir", "editar", "modificar"]:
                # El usuario quiere corregir la información
                flow_data["confirmation_step"] = False
                flow_data["current_step"] = 0  # Reiniciar desde el primer paso
                
                # Obtener la primera pregunta
                first_question = template_config[0]
                response = (
                    "Vamos a corregir la información. Comencemos de nuevo.\n\n"
                    f"{first_question['question']}"
                )
                
                # Si hay texto de ayuda, incluirlo
                if 'help_text' in first_question:
                    response += f"\n\n{first_question['help_text']}"
                
                # Si es un campo de selección, mostrar opciones
                if first_question['type'] == 'choice' and 'options' in first_question:
                    options_text = "\n".join([f"- {option}" for option in first_question['options']])
                    response += f"\n\nOpciones disponibles:\n{options_text}"
                
                self.context.add_assistant_message(response, "incident")
                return response
            else:
                # Respuesta no reconocida
                response = (
                    "No entendí tu respuesta. Por favor confirma si la información es correcta respondiendo 'sí' para crear "
                    "la página de incidente, o 'no' si deseas corregir algún dato."
                )
                self.context.add_assistant_message(response, "incident")
                return response
        
        # Verificar si hemos terminado de recopilar todos los datos
        if current_step >= len(template_config):
            # Preparar el resumen para confirmación
            flow_data["confirmation_step"] = True
            summary = self._prepare_incident_summary()
            
            response = (
                "¡Gracias! He recopilado toda la información necesaria.\n\n"
                f"{summary}\n\n"
                "¿Es correcta toda la información? Responde 'sí' para crear la página de incidente, "
                "o 'no' si deseas corregir algún dato."
            )
            self.context.add_assistant_message(response, "incident")
            return response
        
        # Obtener la configuración del paso actual
        current_config = template_config[current_step]
        current_key = current_config['key']
        current_type = current_config['type']
        collected_data = flow_data["collected_data"]
        
        # Procesar la respuesta según el tipo de campo
        if current_type == 'text' or current_type == 'multiline_text':
            # Guardar el texto directamente
            collected_data[current_key] = message
            # Avanzar al siguiente paso
            flow_data["current_step"] += 1
            
        elif current_type == 'choice':
            # Verificar si la respuesta es una de las opciones válidas
            options = current_config.get('options', [])
            matched_option = None
            
            # Buscar coincidencia exacta primero
            if message in options:
                matched_option = message
            else:
                # Buscar coincidencia parcial ignorando mayúsculas/minúsculas
                message_lower = message.lower()
                for option in options:
                    if option.lower() in message_lower or message_lower in option.lower():
                        matched_option = option
                        break
            
            if matched_option:
                collected_data[current_key] = matched_option
                flow_data["current_step"] += 1
            else:
                # La respuesta no coincide con ninguna opción
                options_text = "\n".join([f"- {option}" for option in options])
                response = (
                    f"Tu respuesta '{message}' no coincide con ninguna de las opciones disponibles. "
                    f"Por favor, elige una de las siguientes opciones:\n{options_text}"
                )
                self.context.add_assistant_message(response, "incident")
                return response
                
        elif current_type == 'date_text':
            # Procesar la fecha
            parsed_date = self._parse_date(message)
            if parsed_date:
                collected_data[current_key] = parsed_date
                flow_data["current_step"] += 1
            else:
                response = (
                    f"No pude interpretar la fecha '{message}'. Por favor, utiliza uno de estos formatos: "
                    "DD/MM/YYYY, DD-MM-YYYY, o escribe 'hoy' para la fecha actual."
                )
                self.context.add_assistant_message(response, "incident")
                return response
                
        elif current_type == 'list_text' or current_type == 'list_structured':
            temp_list_items = flow_data.get("temp_list_items", [])
            
            # Si es un mensaje vacío y ya tenemos elementos, terminamos la lista
            if not message.strip() and temp_list_items:
                collected_data[current_key] = temp_list_items.copy()
                flow_data["temp_list_items"] = []  # Limpiar la lista temporal
                flow_data["current_step"] += 1
            # Si el usuario escribe "ninguno" o similar
            elif message.lower() in ["ninguno", "none", "no hay", "nadie"]:
                collected_data[current_key] = []
                flow_data["temp_list_items"] = []
                flow_data["current_step"] += 1
            else:
                # Agregar el elemento a la lista temporal
                if current_type == 'list_text':
                    # Para listas simples, dividir por comas si hay varias
                    items = [item.strip() for item in message.split(',') if item.strip()]
                    temp_list_items.extend(items)
                else:
                    # Para listas estructuradas, agregar como está
                    temp_list_items.append(message)
                
                flow_data["temp_list_items"] = temp_list_items
                
                # Preguntar si hay más elementos
                if 'follow_up' in current_config:
                    response = current_config['follow_up']
                    if current_type == 'list_structured' and 'help_text' in current_config:
                        response += f"\n\n{current_config['help_text']}"
                    
                    # Mostrar los elementos agregados hasta ahora
                    if temp_list_items:
                        items_text = "\n".join([f"- {item}" for item in temp_list_items])
                        response += f"\n\nElementos agregados hasta ahora:\n{items_text}"
                    
                    response += "\n\n(Deja el mensaje vacío para continuar)"
                    self.context.add_assistant_message(response, "incident")
                    return response
        
        # Si hemos llegado aquí, significa que se ha procesado la respuesta y avanzamos al siguiente paso
        
        # Verificar si hemos terminado de recopilar todos los datos después de actualizar current_step
        if flow_data["current_step"] >= len(template_config):
            # Preparar el resumen para confirmación
            flow_data["confirmation_step"] = True
            summary = self._prepare_incident_summary()
            
            response = (
                "¡Gracias! He recopilado toda la información necesaria.\n\n"
                f"{summary}\n\n"
                "¿Es correcta toda la información? Responde 'sí' para crear la página de incidente, "
                "o 'no' si deseas corregir algún dato."
            )
            self.context.add_assistant_message(response, "incident")
            return response
        
        # Obtener la siguiente pregunta
        next_config = template_config[flow_data["current_step"]]
        next_question = next_config['question']
        
        # Crear la respuesta para la siguiente pregunta
        response = next_question
        
        # Si hay texto de ayuda, incluirlo
        if 'help_text' in next_config:
            response += f"\n\n{next_config['help_text']}"
        
        # Si es un campo de selección, mostrar opciones
        if next_config['type'] == 'choice' and 'options' in next_config:
            options_text = "\n".join([f"- {option}" for option in next_config['options']])
            response += f"\n\nOpciones disponibles:\n{options_text}"
        
        self.context.add_assistant_message(response, "incident")
        return response
    
    def _parse_date(self, date_text: str) -> Optional[str]:
        """
        Parsea una entrada de texto a formato de fecha (YYYY-MM-DD).
        
        Args:
            date_text: Texto de la fecha a parsear
            
        Returns:
            str: Fecha parseada en formato YYYY-MM-DD o None si no se pudo parsear
        """
        try:
            if date_text.lower() == "hoy":
                return datetime.now().strftime("%Y-%m-%d")
            
            if date_text.lower() == "ayer":
                yesterday = datetime.now() - timedelta(days=1)
                return yesterday.strftime("%Y-%m-%d")
            
            # Intentar parsear formatos comunes
            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"]:
                try:
                    date_obj = datetime.strptime(date_text, fmt)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            
            # Si llegamos aquí, no se pudo parsear
            return None
        except Exception as e:
            logfire.error(f"Error al parsear fecha: {e}")
            return None
    
    def _prepare_incident_summary(self) -> str:
        """
        Prepara un resumen con la información del incidente recopilada.
        
        Returns:
            str: Resumen formateado del incidente
        """
        data = self.context.metadata["incident_flow"]["collected_data"]
        
        # Formatear las listas
        usuarios_txt = ""
        if "usuarios_soporte" in data and data["usuarios_soporte"]:
            usuarios_txt = "\n- " + "\n- ".join(data["usuarios_soporte"])
        else:
            usuarios_txt = "Ninguno"
        
        acciones_txt = ""
        if "acciones_realizadas" in data and data["acciones_realizadas"]:
            acciones_txt = "\n- " + "\n- ".join(data["acciones_realizadas"]) 
        else:
            acciones_txt = "Ninguna"
        
        resumen = f"""
📋 RESUMEN DEL INCIDENTE:
------------------------
Tipo de incidente: {data.get('tipo_incidente', 'N/A')}
Fecha del incidente: {data.get('fecha_incidente', 'N/A')}
Impacto: {data.get('impacto', 'N/A')}
Prioridad: {data.get('prioridad', 'N/A')}
Estado actual: {data.get('estado_actual', 'N/A')}
Unidad de negocio: {data.get('unidad_negocio', 'N/A')}

Descripción del problema:
{data.get('descripcion_problema', 'N/A')}

Usuarios de soporte: {usuarios_txt}

Acciones realizadas: {acciones_txt}

Fecha de resolución: {data.get('fecha_resolucion', 'Pendiente')}

Observaciones:
{data.get('observaciones', 'N/A')}
"""
        return resumen
    
    def _create_incident_page(self) -> str:
        """
        Crea la página de incidente en Confluence con los datos recopilados.
        
        Returns:
            str: Mensaje de respuesta al usuario
        """
        try:
            # Obtener los datos del incidente
            incident_data = self.context.metadata["incident_flow"]["collected_data"]
            
            # Validar datos mínimos requeridos
            required_fields = ['tipo_incidente', 'fecha_incidente', 'impacto', 'prioridad', 'estado_actual']
            missing_fields = [field for field in required_fields if field not in incident_data or not incident_data[field]]
            
            if missing_fields:
                response = (
                    f"No se puede crear la página de incidente porque faltan campos requeridos: "
                    f"{', '.join(missing_fields)}. Por favor, proporciona esta información."
                )
                self.context.add_assistant_message(response, "incident")
                return response
            
            # Construir un prompt específico para que el agente de Confluence cree la página
            space_key = "PSIMDESASW"  # Espacio predeterminado para incidentes
            
            # Formatear el mensaje para el agente de Confluence
            incident_str = "\n".join([f"{k}: {v}" for k, v in incident_data.items()])
            confluence_prompt = f"""
            Crea una página de incidente en el espacio {space_key} con los siguientes datos:
            
            {incident_str}
            """
            
            # Utilizar el método process_message_sync del agente de Confluence
            result_message = self.confluence_agent.process_message_sync(confluence_prompt)
            
            # Reiniciar el estado del flujo
            self.context.metadata["incident_flow"]["active"] = False
            
            # Analizar la respuesta para determinar si fue exitosa
            if "exitosamente" in result_message.lower() or "creada" in result_message.lower():
                # Extraer URL si está presente en la respuesta
                import re
                url_match = re.search(r'(https?://[^\s]+)', result_message)
                url = url_match.group(0) if url_match else "No disponible"
                
                # Extraer título si está presente
                title_match = re.search(r'Título: ([^\n]+)', result_message)
                title = title_match.group(1) if title_match else "Incidente creado"
                
                response = (
                    f"✅ ¡Página de incidente creada exitosamente!\n\n"
                    f"Título: {title}\n"
                    f"URL: {url}\n\n"
                    f"¿En qué más puedo ayudarte?"
                )
            else:
                response = (
                    f"❌ Hubo un problema al crear la página de incidente:\n\n"
                    f"{result_message}\n\n"
                    f"Los datos del incidente siguen guardados. Puedes intentar nuevamente "
                    f"o contactar al administrador del sistema para resolver el problema."
                )
            
            self.context.add_assistant_message(response, "incident")
            return response
        except Exception as e:
            logfire.error(f"Error al crear página de incidente: {e}")
            response = f"Error al crear la página de incidente: {str(e)}"
            self.context.add_assistant_message(response, "incident")
            return response 
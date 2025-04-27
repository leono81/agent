import os
from typing import Optional, Dict, Any, List
import logfire
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from app.agents.jira_agent import JiraAgent
from app.agents.confluence_agent import ConfluenceAgent
from app.agents.incident_template_agent import IncidentTemplateAgent
from datetime import datetime, date

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
                
                # Informar al usuario que se utilizará el agente de incidentes
                response = (
                    "Entendido. Necesitas registrar un incidente mayor. "
                    "Te redirigiré al Agente de Templates de Incidentes (ATI) para recopilar toda la información necesaria. "
                    "Por favor, ejecuta: streamlit run incident_template_app.py\n\n"
                    "Una vez que hayas completado la información del incidente, los datos serán enviados "
                    "automáticamente al agente de Confluence para crear la página correspondiente."
                )
                
                # Nota: En una implementación más integrada, podríamos iniciar el agente directamente 
                # y recuperar los datos para pasarlos al agente de Confluence, algo como:
                #
                # incident_data = self.incident_template_agent.create_incident_template_app()
                # if incident_data:
                #     # Pasar los datos al agente de Confluence para crear la página
                #     confluence_response = self.confluence_agent.create_incident_page(incident_data)
                #     response += f"\n\nIncidente registrado correctamente. {confluence_response}"
            else:
                logfire.warning(f"Unknown agent type: {agent_type}")
                response = "Lo siento, no puedo determinar qué agente debe manejar esta consulta."
            
            # Add the response to the conversation history
            self.context.add_assistant_message(response, agent_type)
            
            return response
            
        except Exception as e:
            logfire.exception(f"Error processing message: {e}")
            return f"Lo siento, ocurrió un error al procesar tu mensaje: {e}" 
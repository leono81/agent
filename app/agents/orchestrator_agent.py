import os
from typing import Optional, Dict, Any, List
import logfire
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from app.agents.jira_agent import JiraAgent
from app.agents.confluence_agent import ConfluenceAgent
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
        
        # Add fecha actual to both agent contexts for proper date handling
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
        Determine whether the following query is related to Jira or Confluence:
        
        - Jira: Issues, tickets, stories, tasks, sprints, boards, projects, assignments, worklog, time tracking, transitions
        - Confluence: Documents, documentation, wiki pages, spaces, knowledge base, articles
        
        Today's date is {self.context.current_date} ({self.context.metadata["current_date_human"]}).
        
        Only respond with "jira", "confluence", or "unsure".
        """
        
        # Initialize the classifier agent
        self.classifier = Agent(
            model="openai:gpt-4o",
            system_prompt=self.classifier_prompt
        )
        
        logfire.info("OrchestratorAgent initialized successfully")

    def classify_query(self, query: str) -> str:
        """
        Classify the query as related to Jira, Confluence, or unsure.
        
        Args:
            query: The user's query to classify
            
        Returns:
            str: "jira", "confluence", or "unsure"
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
            str: "jira" or "confluence"
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
        
        # Update the current date in context
        self.context.update_current_date()
        
        # Update date in both agents' contexts
        if "context" in self.jira_agent._deps.__dict__:
            self.jira_agent._deps.context["current_date"] = self.context.current_date
            self.jira_agent._deps.context["current_date_human"] = self.context.metadata["current_date_human"]
            self.jira_agent._deps.context["weekday"] = self.context.metadata["weekday"]
            
        if "context" in self.confluence_agent._deps.__dict__:
            self.confluence_agent._deps.context["current_date"] = self.context.current_date
            self.confluence_agent._deps.context["current_date_human"] = self.context.metadata["current_date_human"]
            self.confluence_agent._deps.context["weekday"] = self.context.metadata["weekday"]
        
        # Add user message to context
        self.context.add_user_message(message)
        
        # Check if message involves date confusion
        date_correction_keywords = ["fecha", "hoy", "día", "3 de noviembre", "2023"]
        if any(keyword in message.lower() for keyword in date_correction_keywords) and any(term in message.lower() for term in ["fecha", "3 de noviembre", "2023"]):
            now = datetime.now()
            month_names = {
                1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 
                5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
                9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
            }
            weekday_names = {
                0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
                4: "viernes", 5: "sábado", 6: "domingo"
            }
            
            date_human = f"{now.day} de {month_names[now.month]} de {now.year}"
            weekday = weekday_names[now.weekday()]
            
            if "3 de noviembre" in message.lower() or "noviembre" in message.lower() and "2023" in message.lower():
                response = (
                    f"Parece que hay cierta confusión con la fecha. Hoy no es el 3 de noviembre de 2023. "
                    f"La fecha actual es {weekday.capitalize()}, {date_human}. "
                    f"El sistema está configurado correctamente con la fecha actual. "
                    f"¿En qué más puedo ayudarte?"
                )
            else:
                response = (
                    f"La fecha actual del sistema es {weekday.capitalize()}, {date_human}. "
                    f"El sistema está actualizado con la fecha correcta. "
                    f"¿Necesitas alguna otra información?"
                )
                
            self.context.add_assistant_message(response, "orchestrator")
            return response
        
        # Determine which agent to use
        agent_type = self.determine_agent_with_context(message)
        self.context.active_agent = agent_type
        
        try:
            # Append date context to message for date-sensitive queries
            date_sensitive_keywords = ["hoy", "ayer", "fecha", "día", "semana", "mes"]
            date_enhanced_message = message
            
            if any(keyword in message.lower() for keyword in date_sensitive_keywords):
                # If date-related query, add date context but only for backend processing
                self.jira_agent._deps.context["explicit_date_context"] = True
                self.confluence_agent._deps.context["explicit_date_context"] = True
            
            # Delegate to the appropriate agent
            if agent_type == "jira":
                logfire.info("Delegating to Jira agent")
                response = self.jira_agent.process_message_sync(date_enhanced_message)
            else:  # confluence
                logfire.info("Delegating to Confluence agent")
                response = self.confluence_agent.process_message_sync(date_enhanced_message)
            
            # Add response to context
            self.context.add_assistant_message(response, agent_type)
            
            return response
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            logfire.error(error_msg)
            
            # Add error message to context
            self.context.add_assistant_message(error_msg, agent_type)
            
            return error_msg 
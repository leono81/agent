import os
from typing import Optional, Dict, Any, List
import logfire
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from app.agents.jira_agent import JiraAgent
from app.agents.confluence_agent import ConfluenceAgent

class SharedContext(BaseModel):
    """Shared context that maintains conversation state between agents."""
    conversation_history: List[Dict[str, str]] = []
    active_agent: Optional[str] = None
    last_query: Optional[str] = None
    metadata: Dict[str, Any] = {}

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

class OrchestratorAgent:
    """
    Orchestrator agent that delegates queries to specialized agents.
    
    This agent determines whether a query should be handled by the Jira agent
    or the Confluence agent, and maintains conversation context between them.
    """
    
    def __init__(self):
        """Initialize the orchestrator agent and its specialized sub-agents."""
        logfire.info("Initializing OrchestratorAgent")
        
        # Initialize the specialized agents
        self.jira_agent = JiraAgent()
        self.confluence_agent = ConfluenceAgent()
        
        # Initialize shared context
        self.context = SharedContext()
        
        # Define classifier prompt
        self.classifier_prompt = """
        Determine whether the following query is related to Jira or Confluence:
        
        - Jira: Issues, tickets, stories, tasks, sprints, boards, projects, assignments, worklog, time tracking, transitions
        - Confluence: Documents, documentation, wiki pages, spaces, knowledge base, articles
        
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
        
        # Add user message to context
        self.context.add_user_message(message)
        
        # Determine which agent to use
        agent_type = self.determine_agent_with_context(message)
        self.context.active_agent = agent_type
        
        try:
            # Delegate to the appropriate agent
            if agent_type == "jira":
                logfire.info("Delegating to Jira agent")
                response = self.jira_agent.process_message_sync(message)
            else:  # confluence
                logfire.info("Delegating to Confluence agent")
                response = self.confluence_agent.process_message_sync(message)
            
            # Add response to context
            self.context.add_assistant_message(response, agent_type)
            
            return response
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            logfire.error(error_msg)
            
            # Add error message to context
            self.context.add_assistant_message(error_msg, agent_type)
            
            return error_msg 
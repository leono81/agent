from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date


class Issue(BaseModel):
    """Modelo para representar una issue de Jira."""
    key: str = Field(description="Clave única de la issue (ej. PSIMDESASW-111)")
    summary: str = Field(description="Resumen o título de la issue")
    status: str = Field(description="Estado actual de la issue")
    assignee: Optional[str] = Field(description="Usuario asignado a la issue", default=None)
    

class Worklog(BaseModel):
    """Modelo para representar un registro de trabajo en una issue."""
    issue_key: str = Field(description="Clave de la issue a la que pertenece el worklog")
    time_spent: str = Field(description="Tiempo invertido en formato Jira (1h, 30m, etc.)")
    comment: Optional[str] = Field(description="Comentario del registro de trabajo", default=None)
    start_date: Optional[date] = Field(description="Fecha del registro", default_factory=date.today)


class Transition(BaseModel):
    """Modelo para representar una transición de estado en una issue."""
    id: str = Field(description="ID de la transición")
    name: str = Field(description="Nombre de la transición")
    to_status: str = Field(description="Estado al que lleva la transición")


class AgentResponse(BaseModel):
    """Modelo para la respuesta del agente."""
    message: str = Field(description="Mensaje para mostrar al usuario")
    success: bool = Field(description="Indica si la operación fue exitosa", default=True)
    data: Optional[dict] = Field(description="Datos adicionales de la respuesta", default=None) 
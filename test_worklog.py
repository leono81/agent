from app.agents.jira_agent import JiraAgent, RunContext, JiraAgentDependencies
import asyncio

async def test_worklog():
    agent = JiraAgent()
    # Simulamos un worklog con 15 minutos para hoy
    issue_key = 'PSIMDESASW-11507'  # Usar una issue existente de prueba
    time_str = '15m'
    date_str = 'hoy'
    
    print(f'Probando añadir worklog a {issue_key} con tiempo {time_str} y fecha {date_str}')
    
    # Crear contexto de ejecución manualmente
    ctx = RunContext(deps=agent._deps)
    
    # Ejecutar add_worklog
    result = await agent.add_worklog(
        ctx=ctx,
        issue_key=issue_key,
        time_str=time_str,
        date_str=date_str
    )
    
    print(f'Resultado: {result}')

# Ejecutar el test
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_worklog()) 
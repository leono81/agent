from app.agents.jira_agent import JiraAgent
from app.utils.jira_client import JiraClient
from app.config.config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
from pprint import pprint
import sys

def test_worklogs_yesterday():
    """
    Prueba la funcionalidad de obtener worklogs de ayer usando directamente el JiraClient.
    Verifica que solo se muestren los worklogs creados por el usuario actual.
    """
    print("Iniciando prueba de obtención de tus worklogs de ayer...")
    
    # Inicializar cliente Jira directamente
    client = JiraClient()
    
    try:
        # Obtener información del usuario actual
        user_info = client.jira.myself()
        display_name = user_info.get("displayName", JIRA_USERNAME)
        account_id = user_info.get("accountId", "")
        print(f"Usuario autenticado: {display_name} (accountId: {account_id})")
    except Exception as e:
        print(f"No se pudo obtener información del usuario: {e}")
        print(f"Usando nombre de usuario desde configuración: {JIRA_USERNAME}")
        display_name = JIRA_USERNAME
    
    # Probar el método get_my_worklogs_yesterday
    print("\n=== Test del JiraClient.get_my_worklogs_yesterday ===")
    print(f"Solo se mostrarán registros creados por: {display_name}")
    
    result = client.get_my_worklogs_yesterday()
    
    print(f"URL de Jira: {JIRA_URL}")
    print(f"Éxito: {result.get('success', False)}")
    print(f"Fecha: {result.get('date', 'N/A')}")
    print(f"Total: {result.get('total_formatted', '00:00:00')}")
    print(f"Cantidad de registros: {result.get('count', 0)}")
    
    if result.get('count', 0) == 0:
        print(f"\nNo se encontraron tus registros de trabajo para ayer.")
        return
    
    print("\nPrimeros 3 worklogs (detallados):")
    worklogs = result.get('worklogs', [])
    for idx, worklog in enumerate(worklogs[:3]):
        print(f"\n{idx+1}. {worklog.get('issue_key', 'N/A')} - {worklog.get('issue_summary', 'N/A')}")
        print(f"   Tiempo: {worklog.get('time_spent', 'N/A')}")
        print(f"   Fecha: {worklog.get('started', 'N/A')}")
        print(f"   Autor: {worklog.get('author', 'N/A')}")
        print(f"   Comentario: {worklog.get('comment', 'N/A')}")
        print(f"   URL: {worklog.get('issue_url', 'N/A')}")
    
    if len(worklogs) > 3:
        print(f"\n... y {len(worklogs) - 3} más.")
    
    # Verificar que todos los worklogs son del usuario actual
    unique_authors = set(worklog.get('author', '') for worklog in worklogs)
    print(f"\nAutores únicos en los resultados: {', '.join(unique_authors)}")
    if len(unique_authors) == 1 and display_name in unique_authors:
        print("\n✅ VERIFICACIÓN EXITOSA: Todos los worklogs pertenecen al usuario actual.")
    else:
        print("\n⚠️ ADVERTENCIA: Se encontraron worklogs de otros usuarios o no se pudo verificar la autoría.")
        
if __name__ == "__main__":
    test_worklogs_yesterday()
    print("\nPrueba completada.") 
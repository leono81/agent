from app.utils.jira_client import JiraClient
from datetime import datetime
import time

def test_worklog_simple():
    # Inicializar el cliente de Jira
    jira_client = JiraClient()
    
    # Issue de prueba
    issue_key = 'PSIMDESASW-11507'
    time_in_sec = 900  # 15 minutos
    
    # Crear el formato de fecha con el nuevo método
    dt_obj = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    dt_with_tz = dt_obj.astimezone()
    utc_offset = dt_with_tz.strftime('%z')
    started = dt_with_tz.strftime("%Y-%m-%dT%H:%M:%S.000") + utc_offset
    
    print(f"Probando añadir worklog a {issue_key}")
    print(f"Tiempo: {time_in_sec} segundos (15 minutos)")
    print(f"Fecha: {started}")
    
    # Agregar worklog
    result = jira_client.add_worklog(
        issue_key=issue_key,
        time_in_sec=time_in_sec,
        comment="Test de worklog con formato de fecha corregido",
        started=started
    )
    
    print(f"Resultado: {'Éxito' if result else 'Fallo'}")

if __name__ == "__main__":
    test_worklog_simple() 
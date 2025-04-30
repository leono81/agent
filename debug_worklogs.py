#!/usr/bin/env python3
from app.utils.jira_client import JiraClient
import logging
import sys

# Configurar logging para mostrar en consola
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    """
    Script de depuración para investigar el problema con los worklogs de Jira.
    Ejecuta la función get_my_worklogs_yesterday con logging detallado.
    """
    print("=== Iniciando depuración de worklogs de Jira ===")
    print("Obteniendo worklogs con logs detallados para investigar el problema")
    
    # Inicializar cliente Jira
    client = JiraClient()
    
    # Forzar actualización sin caché
    print("\nEjecutando consulta sin usar caché...")
    result = client.get_my_worklogs_yesterday(use_cache=False)
    
    print("\n=== Resumen de resultados ===")
    print(f"Éxito: {result.get('success', False)}")
    print(f"Fecha: {result.get('date', 'N/A')}")
    print(f"Total: {result.get('total_formatted', '00:00:00')}")
    print(f"Cantidad de registros: {result.get('count', 0)}")
    
    if result.get('count', 0) > 0:
        print("\nIssues con worklogs encontrados:")
        worklogs = result.get('worklogs', [])
        
        # Agrupar worklogs por issue
        issues = {}
        for worklog in worklogs:
            issue_key = worklog.get('issue_key', 'Sin clave')
            if issue_key not in issues:
                issues[issue_key] = []
            issues[issue_key].append(worklog)
        
        # Mostrar resumen por issue
        for issue_key, issue_worklogs in issues.items():
            print(f"- {issue_key}: {len(issue_worklogs)} registro(s)")
    else:
        print("\nNo se encontraron worklogs.")

if __name__ == "__main__":
    main() 
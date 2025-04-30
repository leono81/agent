#!/usr/bin/env python
"""
Script para obtener los worklogs de ayer desde Jira.
Utiliza la API de Jira para buscar y mostrar todos los registros de trabajo
realizados por el usuario actual durante el día anterior.

Uso: python get_yesterday_worklogs.py
"""

from app.utils.jira_client import JiraClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import sys

def format_time(seconds):
    """Formatea segundos en formato hh:mm:ss."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def main():
    console = Console()
    
    try:
        console.print(Panel.fit("🕒 [bold cyan]Obteniendo tus worklogs de ayer...[/]", 
                               border_style="cyan"))
        
        # Inicializar cliente Jira
        client = JiraClient()
        
        # Obtener worklogs de ayer
        result = client.get_my_worklogs_yesterday()
        
        yesterday = result.get('date', 'desconocida')
        total_time = result.get('total_formatted', '00:00:00')
        worklogs_count = result.get('count', 0)
        username = result.get('username', 'Usuario actual')
        
        # Mostrar encabezado con información general
        console.print(f"\n[bold cyan]👤 Usuario:[/] [yellow]{username}[/]")
        console.print(f"[bold]Fecha:[/] [yellow]{yesterday}[/]")
        console.print(f"[bold]Total de tiempo registrado:[/] [green]{total_time}[/]")
        console.print(f"[bold]Cantidad de registros:[/] {worklogs_count}")
        
        if not result.get('success', False):
            console.print(f"\n[bold red]Error:[/] {result.get('error', 'Error desconocido')}")
            return 1
            
        if worklogs_count == 0:
            console.print("\n[yellow]No registraste tiempo ayer.[/]")
            return 0
            
        # Crear una tabla para mostrar los worklogs agrupados por issue
        issues = {}
        worklogs = result.get('worklogs', [])
        
        # Agrupar worklogs por issue
        for worklog in worklogs:
            issue_key = worklog.get('issue_key', 'Sin clave')
            if issue_key not in issues:
                issues[issue_key] = {
                    'summary': worklog.get('issue_summary', 'Sin título'),
                    'url': worklog.get('issue_url', ''),
                    'entries': [],
                    'total_seconds': 0
                }
            
            issues[issue_key]['entries'].append(worklog)
            issues[issue_key]['total_seconds'] += worklog.get('time_spent_seconds', 0)
        
        # Mostrar tabla de issues con sus tiempos totales
        table_issues = Table(title=f"\n[bold]Resumen de TUS registros por Issue[/]", box=box.ROUNDED)
        table_issues.add_column("Issue", style="cyan")
        table_issues.add_column("Resumen", style="white")
        table_issues.add_column("Tiempo Total", style="green", justify="right")
        
        # Ordenar issues por tiempo total (descendente)
        sorted_issues = sorted(issues.items(), key=lambda x: x[1]['total_seconds'], reverse=True)
        
        for issue_key, issue_data in sorted_issues:
            total_time = format_time(issue_data['total_seconds'])
            table_issues.add_row(issue_key, issue_data['summary'], total_time)
            
        console.print(table_issues)
        
        # Mostrar detalles de cada worklog por issue
        for issue_key, issue_data in sorted_issues:
            table_entries = Table(title=f"\nTus Registros para [cyan]{issue_key}[/]: {issue_data['summary']}", 
                                 box=box.SIMPLE)
            table_entries.add_column("Tiempo", style="green", width=10)
            table_entries.add_column("Comentario", style="white")
            table_entries.add_column("Inicio", style="dim", width=20)
            
            for entry in issue_data['entries']:
                time_spent = entry.get('time_spent', '')
                comment = entry.get('comment', 'Sin comentario')
                started = entry.get('started', '').replace('T', ' ').split('.')[0]  # Formatear fecha/hora
                
                table_entries.add_row(time_spent, comment, started)
                
            console.print(table_entries)
        
        console.print(f"\n[bold green]✓[/] Reporte completado. [yellow]{username}[/] registró un total de [bold green]{total_time}[/] ayer.")
        return 0
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/] {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
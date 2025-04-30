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
from datetime import datetime

def format_time(seconds):
    """Formatea segundos en formato hh:mm:ss."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def main():
    console = Console()
    target_seconds = 8 * 3600  # 8 horas en segundos

    try:
        console.print(Panel.fit("🕒 [bold cyan]Obteniendo tus worklogs de ayer...[/]", 
                               border_style="cyan"))
        
        # Inicializar cliente Jira
        client = JiraClient()
        
        # Obtener worklogs de ayer
        result = client.get_my_worklogs_yesterday()
        
        if not result.get('success', False):
            console.print(f"\n[bold red]Error:[/] {result.get('error', 'Error desconocido')}")
            return 1

        yesterday = result.get('date', 'desconocida')
        total_seconds_logged = result.get('total_seconds', 0)
        total_time_formatted = format_time(total_seconds_logged) # Usar nuestra función para consistencia
        worklogs_count = result.get('count', 0)
        username = result.get('username', 'Usuario actual')

        # --- INICIO: Verificación de 8 horas ---
        console.print(f"\n[bold cyan]👤 Usuario:[/] [yellow]{username}[/]")
        console.print(f"[bold]Fecha:[/] [yellow]{yesterday}[/]")
        
        if total_seconds_logged >= target_seconds:
            message = f"✅ [bold green]¡Objetivo cumplido![/] Registraste {total_time_formatted} ({worklogs_count} registros)."
            console.print(Panel(message, title="Estado de Carga", border_style="green", expand=False))
        else:
            missing_seconds = target_seconds - total_seconds_logged
            missing_time_formatted = format_time(missing_seconds)
            message = (
                f"❌ [bold red]¡Atención![/] Registraste {total_time_formatted}.\n" 
                f"   [bold red]Te faltan {missing_time_formatted} para completar las 8 horas.[/] ({worklogs_count} registros)."
            )
            console.print(Panel(message, title="Estado de Carga", border_style="red", expand=False))
        # --- FIN: Verificación de 8 horas ---
            
        if worklogs_count == 0:
            # Mensaje ya implícito en el bloque anterior si faltan 8hs
            # console.print("\n[yellow]No registraste tiempo ayer.[/]")
            return 0
            
        # --- Resto del código para mostrar tablas (sin cambios) ---
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
        table_issues.add_column("Notas", style="yellow", justify="center")
        
        # Ordenar issues por tiempo total (descendente)
        sorted_issues = sorted(issues.items(), key=lambda x: x[1]['total_seconds'], reverse=True)
        
        for issue_key, issue_data in sorted_issues:
            total_time = format_time(issue_data['total_seconds'])
            
            # Ya no deberíamos tener placeholders con la lógica actual
            # has_placeholder = any(entry.get('is_placeholder', False) for entry in issue_data['entries'])
            # notes = "[italic yellow]Tiempo estimado*[/]" if has_placeholder else ""
            notes = "" # Limpiamos notas ya que no hay placeholders
            
            table_issues.add_row(issue_key, issue_data['summary'], total_time, notes)
            
        console.print(table_issues)
        
        # Ya no necesitamos la nota explicativa de placeholders
        # if any(any(entry.get('is_placeholder', False) for entry in issue_data['entries']) for _, issue_data in sorted_issues):
        #     console.print("[yellow]* El tiempo para algunas issues es estimado porque Jira indica que registraste tiempo pero no se pudo recuperar el registro exacto.[/]")
        
        # Mostrar detalles de cada worklog por issue
        for issue_key, issue_data in sorted_issues:
            table_entries = Table(title=f"\nTus Registros para [cyan]{issue_key}[/]: {issue_data['summary']}", 
                                 box=box.SIMPLE)
            table_entries.add_column("Tiempo", style="green", width=10)
            table_entries.add_column("Comentario", style="white")
            table_entries.add_column("Inicio", style="dim", width=20)
            # Ya no necesitamos la columna Tipo
            # table_entries.add_column("Tipo", style="yellow", width=12)
            
            for entry in issue_data['entries']:
                time_spent = entry.get('time_spent', '')
                comment = entry.get('comment', 'Sin comentario')
                started_str = entry.get('started', '')
                # Formatear fecha/hora un poco mejor
                try:
                     started_dt = datetime.strptime(started_str, '%Y-%m-%dT%H:%M:%S.%f%z')
                     started_formatted = started_dt.strftime('%Y-%m-%d %H:%M:%S') # Sin offset
                except:
                     started_formatted = started_str # Fallback a la cadena original

                # entry_type = "[italic yellow]Estimado*[/]" if entry.get('is_placeholder', False) else "Registrado"
                
                # table_entries.add_row(time_spent, comment, started_formatted, entry_type)
                table_entries.add_row(time_spent, comment, started_formatted)
                
            console.print(table_entries)
        
        # Mensaje final ya cubierto por el panel de estado
        # console.print(f"\n[bold green]✓[/] Reporte completado. [yellow]{username}[/] registró un total de [bold green]{total_time_formatted}[/] ayer.")
        return 0
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/] {str(e)}")
        # Loggear el traceback completo para depuración
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/]")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
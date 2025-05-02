import os
import sys
import signal
import subprocess
import locale
from dotenv import load_dotenv

# Configurar locale para fechas en español
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Spanish')
        except locale.Error:
            print("No se pudo configurar el locale para español, usando el predeterminado.")

# Cargar variables de entorno
load_dotenv()

# Variable global para el proceso de Streamlit
streamlit_process = None

def signal_handler(sig, frame):
    """
    Manejador de señales para interrupciones (Ctrl+C)
    """
    print("\nDeteniendo la aplicación de manera segura...")
    
    # Si hay un proceso de Streamlit en ejecución, terminarlo adecuadamente
    global streamlit_process
    if streamlit_process and streamlit_process.poll() is None:
        print("Terminando proceso de Streamlit...")
        try:
            # En sistemas Unix, enviar SIGTERM es más adecuado que kill directamente
            streamlit_process.terminate()
            # Dar un tiempo para que termine normalmente
            streamlit_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Forzando cierre del proceso...")
            streamlit_process.kill()
    
    print("Aplicación finalizada.")
    sys.exit(0)

def main():
    """
    Función principal para iniciar la aplicación.
    """
    # Configurar el manejador de señales para Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Verificar que las variables de entorno están configuradas
    required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "OPENAI_API_KEY", 
                     "CONFLUENCE_URL", "CONFLUENCE_USERNAME", "CONFLUENCE_API_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Faltan las siguientes variables de entorno:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPor favor, crea un archivo .env con las variables requeridas.")
        print("Puedes usar env.example como referencia.")
        return
    
    # Ejecutar la aplicación Streamlit usando el script wrapper y el venv
    print("Iniciando el Asistente Atlassian via wrapper...")
    
    try:
        # Usar Popen en lugar de run para tener más control sobre el proceso
        global streamlit_process
        # --- MODIFICADO ---: Ejecutar run_app.py con el python del venv
        python_executable = "venv/bin/python"
        if not os.path.exists(python_executable):
            print(f"Error: No se encuentra el ejecutable de Python en {python_executable}")
            print("Asegúrate de que el entorno virtual 'venv' existe y está configurado.")
            return
            
        streamlit_process = subprocess.Popen(
            [python_executable, "run_app.py"],
            # Redirigir la salida estándar y de error al proceso principal
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1  # Line buffered
        )
        
        # Leer y mostrar la salida del proceso en tiempo real
        for line in streamlit_process.stdout:
            print(line, end='')
            
        # Esperar a que el proceso termine (o sea interrumpido)
        streamlit_process.wait()
        
    except KeyboardInterrupt:
        # Esta excepción será capturada por el manejador de señales
        pass
    except Exception as e:
        print(f"Error al ejecutar la aplicación: {e}")
    finally:
        # Asegurarse de que el proceso de Streamlit termine correctamente
        if streamlit_process and streamlit_process.poll() is None:
            signal_handler(None, None)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Capturar Ctrl+C a nivel global
        signal_handler(None, None)
    except Exception as e:
        print(f"Error no capturado: {e}")
        sys.exit(1) 
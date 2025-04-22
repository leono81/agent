import os
import sys
import subprocess
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def main():
    """
    Función principal para iniciar la aplicación.
    """
    # Verificar que las variables de entorno están configuradas
    required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("Error: Faltan las siguientes variables de entorno:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPor favor, crea un archivo .env con las variables requeridas.")
        print("Puedes usar env.example como referencia.")
        return
    
    # Ejecutar la aplicación Streamlit
    print("Iniciando la aplicación Jira Agent...")
    subprocess.run(["streamlit", "run", "app/ui/app.py"])

if __name__ == "__main__":
    main() 
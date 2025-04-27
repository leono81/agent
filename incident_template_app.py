import streamlit as st
import os
import sys
from dotenv import load_dotenv
import json
import datetime

# Añadir el directorio raíz al path para poder importar desde app/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importar el agente de templates de incidentes
from app.agents.incident_template_agent import IncidentTemplateAgent

# Cargar variables de entorno
load_dotenv()

def set_page_config():
    """Configura las opciones de la página de Streamlit."""
    st.set_page_config(
        page_title="ATI - Agente de Templates de Incidentes",
        page_icon="🚨",
        layout="centered",
        initial_sidebar_state="collapsed"
    )
    
    # Aplicar algunos estilos personalizados
    st.markdown("""
    <style>
    .stButton button {
        width: 100%;
    }
    .stTextInput, .stTextArea, .stSelectbox {
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    """
    Función principal que ejecuta la aplicación de recopilación de datos de incidentes.
    
    Esta aplicación permite al usuario ingresar toda la información necesaria para registrar
    un incidente mayor a través de una interfaz conversacional. Una vez completado el proceso,
    los datos son devueltos como un diccionario estructurado que será utilizado por el agente
    de Confluence para crear la página correspondiente.
    """
    # Configurar la página
    set_page_config()
    
    # Crear y ejecutar el agente
    agent = IncidentTemplateAgent()
    
    # Ejecutar el agente para recopilar la información del incidente
    result = agent.run()
    
    # Si el resultado no es None, significa que el proceso ha sido completado
    if result:
        # En una implementación completa, aquí enviaríamos los datos al orquestador
        # para que los pase al agente de Confluence
        print("Datos del incidente recopilados con éxito.")
        print(f"Datos listos para enviar al agente de Confluence: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        # También podríamos guardar los datos en un archivo para recuperarlos
        # en caso de que la aplicación se cierre
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        incidents_dir = "incidents"
        if not os.path.exists(incidents_dir):
            os.makedirs(incidents_dir)
            
        filename = f"{incidents_dir}/incidente_{timestamp}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Datos guardados en: {filename}")
            st.success(f"Datos guardados en: {filename}")
        except Exception as e:
            print(f"Error al guardar los datos: {e}")
            
        # Para comunicarse con el orquestador, en una implementación real
        # podríamos usar un endpoint o un mecanismo de comunicación entre procesos

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error en la aplicación: {e}")
        st.error(f"Ha ocurrido un error: {e}") 
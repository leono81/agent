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
# Importar el agente de Confluence
from app.agents.confluence_agent import ConfluenceAgent
from app.utils.deps import get_deps
from pydantic_ai import RunContext

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

def enviar_a_confluence(incident_data):
    """
    Envía los datos del incidente al agente de Confluence para crear una página.
    
    Args:
        incident_data (dict): Diccionario con los datos del incidente
        
    Returns:
        dict: Resultado de la operación con el estado y la URL de la página creada
    """
    try:
        # Configurar el agente de Confluence
        deps = get_deps()
        confluence_agent = ConfluenceAgent(deps)
        confluence_context = RunContext(deps=deps)
        
        # Espacio predeterminado para las páginas de incidentes
        space_key = "PSIMDESASW"  # Este espacio puede ser configurable o parte de las variables de entorno
        
        # Crear la página de incidente
        st.info("Enviando datos a Confluence. Por favor, espera...")
        
        # Llamar al método de forma sincrónica
        import asyncio
        result = asyncio.run(confluence_agent.create_incident_page(
            confluence_context,
            incident_data,
            space_key
        ))
        
        return result
    except Exception as e:
        return {
            "success": False,
            "message": f"Error al crear la página en Confluence: {str(e)}"
        }

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
        # Mostrar los datos recopilados
        st.subheader("Datos del incidente recopilados correctamente")
        st.json(result)
        
        # Guardar los datos en un archivo para recuperarlos en caso de que la aplicación se cierre
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        incidents_dir = "incidents"
        if not os.path.exists(incidents_dir):
            os.makedirs(incidents_dir)
            
        filename = f"{incidents_dir}/incidente_{timestamp}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            st.success(f"Datos guardados en: {filename}")
        except Exception as e:
            st.error(f"Error al guardar los datos: {e}")
        
        # Preguntar al usuario si desea crear la página en Confluence
        if st.button("Crear página en Confluence"):
            # Enviar datos a Confluence
            confluence_result = enviar_a_confluence(result)
            
            if confluence_result.get("success", False):
                st.success(f"✅ Página creada exitosamente: {confluence_result.get('title')}")
                st.markdown(f"[Ver página en Confluence]({confluence_result.get('url')})")
            else:
                st.error(f"❌ Error al crear la página: {confluence_result.get('message')}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error en la aplicación: {e}")
        st.error(f"Ha ocurrido un error: {e}") 
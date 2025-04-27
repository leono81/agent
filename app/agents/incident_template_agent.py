import streamlit as st
import datetime
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel

# Configuration for the Incident Template
TEMPLATE_CONFIG = [
    {'key': 'tipo_incidente', 'question': '¿Cuál es el tipo de incidente?', 'type': 'text'},
    {'key': 'impacto', 'question': 'Excelente. ¿Cuál fue el Impacto?', 'type': 'choice', 
     'options': ['Alto', 'Medio', 'Bajo']},
    {'key': 'prioridad', 'question': 'Ok. ¿Prioridad?', 'type': 'choice', 
     'options': ['Alta', 'Media', 'Baja']},
    {'key': 'estado_actual', 'question': '¿Cuál es el estado Actual?', 'type': 'choice', 
     'options': ['Pendiente', 'En Progreso', 'Resuelto']},
    {'key': 'unidad_negocio', 'question': '¿Cuál fue la unidad de negocio afectada?', 'type': 'choice', 
     'options': ['CROSS UNIDADES', 'UNTM', 'UNAONTEC', 'PLACAS - SMT']},
    {'key': 'usuarios_soporte', 'question': '¿Quién participó del soporte?', 'type': 'list_text',
     'follow_up': '¿Alguien más participó en el soporte? (Deja vacío para terminar)'},
    {'key': 'descripcion_problema', 'question': 'Bien, guardado. Y ahora cuéntame la descripción del problema.', 
     'type': 'multiline_text'},
    {'key': 'acciones_realizadas', 'question': '¿Cuál fue la acción realizada?', 'type': 'list_structured', 
     'follow_up': '¿Se realizó alguna otra acción? (Deja vacío para terminar)',
     'help_text': 'Ingresa la información en el siguiente formato:\n\n**Fecha** - **Detalle de la acción** - **Área/Responsable**\n\nEjemplo: 26/04/2025 - Se reinició el servidor principal - Soporte IT'},
    {'key': 'fecha_resolucion', 'question': 'Ok. ¿Cuándo se resolvió? (Puedes escribir "hoy" o la fecha en formato DD/MM/YYYY)', 
     'type': 'date_text'},
    {'key': 'observaciones', 'question': 'Buenísimo. ¿Alguna observación adicional?', 'type': 'multiline_text'},
]

class IncidentTemplateAgent:
    """
    ATI - Agente Templates Incidentes
    
    Este agente guía al usuario a través de una conversación estructurada para recopilar
    información sobre un incidente mayor, siguiendo un template específico.
    """
    
    def __init__(self):
        """Inicializar el agente con la configuración del template."""
        print("Inicializando IncidentTemplateAgent (ATI)")
        self.template_config = TEMPLATE_CONFIG
        
    def parse_date(self, date_text: str) -> str:
        """Parsea una entrada de texto a formato de fecha (YYYY-MM-DD)."""
        try:
            if date_text.lower() == "hoy":
                return datetime.date.today().strftime("%Y-%m-%d")
            
            # Intentar parsear formatos comunes
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    date_obj = datetime.datetime.strptime(date_text, fmt)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
                    
            # Si no se pudo parsear, devolver el texto original
            return date_text
        except Exception as e:
            print(f"Error al parsear fecha: {e}")
            return date_text
            
    def initialize_session_state(self):
        """Inicializa el estado de la sesión en Streamlit si no existe."""
        if "current_step" not in st.session_state:
            st.session_state.current_step = 0
            
        if "collected_data" not in st.session_state:
            st.session_state.collected_data = {}
            # Agregar la fecha del incidente automáticamente
            st.session_state.collected_data["fecha_incidente"] = datetime.date.today().strftime("%Y-%m-%d")
            
        if "temp_list_items" not in st.session_state:
            st.session_state.temp_list_items = []
        
        # Debug
        print(f"Estado actual de la sesión - current_step: {st.session_state.current_step}, confirmation_step: {st.session_state.get('confirmation_step', False)}, process_completed: {st.session_state.get('process_completed', False)}")
            
    def reset_conversation(self):
        """Reinicia la conversación desde el principio."""
        st.session_state.current_step = 0
        st.session_state.collected_data = {
            "fecha_incidente": datetime.date.today().strftime("%Y-%m-%d")
        }
        st.session_state.temp_list_items = []
        st.session_state.confirmation_step = False
        st.session_state.process_completed = False
        # Limpiar otros valores de session_state para evitar persistencia de datos
        for key in list(st.session_state.keys()):
            if key.startswith("input_"):
                del st.session_state[key]
        
    def render_conversation_ui(self):
        """Renderiza la interfaz de conversación en Streamlit."""
        self.initialize_session_state()
        
        # Título y descripción
        st.title("Registro de Incidente Mayor")
        st.write("Soy el ATI (Agente Templates Incidentes). Te guiaré paso a paso para recopilar toda la información necesaria.")
        
        # Si el proceso ya está completado, mostrar el resultado final
        if st.session_state.get("process_completed", False):
            st.success("¡Proceso completado! La información del incidente ha sido registrada.")
            
            # Mostrar el diccionario recopilado en formato legible
            st.write("### Información del Incidente")
            for key, value in st.session_state.collected_data.items():
                # Formatear las claves para mejor lectura
                formatted_key = key.replace('_', ' ').title()
                
                # Formatear valores según su tipo
                if isinstance(value, list):
                    st.write(f"**{formatted_key}:**")
                    for idx, item in enumerate(value, 1):
                        st.write(f"{idx}. {item}")
                else:
                    st.write(f"**{formatted_key}:** {value}")
            
            # Mensaje de integración con Confluence
            st.info("Los datos del incidente han sido recopilados con éxito y serán enviados al agente de Confluence para crear la página correspondiente.")
                
            return st.session_state.collected_data
        
        # Si estamos en el paso de confirmación
        if st.session_state.get("confirmation_step", False):
            st.write("### Resumen de la información recopilada")
            
            # Mostrar toda la información recopilada
            for key, value in st.session_state.collected_data.items():
                # Formatear las claves para mejor lectura
                formatted_key = key.replace('_', ' ').title()
                
                # Formatear valores según su tipo
                if isinstance(value, list):
                    st.write(f"**{formatted_key}:**")
                    for idx, item in enumerate(value, 1):
                        st.write(f"{idx}. {item}")
                else:
                    st.write(f"**{formatted_key}:** {value}")
            
            st.write("### ¿Es correcta toda la información?")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Sí, confirmar", key="btn_confirm"):
                    # Marcar como completado
                    st.session_state.process_completed = True
                    st.rerun()
            
            with col2:
                if st.button("No, corregir", key="btn_correct"):
                    # Volver al primer paso
                    st.session_state.confirmation_step = False
                    st.session_state.current_step = 0
                    st.rerun()
                    
            return None
        
        # Verificar si hemos terminado de recopilar todos los datos (mover esta verificación aquí)
        if st.session_state.current_step >= len(self.template_config):
            print(f"Paso final completado. Cambiando a confirmación. current_step: {st.session_state.current_step}")
            st.session_state.confirmation_step = True
            st.rerun()
            return None
            
        # Asegurarse de que current_step esté dentro del rango válido
        if st.session_state.current_step < 0:
            st.session_state.current_step = 0
        if st.session_state.current_step >= len(self.template_config):
            st.session_state.current_step = len(self.template_config) - 1
        
        # Mostrar la conversación normal paso a paso
        current_config = self.template_config[st.session_state.current_step]
        current_key = current_config['key']
        current_type = current_config['type']
        
        # Mostrar la pregunta actual
        st.write(f"### {current_config['question']}")
        
        # Mostrar texto de ayuda si existe
        if 'help_text' in current_config:
            st.info(current_config['help_text'])
        
        # Debug - Mostrar el paso actual
        st.write(f"Paso {st.session_state.current_step + 1} de {len(self.template_config)}")
        
        # Renderizar el widget apropiado según el tipo de campo
        if current_type == 'text':
            user_input = st.text_input("Entrada de texto", key=f"input_{current_key}", label_visibility="collapsed")
            
            if st.button("Continuar", key=f"btn_{current_key}"):
                if user_input.strip():
                    st.session_state.collected_data[current_key] = user_input
                    st.session_state.current_step += 1
                    print(f"Avanzando a paso {st.session_state.current_step}")
                    st.rerun()
                else:
                    st.error("Por favor, ingresa la información solicitada.")
                    
        elif current_type == 'choice':
            options = current_config['options']
            selected_option = st.selectbox("Seleccione una opción", options, key=f"select_{current_key}", label_visibility="collapsed")
            
            if st.button("Continuar", key=f"btn_{current_key}"):
                st.session_state.collected_data[current_key] = selected_option
                st.session_state.current_step += 1
                print(f"Avanzando a paso {st.session_state.current_step}")
                st.rerun()
                
        elif current_type == 'multiline_text':
            user_input = st.text_area("Texto multilínea", key=f"textarea_{current_key}", label_visibility="collapsed")
            
            if st.button("Continuar", key=f"btn_{current_key}"):
                if user_input.strip():
                    st.session_state.collected_data[current_key] = user_input
                    st.session_state.current_step += 1
                    # Si estamos en el último paso (observaciones), establecer confirmation_step=True
                    if current_key == 'observaciones':
                        print("Última pregunta respondida, pasando a confirmación")
                        st.session_state.confirmation_step = True
                    print(f"Avanzando a paso {st.session_state.current_step}")
                    st.rerun()
                else:
                    st.error("Por favor, ingresa la información solicitada.")
                    
        elif current_type == 'list_text' or current_type == 'list_structured':
            # Si es una lista, gestionamos la entrada de múltiples ítems
            
            # Mostrar los ítems ya agregados
            if st.session_state.temp_list_items:
                st.write("Elementos agregados:")
                for idx, item in enumerate(st.session_state.temp_list_items, 1):
                    st.write(f"{idx}. {item}")
            
            # Para eliminar la entrada de texto anterior, usamos un key único que cambia con cada adición
            # y también inicializamos el campo en vacío
            list_input_key = f"input_{current_key}_{len(st.session_state.temp_list_items)}"
            if list_input_key not in st.session_state:
                st.session_state[list_input_key] = ""
            
            # Si es la primera vez o si estamos pidiendo otro ítem
            if 'follow_up' in current_config and st.session_state.temp_list_items:
                # Usamos la pregunta de seguimiento
                st.write(current_config['follow_up'])
                if current_type == 'list_structured':
                    user_input = st.text_input(
                        "Formato: Fecha - Detalle - Responsable", 
                        key=list_input_key, 
                        label_visibility="collapsed"
                    )
                else:
                    user_input = st.text_input(
                        "Entrada adicional", 
                        key=list_input_key, 
                        label_visibility="collapsed"
                    )
            else:
                # Primera entrada para esta lista
                if current_type == 'list_structured':
                    user_input = st.text_input(
                        "Formato: Fecha - Detalle - Responsable", 
                        key=list_input_key, 
                        label_visibility="collapsed"
                    )
                else:
                    user_input = st.text_input(
                        "Entrada de texto", 
                        key=list_input_key, 
                        label_visibility="collapsed"
                    )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Agregar", key=f"btn_add_{current_key}_{len(st.session_state.temp_list_items)}"):
                    if user_input.strip():
                        st.session_state.temp_list_items.append(user_input)
                        # La limpieza ya no es necesaria, ya que estamos creando una nueva clave para cada entrada
                        print(f"Elemento agregado: {user_input}. Total: {len(st.session_state.temp_list_items)}")
                        st.rerun()
            
            with col2:
                if st.button("Continuar", key=f"btn_cont_{current_key}"):
                    if st.session_state.temp_list_items:
                        # Guardar la lista completa y limpiar la temporal
                        st.session_state.collected_data[current_key] = st.session_state.temp_list_items.copy()
                        st.session_state.temp_list_items = []
                        st.session_state.current_step += 1
                        print(f"Avanzando a paso {st.session_state.current_step}")
                        st.rerun()
                    else:
                        st.error("Debes agregar al menos un elemento.")
        
        elif current_type == 'date_text':
            user_input = st.text_input("Fecha (DD/MM/YYYY o 'hoy')", key=f"input_{current_key}", label_visibility="collapsed")
            
            if st.button("Continuar", key=f"btn_{current_key}"):
                if user_input.strip():
                    # Parsear la fecha ingresada
                    parsed_date = self.parse_date(user_input)
                    st.session_state.collected_data[current_key] = parsed_date
                    st.session_state.current_step += 1
                    print(f"Avanzando a paso {st.session_state.current_step}")
                    st.rerun()
                else:
                    st.error("Por favor, ingresa la fecha solicitada.")
            
        return None
    
    def run(self) -> Optional[Dict[str, Any]]:
        """
        Ejecuta el agente y devuelve el diccionario con la información recopilada.
        
        Returns:
            Dict[str, Any]: Diccionario con la información del incidente, o None si 
            aún no se ha completado el proceso.
        """
        try:
            result = self.render_conversation_ui()
            return result
        except Exception as e:
            print(f"Error en IncidentTemplateAgent.run(): {e}")
            st.error(f"Ha ocurrido un error: {e}")
            import traceback
            print(traceback.format_exc())
            return None

def create_incident_template_app():
    """
    Función para crear y ejecutar la aplicación Streamlit del ATI.
    
    Esta función recopila toda la información necesaria para crear un incidente mayor
    a través de una interfaz conversacional. Una vez completado el proceso, el resultado
    es un diccionario estructurado que será utilizado por el agente de Confluence para
    crear la página correspondiente.
    
    Returns:
        Dict[str, Any]: Diccionario con la información del incidente para el agente de Confluence.
        None si el proceso no ha sido completado.
    """
    agent = IncidentTemplateAgent()
    
    # Ejecutar el agente y obtener el resultado
    result = agent.run()
    
    # Si el proceso está completo, devolver el resultado
    if result:
        print("Plantilla de incidente completada. Datos listos para enviar al agente de Confluence.")
        return result
    
    return None

# Para ejecutar directamente como aplicación Streamlit
if __name__ == "__main__":
    create_incident_template_app() 
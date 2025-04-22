#!/usr/bin/env python3
"""
Script para probar la configuración y funcionamiento de Logfire.
Ejecutar con: python -m app.test_logfire
"""

import os
import logging
import logfire
from app.config.config import LOGFIRE_TOKEN, OPENAI_API_KEY
from pydantic_ai import Agent

# Configurar Logfire
try:
    # Asegurar que el token está configurado
    os.environ["LOGFIRE_TOKEN"] = LOGFIRE_TOKEN
    
    # Configurar Logfire con envío a la plataforma
    logfire.configure(send_to_logfire=True)
    print("✅ Logfire configurado correctamente")
    
    # Instrumentar también las peticiones HTTP
    logfire.instrument_httpx(capture_all=True)
    print("✅ Instrumentación HTTPX activada")
    
    # Registrar algunos logs de prueba usando logging estándar
    logger = logging.getLogger("test_logfire")
    logger.setLevel(logging.INFO)
    logger.info("Este es un mensaje de prueba INFO")
    logger.warning("Este es un mensaje de prueba WARNING")
    logger.error("Este es un mensaje de prueba ERROR (no real)")
    
    print("\n✅ Configuración básica completada con éxito")
    print("¿Deseas continuar con la prueba de consulta al agente? (s/n)")
    continuar = input()
    
    if continuar.lower() != 's':
        print("Prueba de configuración básica finalizada")
        exit(0)
    
    # Crear un agente básico para probar la instrumentación
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
    agent = Agent(
        "openai:gpt-4o",
        instrument=True
    )
    
    # Ejecutar una consulta simple para probar la instrumentación
    print("\n⏳ Probando consulta al agente...")
    result = agent.run_sync("¿Cuál es la ciudad más poblada de Argentina?")
    print(f"✅ Respuesta: {result.output}")
    
    print("\n✅ Prueba completa finalizada con éxito")
    print("Puedes verificar los datos en la plataforma Logfire")
    
except Exception as e:
    print(f"❌ Error al configurar o usar Logfire: {e}")
    import traceback
    traceback.print_exc() 
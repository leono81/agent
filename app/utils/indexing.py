import os
import time
import logfire
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings # Cambio 1: Corregir import
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma # Cambio 2: Corregir import
from langchain_huggingface import HuggingFaceEmbeddings # Asegurar que se usa langchain_huggingface
from langchain_chroma import Chroma as ChromaLangchain # Asegurar que se usa langchain_chroma

# Configuración (puede ser centralizada más adelante si es necesario)
KNOWLEDGE_BASE_DIR = "knowledge_base"
VECTOR_STORE_DIR = "vector_store_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Configurar Logfire (opcional, pero útil para seguimiento)
try:
    logfire.configure(send_to_logfire=False) # Evitar envíos automáticos si no está configurado
    logfire.info("Logfire configurado para utils.indexing")
except Exception as e:
    print(f"Advertencia: No se pudo configurar Logfire en utils.indexing: {e}")

def _get_last_modified_time(path: str) -> float:
    """Obtiene la fecha de última modificación de un archivo o directorio, 0 si no existe."""
    if not os.path.exists(path):
        return 0
    return os.path.getmtime(path)

def _should_reindex(knowledge_dir: str, vector_store_dir: str) -> bool:
    """Comprueba si es necesario reindexar comparando fechas de modificación."""
    last_index_time = _get_last_modified_time(vector_store_dir)
    if last_index_time == 0:
        logfire.info("El directorio del vector store no existe. Se requiere indexación.")
        return True # Vector store no existe, hay que crearlo

    last_knowledge_change = 0
    for root, _, files in os.walk(knowledge_dir):
        for file in files:
            if file.endswith(('.md', '.txt')): # Considerar solo archivos de texto
                file_path = os.path.join(root, file)
                last_knowledge_change = max(last_knowledge_change, _get_last_modified_time(file_path))

    if last_knowledge_change == 0:
        logfire.warning(f"No se encontraron archivos .md o .txt en {knowledge_dir}. No se indexará.")
        return False # No hay nada que indexar

    should_index = last_knowledge_change > last_index_time
    if should_index:
        logfire.info("Se detectaron cambios en la base de conocimientos. Se requiere reindexación.")
    else:
        logfire.info("No se detectaron cambios en la base de conocimientos desde la última indexación.")
    return should_index

def update_vector_store(force_reindex: bool = False):
    """
    Carga documentos de knowledge_base, los divide, crea embeddings
    y los guarda en ChromaDB SI es necesario (o si force_reindex es True).
    """
    if not force_reindex and not _should_reindex(KNOWLEDGE_BASE_DIR, VECTOR_STORE_DIR):
        print("Base de conocimientos sin cambios. No se requiere indexación.")
        logfire.info("Indexación omitida: sin cambios detectados.")
        return

    logfire.info(f"Iniciando indexación desde: {KNOWLEDGE_BASE_DIR} hacia {VECTOR_STORE_DIR}")
    print(f"Actualizando índice vectorial desde {KNOWLEDGE_BASE_DIR}...")

    # Crear directorio de vector store si no existe
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)

    # 1. Cargar Documentos
    try:
        loader = DirectoryLoader(
            KNOWLEDGE_BASE_DIR,
            glob="**/*[.md|.txt]",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=True,
            use_multithreading=True # Puede dar problemas en algunos entornos, desactivar si es necesario
        )
        documents = loader.load()
        if not documents:
            logfire.warning(f"No se encontraron documentos en {KNOWLEDGE_BASE_DIR}. No se generará índice.")
            print(f"Advertencia: No se encontraron documentos en {KNOWLEDGE_BASE_DIR} para indexar.")
            # Asegurarse de que el directorio exista para la comprobación de mtime la próxima vez
            # (si no existe, _should_reindex siempre devolverá True)
            if not os.path.exists(VECTOR_STORE_DIR):
                 os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
            return
        logfire.info(f"Cargados {len(documents)} documentos.")
    except Exception as e:
        logfire.error(f"Error al cargar documentos: {e}", exc_info=True)
        print(f"Error fatal al cargar documentos: {e}")
        return

    # 2. Dividir Documentos en Chunks
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        docs_split = text_splitter.split_documents(documents)
        logfire.info(f"Documentos divididos en {len(docs_split)} chunks.")
    except Exception as e:
        logfire.error(f"Error al dividir documentos: {e}", exc_info=True)
        print(f"Error fatal al dividir documentos: {e}")
        return

    # 3. Crear Embeddings y Almacenar en ChromaDB
    try:
        logfire.info(f"Inicializando modelo de embeddings: {EMBEDDING_MODEL}")
        # Usar el wrapper de HuggingFace compatible con LangChain más reciente
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

        logfire.info(f"Creando/Actualizando vector store en: {VECTOR_STORE_DIR}")
        # Usar el wrapper de Chroma compatible con LangChain más reciente
        # ChromaLangchain se encarga de borrar el directorio si existe para recrearlo
        vector_store = ChromaLangchain.from_documents(
            documents=docs_split,
            embedding=embeddings,
            persist_directory=VECTOR_STORE_DIR
        )
        # La persistencia ahora suele manejarse internamente en el constructor,
        # pero una llamada explícita puede ser necesaria en algunas versiones o para asegurar.
        # vector_store.persist() # Probar sin esto primero, ChromaLangchain debería manejarlo.

        # Forzar la escritura inmediata (puede no ser necesario con persist_directory)
        # Esto asegura que el mtime del directorio se actualice
        vector_store = None # Liberar el objeto para asegurar que se cierren los archivos
        time.sleep(1) # Pequeña pausa para asegurar que el sistema de archivos actualiza mtime

        logfire.info("Vector store creado/actualizado exitosamente.")
        print("Indexación completada exitosamente.")

    except Exception as e:
        logfire.error(f"Error durante la creación de embeddings o almacenamiento en ChromaDB: {e}", exc_info=True)
        print(f"Error fatal durante la indexación: {e}")

if __name__ == '__main__':
    # Permitir forzar la reindexación si se ejecuta el script directamente
    import argparse
    parser = argparse.ArgumentParser(description='Actualiza el índice vectorial de ChromaDB.')
    parser.add_argument('--force', action='store_true', help='Forzar la reindexación aunque no se detecten cambios.')
    args = parser.parse_args()

    print("Ejecutando indexación desde script directo...")
    update_vector_store(force_reindex=args.force) 
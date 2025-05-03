import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import logfire
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
import argparse
from app.utils.indexing import update_vector_store

# Configuración
KNOWLEDGE_BASE_DIR = "knowledge_base"
VECTOR_STORE_DIR = "vector_store_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2" # Modelo ligero y popular
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Configurar Logfire (opcional, pero útil para seguimiento)
try:
    logfire.configure()
    logfire.info("Logfire configurado para indexación.")
except Exception as e:
    print(f"Advertencia: No se pudo configurar Logfire: {e}")

def main():
    """Carga documentos, los divide, crea embeddings y los guarda en ChromaDB."""
    logfire.info(f"Iniciando indexación desde: {KNOWLEDGE_BASE_DIR}")

    # 1. Cargar Documentos
    try:
        # Usar DirectoryLoader para cargar todos los .md y .txt
        # Configurar TextLoader para usar UTF-8 explícitamente
        loader = DirectoryLoader(
            KNOWLEDGE_BASE_DIR,
            glob="**/*[.md|.txt]",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=True,
            use_multithreading=True
        )
        documents = loader.load()
        if not documents:
            logfire.warning("No se encontraron documentos en el directorio knowledge_base. Abortando.")
            print("Error: No se encontraron documentos en ./knowledge_base/")
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
        # Usar SentenceTransformerEmbeddings para embeddings locales
        embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)

        logfire.info(f"Creando/Actualizando vector store en: {VECTOR_STORE_DIR}")
        # Crear ChromaDB persistente. Si ya existe, añadirá nuevos documentos
        # o actualizará los existentes si su contenido ha cambiado.
        vector_store = Chroma.from_documents(
            documents=docs_split,
            embedding=embeddings,
            persist_directory=VECTOR_STORE_DIR
        )
        # Asegurarse de que los datos se escriban en disco
        vector_store.persist()
        logfire.info("Vector store creado/actualizado y persistido exitosamente.")
        print("Indexación completada exitosamente.")

    except Exception as e:
        logfire.error(f"Error durante la creación de embeddings o almacenamiento en ChromaDB: {e}", exc_info=True)
        print(f"Error fatal durante la indexación: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Actualiza el índice vectorial de ChromaDB desde el script.')
    parser.add_argument('--force', action='store_true', help='Forzar la reindexación aunque no se detecten cambios.')
    args = parser.parse_args()

    print("Iniciando indexación manual...")
    update_vector_store(force_reindex=args.force)
    print("Proceso de indexación manual finalizado.") 
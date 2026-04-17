# autoso/pipeline/holy_grail.py
import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
import autoso.config as config

_COLLECTION_NAME = "bucket_holy_grail"


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=config.CHROMADB_PATH)


def ingest_holy_grail(file_path: str) -> VectorStoreIndex:
    """Ingest a document into the persistent Holy Grail index. Replaces existing."""
    client = _get_client()
    try:
        client.delete_collection(_COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(_COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    docs = SimpleDirectoryReader(input_files=[file_path]).load_data()
    return VectorStoreIndex.from_documents(
        docs, storage_context=storage_context, show_progress=False
    )


def load_holy_grail() -> VectorStoreIndex:
    """Load the existing Holy Grail index. Raises RuntimeError if not ingested."""
    client = _get_client()
    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(
            "Holy Grail index not found. "
            "Run: python scripts/ingest_holy_grail.py <path_to_document>"
        ) from exc
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(
        vector_store, storage_context=storage_context
    )

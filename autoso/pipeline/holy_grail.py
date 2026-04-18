# autoso/pipeline/holy_grail.py
import logging
from pathlib import Path
import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
import autoso.config as config

Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "bucket_holy_grail"


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=config.CHROMADB_PATH)


def ingest_holy_grail(path: str) -> VectorStoreIndex:
    """Ingest a file or directory into the persistent Holy Grail index. Replaces existing."""
    client = _get_client()
    try:
        client.delete_collection(_COLLECTION_NAME)
    except Exception:
        logger.debug("No existing collection to delete; creating fresh.")

    collection = client.create_collection(_COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    p = Path(path)
    if p.is_dir():
        docs = SimpleDirectoryReader(input_dir=str(p), recursive=True).load_data()
    else:
        docs = SimpleDirectoryReader(input_files=[str(p)]).load_data()
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

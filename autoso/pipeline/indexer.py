# autoso/pipeline/indexer.py
import uuid
from typing import List

import chromadb
from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

from autoso.scraping.models import Comment


def index_comments(
    comments: List[Comment], collection_name: str | None = None
) -> VectorStoreIndex:
    """Index comments into an ephemeral (in-memory) ChromaDB collection."""
    if collection_name is None:
        collection_name = f"run_{uuid.uuid4().hex[:12]}"

    client = chromadb.EphemeralClient()
    collection = client.create_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = [
        Document(
            text=comment.text,
            metadata={
                "platform": comment.platform,
                "id": comment.id,
                "position": comment.position,
            },
            doc_id=comment.id,
        )
        for comment in comments
    ]

    return VectorStoreIndex.from_documents(
        documents, storage_context=storage_context, show_progress=False
    )

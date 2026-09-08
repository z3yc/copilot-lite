"""RAG（检索增强生成）层。"""

from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.pipeline import IngestError, ingest_document
from app.rag.query_rewriter import QueryRewriter, get_rewriter
from app.rag.reranker import Reranker, get_reranker
from app.rag.retriever import RetrievedChunk, hybrid_search, multi_query_search
from app.rag.vector_store import SearchHit, VectorStore, get_vector_store

__all__ = [
    "EmbeddingService",
    "IngestError",
    "QueryRewriter",
    "Reranker",
    "RetrievedChunk",
    "SearchHit",
    "VectorStore",
    "chunk_document",
    "get_embedding_service",
    "get_reranker",
    "get_rewriter",
    "get_vector_store",
    "hybrid_search",
    "ingest_document",
    "multi_query_search",
]

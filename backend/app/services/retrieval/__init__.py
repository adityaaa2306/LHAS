"""Retrieval Services Module

Provides RAG (Retrieval Augmented Generation) capabilities.
Handles FAISS vector retrieval and PostgreSQL metadata enrichment.
"""

from app.services.retrieval.retrieval_module import (
    RetrievalModule,
    get_retrieval_module,
)

__all__ = ["RetrievalModule", "get_retrieval_module"]

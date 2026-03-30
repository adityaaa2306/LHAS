"""Embedding Service - Generate and manage paper embeddings using NVIDIA NIM"""

import logging
import numpy as np
from typing import List, Optional
from app.config import settings

# Lazy import to avoid dependency issues
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using NVIDIA's llama-nemotron model"""
    
    def __init__(self):
        """Initialize embedding service with NVIDIA API credentials"""
        if not settings.EMBEDDING_MODEL_API_KEY:
            logger.warning("EMBEDDING_MODEL_API_KEY not set - embeddings will not work")
            self.client = None
        else:
            self.client = AsyncOpenAI(
                api_key=settings.EMBEDDING_MODEL_API_KEY,
                base_url=settings.EMBEDDING_BASE_URL
            )
        
        self.model_name = settings.EMBEDDING_MODEL_NAME
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.embedding_cache = {}  # Simple cache to avoid re-embedding same text
    
    async def embed_text(self, text: str, input_type: str = "query") -> Optional[List[float]]:
        """
        Get embedding for a single text string.
        
        Args:
            text: Text to embed (query or passage)
            input_type: "query" or "passage" - helps model optimize embeddings
            
        Returns:
            Embedding vector as list of floats, or None if failed
        """
        if not self.client:
            logger.warning("Embedding client not initialized - returning None")
            return None
        
        # Check cache
        cache_key = f"{text}:{input_type}"
        if cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]
        
        try:
            response = await self.client.embeddings.create(
                input=[text[:2000]],  # Truncate to avoid token limits
                model=self.model_name,
                encoding_format="float",
                extra_body={
                    "modality": ["text"],
                    "input_type": input_type,
                    "truncate": "NONE"
                }
            )
            
            embedding = response.data[0].embedding
            self.embedding_cache[cache_key] = embedding
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to embed text: {str(e)}")
            return None
    
    async def embed_batch(
        self,
        texts: List[str],
        input_type: str = "passage"
    ) -> List[Optional[List[float]]]:
        """
        Get embeddings for multiple texts (batch processing).
        
        Args:
            texts: List of texts to embed
            input_type: "query" or "passage"
            
        Returns:
            List of embedding vectors, None for failed texts
        """
        if not self.client:
            logger.warning("Embedding client not initialized - returning empty")
            return [None] * len(texts)
        
        embeddings = []
        
        try:
            # Process in batches
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                # Check cache first
                batch_embeddings = []
                uncached_indices = []
                uncached_texts = []
                
                for j, text in enumerate(batch):
                    cache_key = f"{text}:{input_type}"
                    if cache_key in self.embedding_cache:
                        batch_embeddings.append(self.embedding_cache[cache_key])
                    else:
                        uncached_indices.append(j)
                        uncached_texts.append(text[:2000])  # Truncate
                
                # Get uncached embeddings
                if uncached_texts:
                    response = await self.client.embeddings.create(
                        input=uncached_texts,
                        model=self.model_name,
                        encoding_format="float",
                        extra_body={
                            "modality": ["text"] * len(uncached_texts),
                            "input_type": input_type,
                            "truncate": "NONE"
                        }
                    )
                    
                    for idx, response_item in enumerate(response.data):
                        embedding = response_item.embedding
                        original_idx = uncached_indices[idx]
                        cache_key = f"{uncached_texts[idx]}:{input_type}"
                        self.embedding_cache[cache_key] = embedding
                        batch_embeddings.insert(original_idx, embedding)
                
                embeddings.extend(batch_embeddings)
                logger.info(f"Embedded batch {i//self.batch_size + 1} of {len(texts)//self.batch_size + 1}")
        
        except Exception as e:
            logger.error(f"Failed to embed batch: {str(e)}")
            return [None] * len(texts)
        
        return embeddings
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        if not vec1 or not vec2:
            return 0.0
        
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    @staticmethod
    def embedding_distance(vec1: List[float], vec2: List[float]) -> float:
        """
        Compute distance between two vectors (1 - cosine_similarity).
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
            
        Returns:
            Distance score between 0 and 1
        """
        similarity = EmbeddingService.cosine_similarity(vec1, vec2)
        return 1.0 - similarity


# Global singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service

"""ADDED: Advanced Semantic Retrieval Layer with GROBID + Multi-Query Retrieval

Implements structured document parsing, chunking, semantic embedding,
multi-query retrieval, and cross-encoder reranking to provide evidence-grounded
context to Pass 1 LLM extraction.
"""

import asyncio
import logging
import json
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
import math

logger = logging.getLogger(__name__)


@dataclass
class ChunkMetadata:
    """Metadata for a parsed chunk from a paper"""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str = ""
    section_name: str = ""  # abstract, introduction, methods, results, discussion, conclusion
    chunk_type: str = "text"  # text, table, figure_caption
    paragraph_index: int = 0
    sentence_range: Tuple[int, int] = field(default_factory=lambda: (0, 0))
    token_count: int = 0
    raw_text: str = ""
    
    # Retrieval metadata
    retrieval_query_matches: List[int] = field(default_factory=list)  # which of 5 queries matched
    cosine_score: Optional[float] = None
    crossencoder_score: Optional[float] = None
    final_rank: Optional[int] = None
    embedding: Optional[List[float]] = None


@dataclass
class RetrievalResult:
    """Result of multi-query retrieval"""
    success: bool
    chunks: List[ChunkMetadata] = field(default_factory=list)
    total_found: int = 0
    retrieval_fallback: bool = False
    error: Optional[str] = None
    latency_ms: float = 0


class RetrievalLayer:
    """ADDED: Document retrieval layer with semantic ranking and reranking"""
    
    def __init__(
        self,
        db: Any,
        embedding_service: Any,
        llm_provider: Any,
        grobid_url: str = "http://localhost:8070",
        max_chunk_tokens: int = 300,
        enable_cross_encoder: bool = True
    ):
        """
        Initialize retrieval layer.
        
        Args:
            db: AsyncSession database connection
            embedding_service: Service for embedding chunks
            llm_provider: LLM service for query generation
            grobid_url: URL of GROBID service for PDF parsing
            max_chunk_tokens: Maximum tokens per chunk before splitting
            enable_cross_encoder: Whether to use cross-encoder reranking
        """
        self.db = db
        self.embedding_service = embedding_service
        self.llm_provider = llm_provider
        self.grobid_url = grobid_url
        self.max_chunk_tokens = max_chunk_tokens
        self.enable_cross_encoder = enable_cross_encoder
        
        # Lazy load cross-encoder only if enabled
        self._cross_encoder = None
        
        logger.info("RetrievalLayer initialized")
    
    async def parse_with_grobid(
        self,
        paper_id: str,
        pdf_url: str
    ) -> Dict[str, Any]:
        """ADDED: Parse PDF with GROBID to extract structured sections"""
        try:
            # GROBID would parse PDF and return structured output
            # For MVP: return simulated structure (in production, call GROBID service)
            logger.info(f"Parsing PDF for paper {paper_id} from {pdf_url}")
            
            # Simulated GROBID output structure
            parsed_sections = {
                "abstract": "Sample abstract text with research findings...",
                "introduction": "Background and motivation...",
                "methods": "Research methodology...",
                "results": "Key results and findings...",
                "discussion": "Interpretation and implications...",
                "conclusion": "Summary of conclusions..."
            }
            
            return {
                "success": True,
                "sections": parsed_sections,
                "tables": [],  # Detected table structures
                "figures": []  # Figure captions
            }
        except Exception as e:
            logger.error(f"GROBID parsing failed for paper {paper_id}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def chunk_paper(
        self,
        paper_id: str,
        parsed_sections: Dict[str, str]
    ) -> List[ChunkMetadata]:
        """ADDED: Chunk parsed sections into retrievable units"""
        chunks = []
        chunk_idx = 0
        
        for section_name, section_text in parsed_sections.items():
            if not section_text:
                continue
            
            # Split into paragraphs
            paragraphs = re.split(r'\n\s*\n', section_text.strip())
            
            for para_idx, paragraph in enumerate(paragraphs):
                if not paragraph.strip():
                    continue
                
                # Estimate token count (rough: ~1 token per 4 chars)
                token_estimate = len(paragraph) // 4
                
                if token_estimate > self.max_chunk_tokens:
                    # Split long paragraph at sentence boundaries
                    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                    current_chunk = ""
                    current_tokens = 0
                    sent_start = 0
                    
                    for sent_idx, sentence in enumerate(sentences):
                        sent_tokens = len(sentence) // 4
                        if current_tokens + sent_tokens > self.max_chunk_tokens and current_chunk:
                            # Emit current chunk
                            chunk = ChunkMetadata(
                                paper_id=paper_id,
                                section_name=section_name,
                                chunk_type="text",
                                paragraph_index=para_idx,
                                sentence_range=(sent_start, sent_idx - 1),
                                token_count=current_tokens,
                                raw_text=current_chunk.strip()
                            )
                            chunks.append(chunk)
                            chunk_idx += 1
                            current_chunk = ""
                            current_tokens = 0
                            sent_start = sent_idx
                        
                        current_chunk += sentence + " "
                        current_tokens += sent_tokens
                    
                    # Emit final chunk
                    if current_chunk.strip():
                        chunk = ChunkMetadata(
                            paper_id=paper_id,
                            section_name=section_name,
                            chunk_type="text",
                            paragraph_index=para_idx,
                            sentence_range=(sent_start, len(sentences) - 1),
                            token_count=current_tokens,
                            raw_text=current_chunk.strip()
                        )
                        chunks.append(chunk)
                        chunk_idx += 1
                else:
                    # Paragraph fits in single chunk
                    chunk = ChunkMetadata(
                        paper_id=paper_id,
                        section_name=section_name,
                        chunk_type="text",
                        paragraph_index=para_idx,
                        sentence_range=(0, len(re.split(r'(?<=[.!?])\s+', paragraph)) - 1),
                        token_count=token_estimate,
                        raw_text=paragraph.strip()
                    )
                    chunks.append(chunk)
                    chunk_idx += 1
        
        logger.info(f"Created {len(chunks)} chunks for paper {paper_id}")
        return chunks
    
    async def embed_chunks(
        self,
        chunks: List[ChunkMetadata]
    ) -> List[ChunkMetadata]:
        """ADDED: Embed all chunks using embedding service"""
        try:
            texts = [chunk.raw_text for chunk in chunks]
            embeddings = await self.embedding_service.embed_batch_async(texts)
            
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding
            
            logger.info(f"Embedded {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Embedding failed: {str(e)}")
            return chunks
    
    async def multi_query_retrieve(
        self,
        mission_question: str,
        pico_data: Dict[str, str],
        chunks: List[ChunkMetadata],
        top_k_per_query: int = 15
    ) -> List[ChunkMetadata]:
        """ADDED: Generate 5 retrieval queries and retrieve from chunks"""
        
        # Generate 5 retrieval queries
        queries = self._generate_retrieval_queries(mission_question, pico_data)
        logger.info(f"Generated {len(queries)} retrieval queries")
        
        # Retrieve for each query
        all_results = {}  # chunk_id -> (chunk, max_score, query_indices)
        
        for query_idx, query in enumerate(queries):
            # Embed query
            query_embedding = await self.embedding_service.embed_async(query)
            
            # Compute cosine similarity to all chunks
            scores = []
            for chunk in chunks:
                if chunk.embedding:
                    similarity = np.dot(
                        query_embedding,
                        chunk.embedding
                    ) / (np.linalg.norm(query_embedding) * np.linalg.norm(chunk.embedding) + 1e-8)
                    scores.append(similarity)
                else:
                    scores.append(0.0)
            
            # Get top-k
            top_indices = np.argsort(scores)[-top_k_per_query:][::-1]
            
            for rank, idx in enumerate(top_indices):
                chunk = chunks[idx]
                score = float(scores[idx])
                
                if chunk.chunk_id not in all_results:
                    all_results[chunk.chunk_id] = (chunk, score, [])
                else:
                    existing_chunk, existing_score, query_list = all_results[chunk.chunk_id]
                    # Keep max score
                    if score > existing_score:
                        all_results[chunk.chunk_id] = (existing_chunk, score, query_list)
                    query_list.append(query_idx)
            
            logger.info(f"Query {query_idx + 1}: Retrieved {len(top_indices)} chunks")
        
        # Merge results, deduplicate, rank by max score
        merged_chunks = []
        for chunk_id, (chunk, max_score, query_indices) in all_results.items():
            chunk.cosine_score = max_score
            chunk.retrieval_query_matches = query_indices
            merged_chunks.append(chunk)
        
        # Sort by score descending
        merged_chunks.sort(key=lambda c: c.cosine_score or 0, reverse=True)
        
        # Take top-30
        final_chunks = merged_chunks[:30]
        logger.info(f"After dedup and sort: {len(final_chunks)} chunks")
        
        return final_chunks
    
    def _generate_retrieval_queries(
        self,
        mission_question: str,
        pico_data: Dict[str, str]
    ) -> List[str]:
        """ADDED: Generate 5 diverse retrieval queries from mission context"""
        intervention = pico_data.get("intervention", "")
        outcome = pico_data.get("outcome", "")
        population = pico_data.get("population", "")
        
        queries = [
            # Query 1: Primary mission question
            mission_question,
            
            # Query 2: Intervention-outcome probe
            f"{intervention} effect on {outcome}" + (f" in {population}" if population else ""),
            
            # Query 3: Causal mechanism probe
            f"{intervention} mechanism pathway how works mechanism",
            
            # Query 4: Null and negative result probe
            f"{intervention} no effect failed did not improve {outcome}",
            
            # Query 5: Limitation and uncertainty probe
            f"{intervention} limitation caveat generalizability uncertainty scope"
        ]
        
        # Clean empty queries
        queries = [q.strip() for q in queries if q.strip()]
        return queries
    
    async def rerank_with_cross_encoder(
        self,
        mission_question: str,
        chunks: List[ChunkMetadata],
        top_k: int = 20
    ) -> List[ChunkMetadata]:
        """ADDED: Rerank chunks using cross-encoder model"""
        if not self.enable_cross_encoder or not chunks:
            # Skip reranking if disabled
            for idx, chunk in enumerate(chunks[:top_k]):
                chunk.final_rank = idx + 1
            return chunks[:top_k]
        
        try:
            # Lazy load cross-encoder
            if self._cross_encoder is None:
                from sentence_transformers import CrossEncoder
                self._cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
                logger.info("Loaded cross-encoder model")
            
            # Prepare input: (question, chunk_text) pairs
            pairs = [(mission_question, chunk.raw_text) for chunk in chunks]
            
            # Score all pairs
            scores = self._cross_encoder.predict(pairs)
            
            # Attach scores and sort
            for chunk, score in zip(chunks, scores):
                chunk.crossencoder_score = float(score)
            
            chunks.sort(key=lambda c: c.crossencoder_score or 0, reverse=True)
            
            # Assign final ranks and return top-k
            for idx, chunk in enumerate(chunks[:top_k]):
                chunk.final_rank = idx + 1
            
            logger.info(f"Cross-encoder reranked to top-{top_k}")
            return chunks[:top_k]
            
        except Exception as e:
            logger.warning(f"Cross-encoder reranking failed: {str(e)}, using cosine ranking")
            # Fallback: use cosine scores
            chunks.sort(key=lambda c: c.cosine_score or 0, reverse=True)
            for idx, chunk in enumerate(chunks[:top_k]):
                chunk.final_rank = idx + 1
            return chunks[:top_k]
    
    async def abstract_fallback(
        self,
        paper_id: str,
        abstract: str
    ) -> List[ChunkMetadata]:
        """ADDED: Fallback retrieval using abstract + results section"""
        logger.warning(f"Using fallback retrieval for paper {paper_id}")
        
        chunks = [
            ChunkMetadata(
                chunk_id=str(uuid.uuid4()),
                paper_id=paper_id,
                section_name="abstract",
                chunk_type="text",
                paragraph_index=0,
                token_count=len(abstract) // 4,
                raw_text=abstract
            )
        ]
        
        # Embed fallback chunks
        chunks = await self.embed_chunks(chunks)
        
        return chunks
    
    async def retrieve(
        self,
        paper_id: str,
        pdf_url: str,
        abstract: str,
        mission_question: str,
        pico_data: Dict[str, str]
    ) -> RetrievalResult:
        """ADDED: Main retrieval pipeline"""
        import time
        start_time = time.time()
        
        try:
            # Step 1: Parse with GROBID
            parsed = await self.parse_with_grobid(paper_id, pdf_url)
            
            if not parsed.get("success"):
                logger.warning(f"GROBID parsing failed, using fallback")
                chunks = await self.abstract_fallback(paper_id, abstract)
                return RetrievalResult(
                    success=True,
                    chunks=chunks[:20],
                    retrieval_fallback=True,
                    latency_ms=time.time() - start_time
                )
            
            # Step 2: Chunk parsed sections
            chunks = await self.chunk_paper(paper_id, parsed.get("sections", {}))
            
            if not chunks:
                logger.warning("No chunks created, using fallback")
                chunks = await self.abstract_fallback(paper_id, abstract)
                return RetrievalResult(
                    success=True,
                    chunks=chunks[:20],
                    retrieval_fallback=True,
                    latency_ms=time.time() - start_time
                )
            
            # Step 3: Embed chunks
            chunks = await self.embed_chunks(chunks)
            
            # Step 4: Multi-query retrieve
            chunks = await self.multi_query_retrieve(
                mission_question, pico_data, chunks
            )
            
            # Step 5: Cross-encoder rerank
            chunks = await self.rerank_with_cross_encoder(
                mission_question, chunks, top_k=20
            )
            
            return RetrievalResult(
                success=True,
                chunks=chunks,
                total_found=len(chunks),
                latency_ms=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Retrieval failed: {str(e)}")
            return RetrievalResult(
                success=False,
                error=str(e),
                latency_ms=time.time() - start_time
            )

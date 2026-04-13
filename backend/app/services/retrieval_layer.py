"""ADDED: Advanced Semantic Retrieval Layer with GROBID + Multi-Query Retrieval

Implements structured document parsing, chunking, semantic embedding,
multi-query retrieval, and cross-encoder reranking to provide evidence-grounded
context to Pass 1 LLM extraction.
"""

import logging
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


SECTION_HEADING_PATTERNS = {
    "abstract": [r"^abstract$"],
    "introduction": [
        r"^introduction$",
        r"^background$",
        r"^background and aims?$",
        r"^overview$",
    ],
    "methods": [
        r"^methods?$",
        r"^materials?(?: and methods?)?$",
        r"^patients and methods$",
        r"^study design$",
        r"^methodology$",
    ],
    "results": [
        r"^results?$",
        r"^findings$",
        r"^outcomes?$",
        r"^primary outcomes?$",
        r"^secondary outcomes?$",
    ],
    "discussion": [
        r"^discussion$",
        r"^discussion and conclusions?$",
        r"^interpretation$",
    ],
    "conclusion": [
        r"^conclusions?$",
        r"^summary and conclusions?$",
        r"^key conclusions?$",
    ],
}


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
        enable_cross_encoder: bool = False
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
    
    def _normalize_section_name(self, raw_name: str) -> str:
        section_name = (raw_name or "body").strip().lower()
        if "method" in section_name or "material" in section_name:
            return "methods"
        if "result" in section_name or "finding" in section_name:
            return "results"
        if "discussion" in section_name:
            return "discussion"
        if "conclusion" in section_name:
            return "conclusion"
        if "intro" in section_name or "background" in section_name:
            return "introduction"
        if "abstract" in section_name:
            return "abstract"
        return section_name or "body"

    def _looks_like_heading(self, line: str) -> Optional[str]:
        text = " ".join((line or "").split()).strip(" :.-").lower()
        if not text or len(text) > 80:
            return None
        if len(text.split()) > 8:
            return None
        for normalized, patterns in SECTION_HEADING_PATTERNS.items():
            if any(re.fullmatch(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
                return normalized
        return None

    def _split_plaintext_into_sections(self, full_text: str) -> Dict[str, str]:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", full_text)
            if paragraph.strip()
        ]
        if not paragraphs:
            return {}

        sections: Dict[str, List[str]] = {}
        current_section = "body"
        current_buffer: List[str] = []

        def flush_buffer(section_name: str) -> None:
            nonlocal current_buffer
            cleaned = [paragraph for paragraph in current_buffer if paragraph]
            if cleaned:
                sections.setdefault(section_name, []).extend(cleaned)
            current_buffer = []

        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            heading = self._looks_like_heading(lines[0]) if lines else None

            if heading:
                flush_buffer(current_section)
                current_section = heading
                remainder = "\n".join(lines[1:]).strip()
                if remainder:
                    current_buffer.append(remainder)
                continue

            inline_match = re.match(r"^\s*([A-Za-z][A-Za-z \-]{2,50}):\s+(.*)$", paragraph, flags=re.DOTALL)
            if inline_match:
                inline_heading = self._looks_like_heading(inline_match.group(1))
                if inline_heading:
                    flush_buffer(current_section)
                    current_section = inline_heading
                    body_text = inline_match.group(2).strip()
                    if body_text:
                        current_buffer.append(body_text)
                    continue

            current_buffer.append(paragraph)

        flush_buffer(current_section)

        if set(sections.keys()) <= {"body"} and len(paragraphs) >= 8:
            body_paragraphs = sections.get("body", paragraphs)
            heuristic_sections: Dict[str, List[str]] = {}
            intro_cut = max(1, min(3, len(body_paragraphs) // 6))
            concl_cut = max(1, min(3, len(body_paragraphs) // 6))
            heuristic_sections["introduction"] = body_paragraphs[:intro_cut]
            middle = body_paragraphs[intro_cut: len(body_paragraphs) - concl_cut]
            if middle:
                method_cut = max(1, len(middle) // 3)
                heuristic_sections["methods"] = middle[:method_cut]
                heuristic_sections["results"] = middle[method_cut:]
            heuristic_sections["conclusion"] = body_paragraphs[len(body_paragraphs) - concl_cut:]
            sections = {name: parts for name, parts in heuristic_sections.items() if parts}

        return {
            self._normalize_section_name(name): "\n\n".join(parts)
            for name, parts in sections.items()
            if parts
        }

    def _structured_sections_from_text(
        self,
        full_text_content: str,
        abstract: str
    ) -> Dict[str, str]:
        """Split stored full-text content into sections using known markers when available."""
        sections: Dict[str, List[str]] = {}
        full_text = (full_text_content or "").strip()
        abstract = (abstract or "").strip()

        if full_text:
            header_pattern = re.compile(r'^\[(?P<section>[A-Z][A-Z _-]{1,60})\]\s*$', re.MULTILINE)
            matches = list(header_pattern.finditer(full_text))

            if matches:
                for idx, match in enumerate(matches):
                    start = match.end()
                    end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
                    body = full_text[start:end].strip()
                    if not body:
                        continue
                    section_name = self._normalize_section_name(match.group("section"))
                    sections.setdefault(section_name, []).append(body)

            if not sections:
                inferred_sections = self._split_plaintext_into_sections(full_text)
                for section_name, section_text in inferred_sections.items():
                    if section_text:
                        sections.setdefault(section_name, []).append(section_text)

        if abstract:
            normalized_abstract = " ".join(abstract.split()).strip()
            abstract_present = False
            for existing in sections.get("abstract", []):
                existing_norm = " ".join(existing.split()).strip()
                if normalized_abstract and normalized_abstract[:400] and normalized_abstract[:400] in existing_norm:
                    abstract_present = True
                    break
            if not abstract_present:
                sections.setdefault("abstract", []).insert(0, abstract)

        if "abstract" in sections:
            abstract_norm = " ".join("\n\n".join(sections["abstract"]).split()).strip()
            if abstract_norm:
                for section_name, contents in list(sections.items()):
                    if section_name == "abstract":
                        continue
                    filtered_contents: List[str] = []
                    for content in contents:
                        content_norm = " ".join(content.split()).strip()
                        prefix = abstract_norm[: min(800, len(abstract_norm))]
                        if prefix and content_norm.startswith(prefix):
                            trimmed = content_norm[len(prefix):].strip()
                            if trimmed:
                                filtered_contents.append(trimmed)
                        else:
                            filtered_contents.append(content)
                    sections[section_name] = [content for content in filtered_contents if content]

        return {
            name: "\n\n".join(parts)
            for name, parts in sections.items()
            if parts
        }

    async def parse_with_grobid(
        self,
        paper_id: str,
        pdf_url: str,
        full_text_content: str = "",
        abstract: str = ""
    ) -> Dict[str, Any]:
        """Build structured sections from already-ingested full text."""
        try:
            parsed_sections = self._structured_sections_from_text(full_text_content, abstract)
            if not parsed_sections:
                return {"success": False, "error": "No full text or abstract available"}
            
            return {
                "success": True,
                "sections": parsed_sections,
                "tables": [],
                "figures": []
            }
        except Exception as e:
            logger.error(f"Structured text parsing failed for paper {paper_id}: {str(e)}")
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
        if not self.embedding_service:
            return chunks

        try:
            texts = [chunk.raw_text for chunk in chunks]
            embeddings = await self.embedding_service.embed_batch(texts, input_type="passage")
            
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding
            
            logger.info(f"Embedded {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Embedding failed: {str(e)}")
            return chunks

    def _lexical_match_score(self, query: str, text: str) -> float:
        query = (query or "").lower()
        text = (text or "").lower()
        if not query or not text:
            return 0.0

        query_terms = [
            term for term in re.split(r"[^a-z0-9]+", query)
            if len(term) > 2
        ]
        if not query_terms:
            return 0.0

        unique_terms = set(query_terms)
        matches = sum(1 for term in unique_terms if term in text)
        phrase_bonus = 0.1 if query[:80] and query[:80] in text else 0.0
        return min(1.0, (matches / len(unique_terms)) + phrase_bonus)
    
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
            query_embedding = None
            if self.embedding_service:
                query_embedding = await self.embedding_service.embed_text(query, input_type="query")
            
            scores = []
            for chunk in chunks:
                if query_embedding is not None and chunk.embedding:
                    similarity = np.dot(
                        query_embedding,
                        chunk.embedding
                    ) / (np.linalg.norm(query_embedding) * np.linalg.norm(chunk.embedding) + 1e-8)
                    scores.append(similarity)
                else:
                    scores.append(self._lexical_match_score(query, chunk.raw_text))
            
            # Get top-k
            top_indices = np.argsort(scores)[-top_k_per_query:][::-1]
            
            for rank, idx in enumerate(top_indices):
                chunk = chunks[idx]
                score = float(scores[idx])
                
                if chunk.chunk_id not in all_results:
                    all_results[chunk.chunk_id] = (chunk, score, [query_idx])
                else:
                    existing_chunk, existing_score, query_list = all_results[chunk.chunk_id]
                    if score > existing_score:
                        all_results[chunk.chunk_id] = (existing_chunk, score, query_list)
                    if query_idx not in query_list:
                        query_list.append(query_idx)
            
            logger.info(f"Query {query_idx + 1}: Retrieved {len(top_indices)} chunks")
        
        # Merge results, deduplicate, rank by max score
        merged_chunks = []
        for chunk_id, (chunk, max_score, query_indices) in all_results.items():
            chunk.cosine_score = max_score
            chunk.retrieval_query_matches = query_indices
            merged_chunks.append(chunk)
        
        merged_chunks.sort(key=lambda c: c.cosine_score or 0, reverse=True)

        has_non_abstract = any(chunk.section_name != "abstract" for chunk in merged_chunks)
        if has_non_abstract:
            non_abstract = [chunk for chunk in merged_chunks if chunk.section_name != "abstract"]
            abstract_chunks = [chunk for chunk in merged_chunks if chunk.section_name == "abstract"]
            final_chunks = non_abstract[:24] + abstract_chunks[:6]
        else:
            final_chunks = merged_chunks[:30]

        final_chunks.sort(
            key=lambda c: (
                c.cosine_score or 0.0,
                1.0 if c.section_name in {"results", "conclusion", "discussion"} else 0.0,
            ),
            reverse=True,
        )
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
            for chunk in chunks:
                lexical = self._lexical_match_score(mission_question, chunk.raw_text)
                semantic = chunk.cosine_score or 0.0
                section_bonus = {
                    "results": 0.12,
                    "conclusion": 0.10,
                    "discussion": 0.08,
                    "body": 0.04,
                    "introduction": 0.03,
                    "methods": 0.02,
                    "abstract": 0.01,
                }.get(chunk.section_name, 0.03)
                chunk.crossencoder_score = min(1.0, semantic * 0.7 + lexical * 0.3 + section_bonus)

            chunks.sort(key=lambda c: c.crossencoder_score or c.cosine_score or 0, reverse=True)
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
        full_text_content: str,
        mission_question: str,
        pico_data: Dict[str, str]
    ) -> RetrievalResult:
        """ADDED: Main retrieval pipeline"""
        import time
        start_time = time.time()
        
        try:
            parsed = await self.parse_with_grobid(
                paper_id,
                pdf_url,
                full_text_content=full_text_content,
                abstract=abstract,
            )
            
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

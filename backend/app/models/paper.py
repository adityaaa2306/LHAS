"""Research Paper Database Models"""

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Uuid, ForeignKey, JSON, Index, Enum
from sqlalchemy.orm import relationship
from .mission import Base
import enum


class PaperSource(str, enum.Enum):
    """Paper source identifier"""
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    PUBMED = "pubmed"


class ResearchPaper(Base):
    """Stores research papers retrieved and selected for missions."""

    __tablename__ = "research_papers"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, index=True)
    
    # Paper identifiers
    paper_id = Column(String(255), nullable=False, index=True)  # External ID (arxiv, semantic_scholar, etc.)
    doi = Column(String(255), nullable=True, index=True)
    
    # Core metadata
    title = Column(Text, nullable=False)
    authors = Column(JSON, nullable=True)  # List of author names
    abstract = Column(Text, nullable=True)
    year = Column(Integer, nullable=True, index=True)
    source = Column(Enum(PaperSource), nullable=False, index=True)
    
    # URLs
    arxiv_url = Column(String(500), nullable=True)
    semantic_scholar_url = Column(String(500), nullable=True)
    pubmed_url = Column(String(500), nullable=True)
    pdf_url = Column(String(500), nullable=True)
    
    # Relevance scores
    final_score = Column(Float, nullable=False)  # Combined score (0-1)
    relevance_score = Column(Float, nullable=True)  # LLM relevance (0-1)
    usefulness_score = Column(Float, nullable=True)  # LLM usefulness (0-1)
    embedding_similarity = Column(Float, nullable=True)  # Embedding similarity to query
    keyword_overlap = Column(Float, nullable=True)  # Keyword match score

    # CEGC component scores (Layers 1-5)
    pico_match_score = Column(Float, nullable=True)         # Layer 1
    evidence_strength_score = Column(Float, nullable=True)  # Layer 2
    mechanism_agreement_score = Column(Float, nullable=True)  # Layer 3
    assumption_alignment_score = Column(Float, nullable=True)  # Layer 4
    llm_verification_score = Column(Float, nullable=True)   # Layer 5
    score_breakdown = Column(JSON, nullable=True)           # {"pico": 0.93, ...}
    reasoning_graph = Column(JSON, nullable=True)           # Graph structure
    mechanism_description = Column(Text, nullable=True)     # Human-readable mechanism
    
    # Processing flags
    selected = Column(Integer, default=1, nullable=False)  # 1=selected, 0=rejected
    full_text_flag = Column(Integer, default=0, nullable=False)  # 1=needs full-text, 0=abstract sufficient
    full_text_content = Column(Text, nullable=True)  # Parsed full-text (if available)
    
    # PICO relevance (for biomedical papers)
    pico_population_match = Column(Integer, default=0, nullable=False)
    pico_intervention_match = Column(Integer, default=0, nullable=False)
    pico_comparator_match = Column(Integer, default=0, nullable=False)
    pico_outcome_match = Column(Integer, default=0, nullable=False)
    
    # Metadata
    keywords = Column(JSON, nullable=True)  # Extracted keywords
    citations_count = Column(Integer, nullable=True)
    influence_score = Column(Float, nullable=True)  # From Semantic Scholar
    
    # Timestamps
    published_date = Column(DateTime, nullable=True)
    retrieved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    # Ingestion batch tracking
    ingestion_batch_id = Column(String(36), nullable=True, index=True)
    rank_in_ingestion = Column(Integer, nullable=True)  # Rank in this ingestion session
    
    # Embedding vector (stored as JSON array for compatibility)
    embedding = Column(JSON, nullable=True)  # [768] float vector from llama-nemotron-embed-1b-v2
    
    __table_args__ = (
        Index('ix_paper_mission_selected', 'mission_id', 'selected'),
        Index('ix_paper_mission_score', 'mission_id', 'final_score'),
        Index('ix_paper_source_year', 'source', 'year'),
    )

    def __repr__(self) -> str:
        return f"<ResearchPaper id={self.id} title={self.title[:50]}...>"


class IngestionEvent(Base):
    """Tracks paper ingestion sessions for audit and optimization."""

    __tablename__ = "ingestion_events"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, index=True)
    
    # Session tracking
    batch_id = Column(String(36), nullable=False, index=True)
    session_number = Column(Integer, nullable=False)
    
    # Pipeline statistics
    total_retrieved = Column(Integer, nullable=False)  # From all sources
    after_dedup = Column(Integer, nullable=False)  # After deduplication
    after_prefilter = Column(Integer, nullable=False)  # After embedding/keyword filter
    after_rerank = Column(Integer, nullable=False)  # After LLM reranking
    final_selected = Column(Integer, nullable=False)  # Final MMR selection
    
    # Scores
    avg_relevance_score = Column(Float, nullable=True)
    avg_usefulness_score = Column(Float, nullable=True)
    avg_final_score = Column(Float, nullable=True)
    
    # Config used
    max_candidates = Column(Integer, nullable=False)
    prefilter_k = Column(Integer, nullable=False)
    final_k = Column(Integer, nullable=False)
    relevance_threshold = Column(Float, nullable=False)
    sources_used = Column(JSON, nullable=False)  # List of sources used
    
    # Processing metrics
    total_llm_calls = Column(Integer, nullable=False)
    total_llm_tokens = Column(Integer, nullable=False)
    processing_time_seconds = Column(Float, nullable=True)
    
    # Status
    status = Column(String(50), nullable=False)  # success, partial, failed
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<IngestionEvent batch={self.batch_id} mission={self.mission_id} selected={self.final_selected}>"

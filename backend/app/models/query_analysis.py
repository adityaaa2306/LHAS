"""Query Analysis Database Model"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, JSON, String, Text, Uuid, ForeignKey
from .mission import Base


class QueryAnalysis(Base):
    """Stores query understanding analysis results for auditing and improvement."""

    __tablename__ = "query_analysis"

    id = Column(Uuid, primary_key=True, default=uuid4)
    mission_id = Column(Uuid, nullable=False, index=True)
    original_query = Column(Text, nullable=False)
    normalized_query = Column(Text, nullable=False)
    intent_type = Column(String(50), nullable=False)
    pico = Column(JSON, nullable=True)
    key_concepts = Column(JSON, nullable=True)
    search_queries = Column(JSON, nullable=True)
    ambiguity_flags = Column(JSON, nullable=True)
    interpretation_variants = Column(JSON, nullable=True)
    suggested_refinements = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=False)
    decision = Column(String(50), nullable=False)
    reasoning_steps = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<QueryAnalysis id={self.id} mission_id={self.mission_id} decision={self.decision}>"

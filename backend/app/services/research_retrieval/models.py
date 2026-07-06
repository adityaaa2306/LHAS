"""Data models for the research retrieval planner and execution report."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ResearchEntity:
    """A biomedical entity extracted from the user question."""

    name: str
    entity_type: str  # drug, gene, disease, protein, treatment, biomarker, etc.
    canonical_names: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    drug_class: Optional[str] = None
    mesh_terms: List[str] = field(default_factory=list)


@dataclass
class ResearchIntent:
    """Structured understanding of what evidence the user needs."""

    domain: str  # medical, general_science, etc.
    primary_question: str
    research_goals: List[str] = field(default_factory=list)
    coverage_dimensions: List[str] = field(default_factory=list)
    study_types_wanted: List[str] = field(default_factory=list)
    is_medical: bool = False


@dataclass
class PlannedSearch:
    """A single source-specific search to execute."""

    source: str
    query: str
    strategy: str
    priority: int = 1
    mesh_terms: List[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class RetrievalPlan:
    """Full retrieval plan produced before any API calls."""

    entities: List[ResearchEntity]
    intent: ResearchIntent
    searches: List[PlannedSearch]
    complexity: str = "standard"  # simple | standard | complex
    planner_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [asdict(e) for e in self.entities],
            "intent": asdict(self.intent),
            "searches": [asdict(s) for s in self.searches],
            "complexity": self.complexity,
            "planner_notes": self.planner_notes,
            "total_planned_searches": len(self.searches),
        }


@dataclass
class QueryExecutionResult:
    """Outcome of a single planned search."""

    source: str
    query: str
    strategy: str
    papers_found: int
    error: Optional[str] = None


@dataclass
class RejectedPaper:
    """Paper rejected during quality control."""

    paper_id: str
    title: str
    reason: str


@dataclass
class CoverageReport:
    """Coverage validation after retrieval."""

    dimensions_covered: Dict[str, int] = field(default_factory=dict)
    dimensions_missing: List[str] = field(default_factory=list)
    coverage_score: float = 0.0
    gap_fill_searches: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalReport:
    """Full transparency report for UI and logging."""

    plan: RetrievalPlan
    executions: List[QueryExecutionResult] = field(default_factory=list)
    rejected_papers: List[RejectedPaper] = field(default_factory=list)
    coverage: Optional[CoverageReport] = None
    confidence_score: float = 0.0
    total_candidates: int = 0
    after_dedup: int = 0
    after_qc: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "executions": [asdict(e) for e in self.executions],
            "rejected_papers": [asdict(r) for r in self.rejected_papers[:50]],
            "rejected_count": len(self.rejected_papers),
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "confidence_score": round(self.confidence_score, 3),
            "total_candidates": self.total_candidates,
            "after_dedup": self.after_dedup,
            "after_qc": self.after_qc,
            "source_counts": self._source_counts(),
            "queries_executed": len(self.executions),
        }

    def _source_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for ex in self.executions:
            counts[ex.source] = counts.get(ex.source, 0) + ex.papers_found
        return counts

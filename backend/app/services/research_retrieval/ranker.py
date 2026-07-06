"""Evidence ranking — multi-factor scoring beyond embedding similarity."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, List, Optional

from app.services.research_retrieval.models import ResearchIntent, RetrievalPlan

STUDY_TYPE_BOOSTS = {
    "systematic review": 0.25,
    "meta-analysis": 0.25,
    "meta analysis": 0.25,
    "randomized controlled trial": 0.20,
    "randomised controlled trial": 0.20,
    "clinical trial": 0.12,
    "cohort study": 0.08,
    "observational": 0.06,
    "guideline": 0.15,
    "review": 0.10,
}

OFF_TOPIC_PATTERNS = [
    r"\bibd\b",
    r"inflammatory bowel",
    r"plant (biology|physiology|growth)",
    r"arabidopsis",
    r"breast cancer (survivor|aftercare|reconstruction)",
]


def study_type_score(title: str, abstract: str) -> float:
    text = f"{title} {abstract}".lower()
    score = 0.0
    for phrase, boost in STUDY_TYPE_BOOSTS.items():
        if phrase in text:
            score = max(score, boost)
    return score


def citation_score(citations: Optional[int]) -> float:
    if citations is None or citations <= 0:
        return 0.0
    return min(0.20, math.log1p(citations) / 25.0)


def recency_score(year: Optional[int], current_year: Optional[int] = None) -> float:
    if not year:
        return 0.0
    now = current_year or datetime.utcnow().year
    age = max(0, now - year)
    if age <= 2:
        return 0.15
    if age <= 5:
        return 0.10
    if age <= 10:
        return 0.05
    return 0.0


def abstract_completeness_score(abstract: str) -> float:
    length = len((abstract or "").strip())
    if length >= 500:
        return 0.10
    if length >= 200:
        return 0.06
    if length >= 80:
        return 0.03
    return 0.0


def open_access_bonus(paper: Any) -> float:
    if getattr(paper, "pdf_url", None):
        return 0.05
    raw = getattr(paper, "raw_data", None) or {}
    if raw.get("open_access") or raw.get("retrieval_source") == "europe_pmc":
        return 0.03
    return 0.0


def entity_overlap_score(paper: Any, plan: RetrievalPlan) -> float:
    text = f"{getattr(paper, 'title', '')} {getattr(paper, 'abstract', '')}".lower()
    if not text.strip():
        return 0.0

    terms: List[str] = []
    for entity in plan.entities:
        terms.extend(entity.synonyms)
        terms.extend(entity.canonical_names)
        if entity.drug_class:
            terms.append(entity.drug_class)
        terms.append(entity.name)

    unique = list({t.lower() for t in terms if t and len(t) > 2})
    if not unique:
        return 0.5

    hits = sum(1 for t in unique if t in text)
    return min(1.0, hits / max(1, min(len(unique), 5)))


def rank_papers(
    papers: List[Any],
    plan: RetrievalPlan,
    embedding_similarities: Optional[dict] = None,
) -> List[Any]:
    """Score and sort papers using multi-factor evidence ranking."""
    scored = []
    for paper in papers:
        sim = (embedding_similarities or {}).get(paper.paper_id, 0.0)
        entity = entity_overlap_score(paper, plan)
        study = study_type_score(paper.title or "", paper.abstract or "")
        cites = citation_score(paper.citations_count)
        recency = recency_score(paper.year)
        abstract_q = abstract_completeness_score(paper.abstract or "")
        oa = open_access_bonus(paper)

        # Weighted composite — semantic similarity is one signal, not the only one
        composite = (
            0.30 * sim
            + 0.25 * entity
            + study
            + cites
            + recency
            + abstract_q
            + oa
        )
        if plan.intent.is_medical and entity < 0.15:
            composite *= 0.5

        paper.evidence_rank_score = round(composite, 4)
        paper.score_breakdown = {
            "embedding_similarity": round(sim, 3),
            "entity_overlap": round(entity, 3),
            "study_type": round(study, 3),
            "citations": round(cites, 3),
            "recency": round(recency, 3),
            "abstract_quality": round(abstract_q, 3),
            "open_access": round(oa, 3),
        }
        scored.append((composite, paper))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def is_obviously_irrelevant(paper: Any, plan: RetrievalPlan) -> Optional[str]:
    """Return rejection reason if paper is clearly off-topic."""
    title = (paper.title or "").lower()
    abstract = (paper.abstract or "").lower()
    text = f"{title} {abstract}"

    entity = entity_overlap_score(paper, plan)
    if entity >= 0.2:
        return None

    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, text, re.I):
            return f"Off-topic pattern: {pattern}"

    if plan.intent.is_medical and entity < 0.05 and len(text) > 50:
        return "No entity overlap with research question"

    return None

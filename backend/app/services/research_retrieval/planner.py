"""Retrieval planner — intent analysis, entity extraction, multi-query planning."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.research_retrieval.models import (
    PlannedSearch,
    ResearchEntity,
    ResearchIntent,
    RetrievalPlan,
)
from app.services.research_retrieval.ontology import (
    STUDY_TYPE_PHRASES,
    default_medical_dimensions,
    expand_entity_from_text,
    lookup_drug,
)

logger = logging.getLogger(__name__)

MIN_PLANNED_SEARCHES = 10
MAX_PLANNED_SEARCHES = 30


class RetrievalPlanner:
    """Plans source-specific searches from user research intent — never raw NL only."""

    def __init__(self, llm_provider: Any = None):
        self.llm = llm_provider

    async def plan(self, structured_query: dict) -> RetrievalPlan:
        query_text = (structured_query.get("normalized_query") or "").strip()
        key_concepts = structured_query.get("key_concepts") or []
        intent_type = structured_query.get("intent_type") or structured_query.get("domain") or ""

        llm_data = await self._llm_analyze(query_text, key_concepts, intent_type)
        entities = self._build_entities(query_text, key_concepts, llm_data)
        intent = self._build_intent(query_text, key_concepts, llm_data, entities)
        searches = self._generate_searches(entities, intent, query_text)
        complexity = "complex" if intent.is_medical and len(searches) >= 20 else "standard"

        return RetrievalPlan(
            entities=entities,
            intent=intent,
            searches=searches[:MAX_PLANNED_SEARCHES],
            complexity=complexity,
            planner_notes=llm_data.get("notes", "Rule-based + LLM hybrid planning"),
        )

    async def _llm_analyze(
        self, query_text: str, key_concepts: List[str], intent_type: str
    ) -> Dict[str, Any]:
        if not self.llm or not query_text:
            return {}

        prompt = f"""You are an expert medical research librarian planning a literature search.

User question: {query_text}
Key concepts: {', '.join(key_concepts)}
Intent type: {intent_type}

Analyze this research question. Return JSON only:
{{
  "domain": "medical|general_science|other",
  "entities": [
    {{"name": "Ozempic", "type": "drug", "canonical": "semaglutide", "drug_class": "GLP-1 receptor agonist", "synonyms": ["ozempic","semaglutide"], "mesh": ["Semaglutide"]}}
  ],
  "research_goals": ["long-term safety", "adverse effects", "cardiovascular outcomes"],
  "coverage_dimensions": ["pancreatitis", "thyroid cancer", "kidney effects"],
  "study_types": ["systematic review", "meta-analysis", "RCT", "observational", "guideline"],
  "notes": "brief planning rationale"
}}

Extract ALL relevant biomedical entities (drugs, genes, diseases, proteins, biomarkers).
Map brand names to generic/canonical names. Never return only the raw user question as a search strategy."""

        try:
            response = await self.llm.generate_async(
                [
                    {"role": "system", "content": "You plan rigorous scientific literature searches. JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
            )
            content = response.get("content", "")
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as exc:
            logger.warning("LLM retrieval planning failed: %s", exc)
        return {}

    def _build_entities(
        self, query_text: str, key_concepts: List[str], llm_data: Dict[str, Any]
    ) -> List[ResearchEntity]:
        entities: List[ResearchEntity] = []
        seen: set = set()

        def add_entity(
            name: str,
            entity_type: str,
            canonical: Optional[str] = None,
            drug_class: Optional[str] = None,
            synonyms: Optional[List[str]] = None,
            mesh: Optional[List[str]] = None,
        ) -> None:
            key = (canonical or name).lower()
            if key in seen:
                return
            seen.add(key)
            entities.append(
                ResearchEntity(
                    name=name,
                    entity_type=entity_type,
                    canonical_names=[canonical] if canonical else [name],
                    synonyms=synonyms or [name],
                    drug_class=drug_class,
                    mesh_terms=mesh or [],
                )
            )

        for item in llm_data.get("entities") or []:
            add_entity(
                name=item.get("name", ""),
                entity_type=item.get("type", "unknown"),
                canonical=item.get("canonical"),
                drug_class=item.get("drug_class"),
                synonyms=item.get("synonyms"),
                mesh=item.get("mesh"),
            )

        for brand, entry in expand_entity_from_text(query_text):
            add_entity(
                name=brand.title(),
                entity_type="drug",
                canonical=str(entry.get("canonical", "")),
                drug_class=str(entry.get("drug_class", "")) or None,
                synonyms=list(entry.get("synonyms", [])),
                mesh=list(entry.get("mesh", [])),
            )

        for concept in key_concepts:
            drug = lookup_drug(concept)
            if drug:
                add_entity(
                    name=concept,
                    entity_type="drug",
                    canonical=str(drug.get("canonical", "")),
                    drug_class=str(drug.get("drug_class", "")) or None,
                    synonyms=list(drug.get("synonyms", [])),
                    mesh=list(drug.get("mesh", [])),
                )
            elif concept.lower() not in seen:
                add_entity(concept, "concept", synonyms=[concept])

        if not entities and query_text:
            for term in self._token_terms(query_text)[:3]:
                add_entity(term, "concept", synonyms=[term])

        return entities

    def _build_intent(
        self,
        query_text: str,
        key_concepts: List[str],
        llm_data: Dict[str, Any],
        entities: List[ResearchEntity],
    ) -> ResearchIntent:
        domain = llm_data.get("domain") or "general_science"
        is_medical = domain == "medical" or any(e.entity_type == "drug" for e in entities)
        if any(w in query_text.lower() for w in ("effect", "safety", "adverse", "treatment", "drug", "clinical")):
            is_medical = True
            domain = "medical"

        goals = llm_data.get("research_goals") or []
        if not goals and is_medical:
            goals = ["safety", "efficacy", "long-term outcomes"]

        dimensions = llm_data.get("coverage_dimensions") or []
        if is_medical and len(dimensions) < 5:
            dimensions = default_medical_dimensions(query_text)

        study_types = llm_data.get("study_types") or [
            "systematic review",
            "meta-analysis",
            "RCT",
            "observational",
            "guideline",
        ]

        return ResearchIntent(
            domain=domain,
            primary_question=query_text,
            research_goals=goals,
            coverage_dimensions=dimensions,
            study_types_wanted=study_types,
            is_medical=is_medical,
        )

    def _generate_searches(
        self,
        entities: List[ResearchEntity],
        intent: ResearchIntent,
        query_text: str,
    ) -> List[PlannedSearch]:
        searches: List[PlannedSearch] = []
        seen_queries: set = set()

        def add(
            source: str,
            query: str,
            strategy: str,
            priority: int = 1,
            mesh: Optional[List[str]] = None,
            rationale: str = "",
        ) -> None:
            q = re.sub(r"\s+", " ", (query or "").strip())
            if not q:
                return
            key = (source, q.lower())
            if key in seen_queries:
                return
            seen_queries.add(key)
            searches.append(
                PlannedSearch(
                    source=source,
                    query=q,
                    strategy=strategy,
                    priority=priority,
                    mesh_terms=mesh or [],
                    rationale=rationale,
                )
            )

        primary_terms = self._primary_search_terms(entities, query_text)

        for term in primary_terms:
            add("pubmed", term, "entity_keyword", priority=1, rationale="Core entity PubMed search")
            add("semantic_scholar", term, "entity_keyword", priority=1)
            add("europe_pmc", term, "entity_keyword", priority=1)
            add("openalex", term, "entity_keyword", priority=2)

        if intent.is_medical:
            for entity in entities:
                canon = (entity.canonical_names[0] if entity.canonical_names else entity.name).lower()
                drug_class = (entity.drug_class or "").lower()
                for dim in intent.coverage_dimensions[:12]:
                    dim_short = dim.split()[0] if dim else dim
                    add(
                        "pubmed",
                        f"{canon} {dim}",
                        "entity_dimension",
                        priority=1,
                        mesh=entity.mesh_terms,
                        rationale=f"Entity + coverage dimension: {dim}",
                    )
                    add(
                        "semantic_scholar",
                        f"{canon} {dim} systematic review",
                        "dimension_review",
                        priority=2,
                    )
                    if drug_class:
                        add(
                            "pubmed",
                            f"{drug_class} {dim_short}",
                            "class_dimension",
                            priority=2,
                        )

                for study_key, phrases in STUDY_TYPE_PHRASES.items():
                    if study_key not in [s.lower() for s in intent.study_types_wanted]:
                        continue
                    phrase = phrases[0]
                    add(
                        "pubmed",
                        f"{canon} {phrase}",
                        f"study_type_{study_key}",
                        priority=1,
                    )
                    add(
                        "semantic_scholar",
                        f"{canon} {phrase}",
                        f"study_type_{study_key}",
                        priority=2,
                    )

                if entity.mesh_terms:
                    mesh_q = " AND ".join(f'"{m}"[MeSH Terms]' for m in entity.mesh_terms[:2])
                    add("pubmed", mesh_q, "mesh_terms", priority=1, mesh=entity.mesh_terms)

                add("clinical_trials", canon, "clinical_trials", priority=2)
                add("crossref", f"{canon} adverse effects", "crossref_metadata", priority=3)

        else:
            for term in primary_terms[:4]:
                add("arxiv", term, "preprint", priority=2)
                add("semantic_scholar", f"{term} review", "review", priority=2)
                add("openalex", term, "broad_nl", priority=2)

        # Never search only the raw conversational question — deprioritize if present
        if query_text and len(searches) < MIN_PLANNED_SEARCHES:
            sanitized = self._sanitize_nl(query_text)
            if sanitized:
                add("semantic_scholar", sanitized, "sanitized_nl", priority=3)

        searches.sort(key=lambda s: s.priority)
        return searches

    def _primary_search_terms(
        self, entities: List[ResearchEntity], query_text: str
    ) -> List[str]:
        terms: List[str] = []
        seen: set = set()

        def push(t: str) -> None:
            t = (t or "").strip()
            if not t or len(t) < 3:
                return
            k = t.lower()
            if k in seen:
                return
            seen.add(k)
            terms.append(t)

        for entity in entities:
            for syn in entity.synonyms[:4]:
                push(syn)
            for canon in entity.canonical_names:
                push(canon)
            if entity.drug_class:
                push(entity.drug_class)

        if not terms:
            for t in self._token_terms(query_text):
                push(t)

        return terms[:8]

    def _token_terms(self, text: str) -> List[str]:
        stop = {
            "what", "are", "the", "long", "term", "effects", "our", "bodies", "how",
            "does", "do", "is", "a", "an", "on", "of", "for", "and", "or", "in", "to",
            "with", "about", "from", "that", "this", "human", "body", "impact", "over", "time",
        }
        return [
            w for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text or "")
            if w.lower() not in stop
        ]

    def _sanitize_nl(self, text: str) -> str:
        terms = self._token_terms(text)
        return " ".join(terms[:8]) if terms else ""

    def plan_gap_fill(
        self,
        plan: RetrievalPlan,
        missing_dimensions: List[str],
    ) -> List[PlannedSearch]:
        """Generate targeted searches for uncovered evidence dimensions."""
        gap_searches: List[PlannedSearch] = []
        primary = self._primary_search_terms(plan.entities, plan.intent.primary_question)
        canon = primary[0].lower() if primary else ""

        for dim in missing_dimensions[:6]:
            if not canon:
                continue
            gap_searches.append(
                PlannedSearch(
                    source="pubmed",
                    query=f"{canon} {dim}",
                    strategy="gap_fill",
                    priority=1,
                    rationale=f"Coverage gap: {dim}",
                )
            )
            gap_searches.append(
                PlannedSearch(
                    source="semantic_scholar",
                    query=f"{canon} {dim}",
                    strategy="gap_fill",
                    priority=1,
                    rationale=f"Coverage gap: {dim}",
                )
            )
        return gap_searches

"""Research retrieval engine — orchestrates planner, parallel search, merge, QC, ranking."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.research_retrieval.connectors import (
    ClinicalTrialsConnector,
    CrossrefConnector,
    EuropePMCConnector,
    OpenAlexConnector,
)
from app.services.research_retrieval.models import (
    CoverageReport,
    QueryExecutionResult,
    RejectedPaper,
    RetrievalPlan,
    RetrievalReport,
)
from app.services.research_retrieval.planner import RetrievalPlanner
from app.services.research_retrieval.ranker import is_obviously_irrelevant, rank_papers

logger = logging.getLogger(__name__)

MIN_CANDIDATES = 25
MIN_COVERAGE_DIMENSIONS = 0.5  # fraction of dimensions that need at least 1 paper
COVERAGE_MIN_PER_DIMENSION = 1


class ResearchRetrievalEngine:
    """Production-grade evidence retrieval — plans like a PhD researcher, not a keyword engine."""

    def __init__(
        self,
        *,
        pubmed: Any,
        semantic_scholar: Any,
        arxiv: Any,
        llm_provider: Any = None,
        embedding_service: Any = None,
        progress: Any = None,
    ):
        self.pubmed = pubmed
        self.semantic_scholar = semantic_scholar
        self.arxiv = arxiv
        self.europe_pmc = EuropePMCConnector()
        self.openalex = OpenAlexConnector()
        self.clinical_trials = ClinicalTrialsConnector()
        self.crossref = CrossrefConnector()
        self.planner = RetrievalPlanner(llm_provider)
        self.embedding_service = embedding_service
        self.progress = progress
        self._semaphore = asyncio.Semaphore(6)

    async def retrieve(
        self,
        structured_query: dict,
        config: Any,
    ) -> Tuple[List[Any], RetrievalReport]:
        if self.progress:
            await self.progress.set_stage(
                "query_expansion",
                detail="Analyzing research intent and planning searches",
                progress=5,
                activity="Retrieval planner: extracting entities and building search strategies",
            )

        plan = await self.planner.plan(structured_query)
        logger.info(
            "Retrieval plan: %d searches, %d entities, medical=%s",
            len(plan.searches),
            len(plan.entities),
            plan.intent.is_medical,
        )

        if self.progress:
            self.progress.update_stats(retrieval_plan=plan.to_dict())
            await self.progress.set_stage(
                "searching_papers",
                detail=f"Executing {len(plan.searches)} planned searches",
                progress=10,
                activity=f"Planned {len(plan.searches)} source-specific searches",
            )

        per_query_limit = max(15, config.max_candidates // max(len(plan.searches), 1))
        executions, candidates = await self._execute_searches(plan, config, per_query_limit)

        deduplicated = self._deduplicate(candidates)
        rejected, after_qc = self._quality_filter(deduplicated, plan)

        coverage = self._assess_coverage(after_qc, plan)
        gap_fill_count = 0

        if (
            len(after_qc) < MIN_CANDIDATES
            or coverage.coverage_score < MIN_COVERAGE_DIMENSIONS
        ):
            gap_searches = self.planner.plan_gap_fill(plan, coverage.dimensions_missing)
            if gap_searches:
                gap_fill_count = len(gap_searches)
                if self.progress:
                    self.progress._log_activity_sync(
                        f"Coverage gap-fill: {len(coverage.dimensions_missing)} dimensions, "
                        f"{len(gap_searches)} extra searches",
                    )
                extra_exec, extra_papers = await self._execute_searches(
                    plan, config, per_query_limit, override_searches=gap_searches
                )
                executions.extend(extra_exec)
                merged = self._deduplicate(after_qc + extra_papers)
                rej2, after_qc = self._quality_filter(merged, plan)
                rejected.extend(rej2)
                coverage = self._assess_coverage(after_qc, plan)
                coverage.gap_fill_searches = gap_fill_count

        ranked = await self._rank_candidates(after_qc, plan, structured_query)
        trimmed = ranked[: config.max_candidates]

        confidence = self._confidence_score(
            len(trimmed), coverage, len(plan.searches), len(rejected)
        )

        report = RetrievalReport(
            plan=plan,
            executions=executions,
            rejected_papers=rejected,
            coverage=coverage,
            confidence_score=confidence,
            total_candidates=len(candidates),
            after_dedup=len(deduplicated),
            after_qc=len(after_qc),
        )

        source_counts = report.to_dict()["source_counts"]
        if self.progress:
            self.progress.update_stats(
                candidates_retrieved=len(trimmed),
                source_counts=source_counts,
                retrieval_plan=report.to_dict(),
            )
            await self.progress.set_stage(
                "searching_papers",
                detail=f"Retrieved {len(trimmed)} evidence candidates (confidence {confidence:.0%})",
                progress=16,
                activity=f"Evidence retrieval complete — {len(trimmed)} candidates, "
                f"{len(rejected)} rejected as irrelevant",
            )

        return trimmed, report

    async def _execute_searches(
        self,
        plan: RetrievalPlan,
        config: Any,
        per_query_limit: int,
        override_searches: Optional[list] = None,
    ) -> Tuple[List[QueryExecutionResult], List[Any]]:
        searches = override_searches or plan.searches
        enabled = set(config.sources or [])
        # Extended sources are auto-enabled for medical missions
        if plan.intent.is_medical:
            enabled.update({"pubmed", "semantic_scholar", "europe_pmc", "openalex", "clinical_trials", "crossref"})
        else:
            enabled.update({"arxiv", "semantic_scholar", "openalex"})

        runnable = []
        tasks = []
        for search in searches:
            if search.source not in enabled and search.source not in (config.sources or []):
                if search.source not in (
                    "pubmed", "semantic_scholar", "arxiv",
                    "europe_pmc", "openalex", "clinical_trials", "crossref",
                ):
                    continue
            runnable.append(search)
            tasks.append(self._run_one_search(search, per_query_limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        executions: List[QueryExecutionResult] = []
        papers: List[Any] = []

        for search, result in zip(runnable, results):
            if isinstance(result, Exception):
                executions.append(
                    QueryExecutionResult(
                        source=search.source,
                        query=search.query,
                        strategy=search.strategy,
                        papers_found=0,
                        error=str(result)[:200],
                    )
                )
                continue
            exec_result, found = result
            executions.append(exec_result)
            papers.extend(found)

        return executions, papers

    async def _run_one_search(self, search: Any, limit: int):
        async with self._semaphore:
            connector = self._connector_for(search.source)
            if connector is None:
                return QueryExecutionResult(
                    source=search.source,
                    query=search.query,
                    strategy=search.strategy,
                    papers_found=0,
                    error="unknown source",
                ), []

            try:
                papers = await connector.search(search.query, limit)
                for p in papers:
                    raw = p.raw_data or {}
                    raw["retrieval_strategy"] = search.strategy
                    raw["retrieval_query"] = search.query
                    p.raw_data = raw

                if self.progress and papers:
                    self.progress._log_activity_sync(
                        f"{search.source}: +{len(papers)} for [{search.strategy}] \"{search.query[:45]}\""
                    )

                return (
                    QueryExecutionResult(
                        source=search.source,
                        query=search.query,
                        strategy=search.strategy,
                        papers_found=len(papers),
                    ),
                    papers,
                )
            except Exception as exc:
                logger.warning(
                    "Search failed %s/%s: %s", search.source, search.strategy, exc
                )
                return (
                    QueryExecutionResult(
                        source=search.source,
                        query=search.query,
                        strategy=search.strategy,
                        papers_found=0,
                        error=str(exc)[:200],
                    ),
                    [],
                )

    def _connector_for(self, source: str):
        return {
            "pubmed": self.pubmed,
            "semantic_scholar": self.semantic_scholar,
            "arxiv": self.arxiv,
            "europe_pmc": self.europe_pmc,
            "openalex": self.openalex,
            "clinical_trials": self.clinical_trials,
            "crossref": self.crossref,
        }.get(source)

    def _deduplicate(self, papers: List[Any]) -> List[Any]:
        seen_dois: set = set()
        seen_titles: set = set()
        out = []
        for paper in papers:
            if paper.doi and paper.doi.lower() in seen_dois:
                continue
            title_key = (paper.title or "").lower().strip()
            if title_key and title_key in seen_titles:
                continue
            if paper.doi:
                seen_dois.add(paper.doi.lower())
            if title_key:
                seen_titles.add(title_key)
            out.append(paper)
        return out

    def _quality_filter(
        self, papers: List[Any], plan: RetrievalPlan
    ) -> Tuple[List[RejectedPaper], List[Any]]:
        rejected: List[RejectedPaper] = []
        kept: List[Any] = []
        for paper in papers:
            reason = is_obviously_irrelevant(paper, plan)
            if reason:
                rejected.append(
                    RejectedPaper(
                        paper_id=paper.paper_id,
                        title=(paper.title or "")[:200],
                        reason=reason,
                    )
                )
            else:
                kept.append(paper)
        return rejected, kept

    def _assess_coverage(self, papers: List[Any], plan: RetrievalPlan) -> CoverageReport:
        dimensions = plan.intent.coverage_dimensions or []
        if not dimensions:
            return CoverageReport(coverage_score=1.0)

        covered: Dict[str, int] = {}
        for dim in dimensions:
            dim_l = dim.lower()
            count = 0
            for paper in papers:
                text = f"{paper.title} {paper.abstract}".lower()
                if dim_l in text or any(w in text for w in dim_l.split()[:2]):
                    count += 1
            covered[dim] = count

        missing = [d for d, c in covered.items() if c < COVERAGE_MIN_PER_DIMENSION]
        score = 1.0 - (len(missing) / len(dimensions)) if dimensions else 1.0
        return CoverageReport(
            dimensions_covered=covered,
            dimensions_missing=missing,
            coverage_score=round(score, 3),
        )

    async def _rank_candidates(
        self, papers: List[Any], plan: RetrievalPlan, structured_query: dict
    ) -> List[Any]:
        similarities: Dict[str, float] = {}
        if self.embedding_service and papers:
            query_text = structured_query.get("normalized_query", "")
            query_emb = await self.embedding_service.embed_text(query_text, input_type="query")
            if query_emb:
                abstracts = [p.abstract or p.title or "" for p in papers]
                paper_embs = await self.embedding_service.embed_batch(
                    abstracts, input_type="passage"
                )
                from app.services.embeddings import EmbeddingService

                for paper, emb in zip(papers, paper_embs):
                    if emb:
                        similarities[paper.paper_id] = EmbeddingService.cosine_similarity(
                            query_emb, emb
                        )
        return rank_papers(papers, plan, similarities)

    def _confidence_score(
        self,
        candidate_count: int,
        coverage: CoverageReport,
        searches_run: int,
        rejected_count: int,
    ) -> float:
        count_factor = min(1.0, candidate_count / 50.0)
        coverage_factor = coverage.coverage_score if coverage else 0.5
        search_factor = min(1.0, searches_run / 15.0)
        reject_penalty = min(0.2, rejected_count / max(candidate_count + rejected_count, 1) * 0.2)
        return round(
            0.35 * count_factor + 0.40 * coverage_factor + 0.25 * search_factor - reject_penalty,
            3,
        )

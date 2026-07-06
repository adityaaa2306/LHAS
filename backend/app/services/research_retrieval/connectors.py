"""Extended literature API connectors for research retrieval."""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _paper_types():
    from app.services.paper_ingestion import PaperObject, PaperSource
    return PaperObject, PaperSource


class EuropePMCConnector:
    """Europe PMC REST search."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def search(self, query: str, max_results: int = 50) -> List[Any]:
        PaperObject, PaperSource = _paper_types()
        q = (query or "").strip()
        if not q:
            return []

        params = {
            "query": q,
            "format": "json",
            "pageSize": min(max_results, 100),
            "resultType": "core",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Europe PMC search failed for %r: %s", q[:40], exc)
            return []

        papers = []
        for item in data.get("resultList", {}).get("result", []) or []:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            abstract = (item.get("abstractText") or "").strip()
            authors = [
                a.get("fullName", "")
                for a in (item.get("authorList", {}) or {}).get("author", [])
                if a.get("fullName")
            ]
            year = None
            if item.get("pubYear"):
                try:
                    year = int(item["pubYear"])
                except (TypeError, ValueError):
                    pass
            pmid = item.get("pmid") or item.get("id")
            doi = item.get("doi")
            papers.append(
                PaperObject(
                    paper_id=f"epmc_{pmid or doi or title[:40]}",
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    source=PaperSource.PUBMED,
                    doi=doi,
                    url=item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url")
                    if item.get("fullTextUrlList")
                    else f"https://europepmc.org/article/MED/{pmid}" if pmid else None,
                    citations_count=item.get("citedByCount"),
                    raw_data={"retrieval_source": "europe_pmc", "pmid": pmid},
                )
            )
        logger.info("Europe PMC: %d papers for %r", len(papers), q[:50])
        return papers


class OpenAlexConnector:
    """OpenAlex works search — citation graph metadata."""

    BASE_URL = "https://api.openalex.org/works"

    async def search(self, query: str, max_results: int = 50) -> List[Any]:
        PaperObject, PaperSource = _paper_types()
        q = (query or "").strip()
        if not q:
            return []

        params = {
            "search": q,
            "per-page": min(max_results, 100),
            "mailto": "lhas@research.local",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("OpenAlex search failed for %r: %s", q[:40], exc)
            return []

        papers = []
        for item in data.get("results", []) or []:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            abstract = ""
            if item.get("abstract_inverted_index"):
                abstract = self._reconstruct_abstract(item["abstract_inverted_index"])
            year = item.get("publication_year")
            doi = (item.get("doi") or "").replace("https://doi.org/", "") or None
            authors = [
                (a.get("author") or {}).get("display_name", "")
                for a in item.get("authorships", [])
                if (a.get("author") or {}).get("display_name")
            ]
            papers.append(
                PaperObject(
                    paper_id=f"openalex_{item.get('id', '').split('/')[-1]}",
                    title=title,
                    authors=authors,
                    abstract=abstract or "",
                    year=year,
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    doi=doi,
                    url=item.get("id"),
                    citations_count=item.get("cited_by_count"),
                    raw_data={"retrieval_source": "openalex"},
                )
            )
        logger.info("OpenAlex: %d papers for %r", len(papers), q[:50])
        return papers

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        if not inverted_index:
            return ""
        positions = []
        for word, idxs in inverted_index.items():
            for i in idxs:
                positions.append((i, word))
        positions.sort()
        return " ".join(w for _, w in positions)


class ClinicalTrialsConnector:
    """ClinicalTrials.gov API v2."""

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    async def search(self, query: str, max_results: int = 25) -> List[Any]:
        PaperObject, PaperSource = _paper_types()
        q = (query or "").strip()
        if not q:
            return []

        params = {
            "query.term": q,
            "pageSize": min(max_results, 50),
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("ClinicalTrials search failed for %r: %s", q[:40], exc)
            return []

        papers = []
        for study in data.get("studies", []) or []:
            proto = study.get("protocolSection", {}) or {}
            ident = proto.get("identificationModule", {}) or {}
            desc = proto.get("descriptionModule", {}) or {}
            status = proto.get("statusModule", {}) or {}
            nct = ident.get("nctId", "")
            title = ident.get("briefTitle") or ident.get("officialTitle") or ""
            if not title:
                continue
            abstract = desc.get("briefSummary") or desc.get("detailedDescription") or ""
            year = None
            start = status.get("startDateStruct", {}) or {}
            if start.get("date"):
                try:
                    year = int(str(start["date"])[:4])
                except (TypeError, ValueError):
                    pass
            papers.append(
                PaperObject(
                    paper_id=f"ct_{nct}",
                    title=title,
                    authors=[],
                    abstract=abstract,
                    year=year,
                    source=PaperSource.PUBMED,
                    url=f"https://clinicaltrials.gov/study/{nct}" if nct else None,
                    raw_data={
                        "retrieval_source": "clinical_trials",
                        "nct_id": nct,
                        "study_type": "clinical_trial",
                    },
                )
            )
        logger.info("ClinicalTrials.gov: %d studies for %r", len(papers), q[:50])
        return papers


class CrossrefConnector:
    """Crossref metadata search."""

    BASE_URL = "https://api.crossref.org/works"

    async def search(self, query: str, max_results: int = 25) -> List[Any]:
        PaperObject, PaperSource = _paper_types()
        q = (query or "").strip()
        if not q:
            return []

        params = {
            "query": q,
            "rows": min(max_results, 50),
            "mailto": "lhas@research.local",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Crossref search failed for %r: %s", q[:40], exc)
            return []

        papers = []
        for item in data.get("message", {}).get("items", []) or []:
            titles = item.get("title") or []
            title = titles[0] if titles else ""
            if not title:
                continue
            abstract = (item.get("abstract") or "").strip()
            if abstract:
                abstract = re.sub(r"<[^>]+>", "", abstract)
            year = None
            issued = item.get("issued", {}).get("date-parts", [[]])
            if issued and issued[0]:
                try:
                    year = int(issued[0][0])
                except (TypeError, ValueError, IndexError):
                    pass
            doi = item.get("DOI")
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author", [])
            ]
            papers.append(
                PaperObject(
                    paper_id=f"crossref_{doi or title[:30]}",
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    source=PaperSource.SEMANTIC_SCHOLAR,
                    doi=doi,
                    url=f"https://doi.org/{doi}" if doi else None,
                    citations_count=item.get("is-referenced-by-count"),
                    raw_data={"retrieval_source": "crossref"},
                )
            )
        logger.info("Crossref: %d works for %r", len(papers), q[:50])
        return papers

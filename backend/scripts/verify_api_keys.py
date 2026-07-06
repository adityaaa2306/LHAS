"""Verify Semantic Scholar, PubMed, and NVIDIA embedding credentials."""
import asyncio
import sys


async def main() -> int:
    from app.config import settings

    placeholders = {"", "api_key_here", "nvidia_api_key_here", "your_nvidia_api_key_here"}
    results = []

    def ok(name: str, present: bool) -> None:
        results.append((name, "SET" if present else "MISSING"))
        print(f"{name}: {'OK (set)' if present else 'MISSING'}")

    ok("SEMANTIC_SCHOLAR_API_KEY", settings.SEMANTIC_SCHOLAR_API_KEY not in placeholders)
    ok("PUBMED_API_KEY", settings.PUBMED_API_KEY not in placeholders)
    ok("EMBEDDING_MODEL_API_KEY", settings.EMBEDDING_MODEL_API_KEY not in placeholders)
    print(f"EMBEDDING_MODEL_NAME: {settings.EMBEDDING_MODEL_NAME}")

    if settings.SEMANTIC_SCHOLAR_API_KEY in placeholders:
        print("SKIP semantic scholar live test — key missing")
    else:
        from app.services.paper_ingestion import SemanticScholarConnector

        s2 = SemanticScholarConnector(settings.SEMANTIC_SCHOLAR_API_KEY)
        papers = await s2.search("ozempic semaglutide", max_results=5)
        print(f"Semantic Scholar live: OK — {len(papers)} papers")
        if not papers:
            print("WARN: Semantic Scholar returned 0 papers")

    if settings.PUBMED_API_KEY in placeholders:
        print("SKIP pubmed live test — key missing")
    else:
        from app.services.paper_ingestion import PubMedConnector

        pub = PubMedConnector(settings.PUBMED_API_KEY)
        papers = await pub.search("ozempic", max_results=5)
        print(f"PubMed live: OK — {len(papers)} papers")
        if not papers:
            print("WARN: PubMed returned 0 papers")

    if settings.EMBEDDING_MODEL_API_KEY in placeholders:
        print("SKIP embedding live test — key missing")
    else:
        from app.services.embeddings import EmbeddingService

        svc = EmbeddingService()
        if not svc.client:
            print("FAIL: Embedding client not initialized")
            return 1
        vec = await svc.embed_text("ozempic weight loss clinical trial", input_type="query")
        if vec and len(vec) > 0:
            print(f"Embedding live: OK — vector dim {len(vec)}")
        else:
            print("FAIL: Embedding returned empty")
            return 1

    missing = [n for n, s in results if s == "MISSING"]
    if missing:
        print(f"FAILED: missing {', '.join(missing)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""
Web search ingestion script — searches trusted accounting/audit sites and
ingests article content into Qdrant.

Usage (run from backend/ directory):
    python web_ingest.py --query "ISA 315 risk assessment"
    python web_ingest.py --query "PCAOB inspection findings" --max-results 5
    python web_ingest.py --query "audit materiality" --domains sec.gov,pcaobus.org
    python web_ingest.py --query "audit materiality" --clear  # clears prior web-ingested docs first
"""

import argparse
import asyncio
import sys
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from app.config import settings
from app.utils.rag import chunk_text, embed_text
from app.utils.qdrant_service import get_qdrant_service

TRUSTED_DOMAINS = {
    "aicpa-cima.com",
    "pcaobus.org",
    "sec.gov",
    "ifac.org",
    "ifrs.org",
    "iaasb.org",
    "fasb.org",
    "iosco.org",
    "icas.com",
    "icaew.com",
    "ey.com",
    "kpmg.com",
    "pwc.com",
    "deloitte.com",
}

BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
CRAWL_DELAY_SECONDS = 1.0


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


async def search_web(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    if not settings.brave_api_key:
        raise RuntimeError("BRAVE_API_KEY not configured in .env")

    resp = await client.get(
        BRAVE_SEARCH_ENDPOINT,
        headers={"Accept": "application/json", "X-Subscription-Token": settings.brave_api_key},
        params={"q": query, "count": max_results},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Brave Search returned {resp.status_code}: {resp.text[:200]}")

    results = resp.json().get("web", {}).get("results", [])
    return [{"url": r["url"], "title": r.get("title", "")} for r in results]


def filter_trusted(results: list[dict], allowed_domains: set[str]) -> list[dict]:
    return [r for r in results if domain_of(r["url"]) in allowed_domains]


CRAWL_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuditRAGBot/1.0; +https://github.com)"}

_robots_cache: dict[str, RobotFileParser] = {}


async def _get_robots_parser(client: httpx.AsyncClient, url: str) -> RobotFileParser:
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain in _robots_cache:
        return _robots_cache[domain]

    parser = RobotFileParser()
    robots_url = f"{parsed.scheme}://{domain}/robots.txt"
    try:
        resp = await client.get(robots_url, headers=CRAWL_HEADERS, timeout=10.0)
        if resp.status_code == 200:
            parser.parse(resp.text.splitlines())
        else:
            parser.allow_all = True
    except httpx.HTTPError:
        parser.allow_all = True

    _robots_cache[domain] = parser
    return parser


async def is_crawl_allowed(client: httpx.AsyncClient, url: str) -> bool:
    parser = await _get_robots_parser(client, url)
    return parser.can_fetch(CRAWL_HEADERS["User-Agent"], url)


async def crawl_and_extract(client: httpx.AsyncClient, url: str) -> str | None:
    if not await is_crawl_allowed(client, url):
        print(f"  SKIP '{url}' (blocked by robots.txt)")
        return None

    try:
        resp = await client.get(url, follow_redirects=True, headers=CRAWL_HEADERS)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  SKIP '{url}' (fetch failed: {e})")
        return None

    text = trafilatura.extract(resp.text, favor_recall=True)
    if not text or len(text.strip()) < 200:
        print(f"  SKIP '{url}' (no extractable content)")
        return None
    return text.strip()


async def ingest_page(qdrant, client: httpx.AsyncClient, page_num: int, result: dict, ingested_urls: set[str]) -> bool:
    url, title = result["url"], result["title"] or url

    if url in ingested_urls:
        print(f"  [{page_num}] SKIP '{title}' (already ingested)")
        return False

    print(f"  [{page_num}] Crawling '{title}'...", end=" ", flush=True)
    content = await crawl_and_extract(client, url)
    if not content:
        return False

    doc_id = abs(hash(url)) % (10 ** 9)
    chunks = chunk_text(content)

    for chunk_idx, chunk in enumerate(chunks):
        embedding = await embed_text(chunk, client=client)
        await qdrant.upsert_document(
            doc_id=doc_id * 10000 + chunk_idx,
            embedding=embedding,
            metadata={
                "title": title,
                "content": chunk,
                "source": url,
                "metadata": {
                    "domain": domain_of(url),
                    "doc_id": doc_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                },
            },
        )

    print(f"done ({len(chunks)} chunk{'s' if len(chunks) != 1 else ''})")
    return True


async def clear_web_documents(qdrant) -> int:
    """Delete only documents ingested by this script (tagged with metadata.domain),
    leaving Confluence-ingested documents untouched."""
    docs = await qdrant.list_documents()
    web_doc_ids = [d["id"] for d in docs if d.get("metadata", {}).get("domain")]
    for doc_id in web_doc_ids:
        await qdrant.delete_by_doc_id(doc_id)
    return len(web_doc_ids)


async def ingest(query: str, max_results: int, allowed_domains: set[str], clear: bool = False) -> dict:
    qdrant = get_qdrant_service()
    await qdrant.ensure_ready()

    if clear:
        print("Clearing existing web-ingested documents...")
        cleared = await clear_web_documents(qdrant)
        print(f"Cleared {cleared} document(s).\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Searching for '{query}'...")
        results = await search_web(client, query, max_results)
        print(f"Found {len(results)} result(s) — filtering to trusted domains...")

        trusted = filter_trusted(results, allowed_domains)
        print(f"{len(trusted)} result(s) from trusted domains.\n")

        existing_docs = await qdrant.list_documents()
        ingested_urls = {d.get("source") for d in existing_docs if d.get("source")}

        ingested = 0
        skipped = 0
        ingested_titles: list[str] = []
        for i, result in enumerate(trusted, start=1):
            try:
                ok = await ingest_page(qdrant, client, i, result, ingested_urls)
                ingested += ok
                skipped += not ok
                if ok:
                    ingested_titles.append(result["title"] or result["url"])
            except Exception as e:
                print(f"ERROR: {e}")
                skipped += 1
            await asyncio.sleep(CRAWL_DELAY_SECONDS)

    print(f"\nIngestion complete: {ingested} ingested, {skipped} skipped.")
    return {
        "found": len(results),
        "trusted": len(trusted),
        "ingested": ingested,
        "skipped": skipped,
        "ingested_titles": ingested_titles,
    }


def main():
    parser = argparse.ArgumentParser(description="Search and ingest trusted audit/accounting web content")
    parser.add_argument("--query", "-q", required=True, help="Keyword search query")
    parser.add_argument("--max-results", "-n", type=int, default=10, help="Max search results to fetch")
    parser.add_argument("--domains", "-d", help="Comma-separated domain allowlist override")
    parser.add_argument("--clear", "-c", action="store_true",
                        help="Clear existing web-ingested documents before ingesting (leaves Confluence docs untouched)")
    args = parser.parse_args()

    allowed_domains = (
        {d.strip().lower() for d in args.domains.split(",") if d.strip()}
        if args.domains
        else TRUSTED_DOMAINS
    )

    try:
        asyncio.run(ingest(
            query=args.query,
            max_results=args.max_results,
            allowed_domains=allowed_domains,
            clear=args.clear,
        ))
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Confluence ingestion script (uses Confluence Cloud REST API v2).

Usage (run from backend/ directory):
    python ingest.py                        # ingest all spaces
    python ingest.py --space ENG --space HR # ingest specific spaces by key
    python ingest.py --page PAGE_ID         # ingest a specific page by ID or URL
    python ingest.py --clear                # clear all documents first
"""

import asyncio
import argparse
import re
import sys
from base64 import b64encode

import httpx

from app.config import settings
from app.utils.rag import embed_text
from app.utils.qdrant_service import get_qdrant_service


def strip_html(html: str) -> str:
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_auth_headers() -> dict:
    credentials = b64encode(
        f"{settings.confluence_username}:{settings.confluence_api_token}".encode()
    ).decode()
    return {"Authorization": f"Basic {credentials}", "Accept": "application/json"}


async def resolve_space_ids(client: httpx.AsyncClient, base_url: str, headers: dict, space_keys: list[str]) -> list[str]:
    resp = await client.get(
        f"{base_url}/api/v2/spaces",
        headers=headers,
        params={"keys": ",".join(space_keys), "limit": 250},
    )
    if resp.status_code != 200:
        print(f"ERROR: Could not look up spaces: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    spaces = resp.json().get("results", [])
    mapping = {s["key"]: s["id"] for s in spaces}
    for key in space_keys:
        if key not in mapping:
            print(f"WARNING: Space key '{key}' not found — skipping")
    return list(mapping.values())


async def _iter_pages(client: httpx.AsyncClient, base_url: str, headers: dict, space_id: str | None = None):
    """Yield Confluence pages one at a time."""
    params: dict = {"body-format": "storage", "limit": 50}
    if space_id:
        params["space-id"] = space_id
    url: str | None = f"{base_url}/api/v2/pages"
    while url:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"ERROR: Confluence returned {resp.status_code}: {resp.text[:200]}")
            sys.exit(1)
        data = resp.json()
        for page in data.get("results", []):
            yield page
        next_path = data.get("_links", {}).get("next")
        url = (base_url + next_path.replace("/wiki", "", 1)) if next_path else None
        params = {}


async def _ingest_page(qdrant, client: httpx.AsyncClient, page_num: int, page: dict) -> bool:
    title = page.get("title", "Untitled")
    body_html = page.get("body", {}).get("storage", {}).get("value", "")
    page_id = str(page.get("id", ""))
    space_id = str(page.get("spaceId", ""))
    webui = page.get("_links", {}).get("webui", f"/pages/{page_id}")
    source_url = f"{settings.confluence_base_url.rstrip('/')}{webui}"

    content = strip_html(body_html)
    del body_html

    if not content:
        print(f"  [{page_num}] SKIP '{title}' (empty)")
        return False

    print(f"  [{page_num}] Ingesting '{title}' ({len(content):,} chars)...", end=" ", flush=True)

    doc_id = int(page_id)
    step = 1300
    chunks = [content[i:i+1500].strip() for i in range(0, len(content), step) if content[i:i+1500].strip()]
    del content

    for chunk_idx, chunk in enumerate(chunks):
        embedding = await embed_text(chunk, client=client)
        await qdrant.upsert_document(
            doc_id=doc_id * 10000 + chunk_idx,
            embedding=embedding,
            metadata={
                "title": title,
                "content": chunk,
                "source": source_url,
                "metadata": {
                    "confluence_id": page_id,
                    "space_id": space_id,
                    "doc_id": doc_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                },
            },
        )

    print(f"done ({len(chunks)} chunk{'s' if len(chunks) != 1 else ''})")
    return True


async def ingest(space_keys: list[str] | None = None, page_ids: list[str] | None = None, clear: bool = False):
    if not all([settings.confluence_base_url, settings.confluence_username, settings.confluence_api_token]):
        print("ERROR: Confluence credentials not configured in .env")
        sys.exit(1)

    base_url = settings.confluence_base_url.rstrip("/")
    headers = make_auth_headers()
    qdrant = get_qdrant_service()
    await qdrant.ensure_ready()

    if clear:
        print("Clearing existing documents...")
        await qdrant.clear_collection()
        print("Cleared.")

    ingested = 0
    skipped = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        if page_ids:
            async def _source():
                for pid in page_ids:
                    resp = await client.get(
                        f"{base_url}/api/v2/pages/{pid}",
                        headers=headers,
                        params={"body-format": "storage"},
                    )
                    if resp.status_code != 200:
                        print(f"ERROR: Page {pid} returned {resp.status_code}: {resp.text[:200]}")
                        return
                    yield resp.json()
        else:
            if space_keys:
                space_ids = await resolve_space_ids(client, base_url, headers, space_keys)
                if not space_ids:
                    print("No valid spaces found — nothing to ingest.")
                    return
            else:
                space_ids = [None]

            async def _source():
                for space_id in space_ids:
                    label = f"space {space_id}" if space_id else "all spaces"
                    print(f"Fetching pages from {label}...")
                    async for page in _iter_pages(client, base_url, headers, space_id):
                        yield page

        page_num = 0
        async for page in _source():
            page_num += 1
            try:
                ok = await _ingest_page(qdrant, client, page_num, page)
                ingested += ok
                skipped += not ok
            except Exception as e:
                print(f"ERROR: {e}")
                skipped += 1

    print(f"\nIngestion complete: {ingested} ingested, {skipped} skipped.")


def main():
    parser = argparse.ArgumentParser(description="Ingest Confluence pages into the RAG system")
    parser.add_argument("--space", "-s", action="append", dest="spaces", metavar="SPACE_KEY",
                        help="Space key to ingest (repeatable). Omit for all spaces.")
    parser.add_argument("--page", "-p", action="append", dest="pages", metavar="PAGE_ID_OR_URL",
                        help="Specific page ID or full API URL (repeatable).")
    parser.add_argument("--clear", "-c", action="store_true",
                        help="Clear all existing documents before ingesting.")
    args = parser.parse_args()

    page_ids = None
    if args.pages:
        page_ids = [
            re.search(r"/pages/(\d+)", p).group(1) if "/pages/" in p else p
            for p in args.pages
        ]

    asyncio.run(ingest(space_keys=args.spaces, page_ids=page_ids, clear=args.clear))


if __name__ == "__main__":
    main()

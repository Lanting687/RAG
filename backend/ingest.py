"""
Confluence ingestion script (uses Confluence Cloud REST API v2).

Usage (run from backend/ directory):
    python ingest.py                        # ingest all spaces
    python ingest.py --space ENG --space HR # ingest specific spaces by key
    python ingest.py --clear                # clear existing docs first

API reference:
    GET /wiki/api/v2/pa
    ges?body-format=storage&limit=50
    GET /wiki/api/v2/spaces?keys=ENG,HR
"""

import asyncio
import argparse
import re
import sys
from base64 import b64encode

import httpx

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app import crud
from app.utils.rag import embed_text
from app.utils.qdrant_service import get_qdrant_service

def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def make_auth_headers() -> dict:
    credentials = b64encode(
        f"{settings.confluence_username}:{settings.confluence_api_token}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

async def resolve_space_ids(client: httpx.AsyncClient, base_url: str, headers: dict, space_keys: list[str]) -> dict[str, str]:
    """Convert space keys to space IDs using the v2 spaces endpoint."""
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
            print(f"WARNING: Space key '{key}' not found in Confluence — skipping")

    return mapping  # { "ENG": "98306", ... }

async def fetch_single_page(page_id: str) -> list[dict]:
    """Fetch a single Confluence page by ID using the v2 API."""
    base_url = settings.confluence_base_url.rstrip("/")
    headers = make_auth_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{base_url}/api/v2/pages/{page_id}",
            headers=headers,
            params={"body-format": "storage"},
        )
        if resp.status_code != 200:
            print(f"ERROR: Confluence returned {resp.status_code}: {resp.text[:200]}")
            return []
        return [resp.json()]

async def fetch_pages(space_keys: list[str] | None = None) -> list[dict]:
    """Fetch pages from Confluence using API v2 with cursor-based pagination."""
    if not all([settings.confluence_base_url, settings.confluence_username, settings.confluence_api_token]):
        print("ERROR: Confluence credentials not configured in .env")
        sys.exit(1)

    base_url = settings.confluence_base_url.rstrip("/")
    headers = make_auth_headers()
    all_pages: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Resolve space keys → space IDs if filtering requested
        space_ids: list[str] = []
        if space_keys:
            mapping = await resolve_space_ids(client, base_url, headers, space_keys)
            space_ids = list(mapping.values())
            if not space_ids:
                print("No valid spaces found — nothing to ingest.")
                return []

        # Build initial request params
        params: dict = {
            "body-format": "storage",
            "limit": 50,
        }
        if space_ids:
            # v2 accepts repeated space-id params; pass as comma-separated isn't supported,
            # so we fetch each space separately when multiple are given
            pass  # handled below

        fetch_groups = space_ids if space_ids else [None]

        for space_id in fetch_groups:
            group_params = dict(params)
            if space_id:
                group_params["space-id"] = space_id

            url: str | None = f"{base_url}/api/v2/pages"
            group_label = f"space-id={space_id}" if space_id else "all spaces"
            print(f"Fetching pages from {group_label}...")

            while url:
                resp = await client.get(url, headers=headers, params=group_params)
                if resp.status_code != 200:
                    print(f"ERROR: Confluence returned {resp.status_code}: {resp.text[:200]}")
                    sys.exit(1)

                data = resp.json()
                results = data.get("results", [])
                all_pages.extend(results)
                print(f"  {len(all_pages)} pages fetched so far...")

                # v2 cursor pagination: follow _links.next if present
                next_path = data.get("_links", {}).get("next")
                if next_path:
                    # next_path is relative, e.g. /wiki/api/v2/pages?cursor=xxx&...
                    # Strip leading /wiki since base_url already ends with /wiki
                    url = base_url + next_path.replace("/wiki", "", 1)
                    group_params = {}  # cursor URL already contains all params
                else:
                    url = None

    print(f"Total pages fetched: {len(all_pages)}")
    return all_pages

async def ingest(space_keys: list[str] | None = None, page_ids: list[str] | None = None, clear: bool = False):
    await init_db()

    async with AsyncSessionLocal() as session:
        if clear:
            print("Clearing existing documents...")
            await crud.clear_documents(session)
            get_qdrant_service().clear_collection()
            print("Cleared.")

        if page_ids:
            pages = []
            for pid in page_ids:
                pages.extend(await fetch_single_page(pid))
        else:
            pages = await fetch_pages(space_keys)
        if not pages:
            print("No pages found.")
            return

        print(f"\nFound {len(pages)} pages. Starting ingestion...\n")
        qdrant = get_qdrant_service()
        ingested = 0
        skipped = 0

        for i, page in enumerate(pages, 1):
            title = page.get("title", "Untitled")
            # v2 body path: page["body"]["storage"]["value"]
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            content = strip_html(body_html)
            page_id = str(page.get("id", ""))
            space_id = str(page.get("spaceId", ""))
            # v2 provides a webui link; fall back to constructing the URL
            webui = page.get("_links", {}).get("webui", f"/pages/{page_id}")
            source_url = f"{settings.confluence_base_url.rstrip('/')}{webui}"

            if not content:
                print(f"  [{i}/{len(pages)}] SKIP '{title}' (empty content)")
                skipped += 1
                continue

            print(f"  [{i}/{len(pages)}] Ingesting '{title}'...", end=" ", flush=True)

            try:
                db_doc = await crud.create_document(
                    session,
                    title=title,
                    content=content,
                    source=source_url,
                    metadata={"confluence_id": page_id, "space_id": space_id},
                )
                embedding = await embed_text(content)
                qdrant.upsert_document(
                    doc_id=db_doc.id,
                    embedding=embedding,
                    metadata={
                        "title": title,
                        "content": content,
                        "metadata": db_doc.metadata_json or {},
                    },
                )
                print("done")
                ingested += 1
            except Exception as e:
                print(f"ERROR: {e}")
                skipped += 1

    print(f"\nIngestion complete: {ingested} ingested, {skipped} skipped.")

def main():
    parser = argparse.ArgumentParser(description="Ingest Confluence pages into the RAG system")
    parser.add_argument(
        "--space", "-s",
        action="append",
        dest="spaces",
        metavar="SPACE_KEY",
        help="Confluence space key to ingest (can repeat for multiple spaces). Omit to ingest all spaces.",
    )
    parser.add_argument(
        "--page", "-p",
        action="append",
        dest="pages",
        metavar="PAGE_ID_OR_URL",
        help="Ingest a specific page by ID or full API URL (can repeat). "
             "E.g. --page 66076 or --page https://…/api/v2/pages/66076?…",
    )
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear all existing documents before ingesting",
    )
    args = parser.parse_args()

    # Accept full URLs like https://…/api/v2/pages/66076?body-format=storage
    page_ids = None
    if args.pages:
        import re as _re
        page_ids = [
            _re.search(r"/pages/(\d+)", p).group(1) if "/pages/" in p else p
            for p in args.pages
        ]

    asyncio.run(ingest(space_keys=args.spaces, page_ids=page_ids, clear=args.clear))

if __name__ == "__main__":
    main()
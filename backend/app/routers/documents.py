from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app import crud
from app.config import settings
from app.schemas import DocumentCreate, DocumentReadFull
from app.utils.rag import embed_text
from app.utils.qdrant_service import get_qdrant_service
import httpx
from base64 import b64encode

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=List[DocumentReadFull])
async def list_documents(session: AsyncSession = Depends(get_session)):
    docs = await crud.get_all_documents(session)
    return [
        DocumentReadFull(
            id=d.id,
            title=d.title,
            content=d.content,
            source=d.source,
            metadata=d.metadata_json,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.post("/", response_model=DocumentReadFull)
async def create_document(doc: DocumentCreate, session: AsyncSession = Depends(get_session)):
    db_doc = await crud.create_document(
        session,
        title=doc.title,
        content=doc.content,
        source=doc.source,
        metadata=doc.metadata or {},
    )
    embedding = await embed_text(doc.content)
    qdrant_service = get_qdrant_service()
    qdrant_service.upsert_document(
        doc_id=db_doc.id,
        embedding=embedding,
        metadata={"title": db_doc.title, "content": db_doc.content, "metadata": db_doc.metadata_json or {}},
    )
    return DocumentReadFull(
        id=db_doc.id,
        title=db_doc.title,
        content=db_doc.content,
        source=db_doc.source,
        metadata=db_doc.metadata_json,
        created_at=db_doc.created_at,
    )


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    await crud.delete_document(session, doc_id)
    qdrant_service = get_qdrant_service()
    qdrant_service.delete_document(doc_id)
    return {"message": f"Document {doc_id} deleted"}


@router.delete("/")
async def clear_documents(session: AsyncSession = Depends(get_session)):
    await crud.clear_documents(session)
    qdrant_service = get_qdrant_service()
    qdrant_service.clear_collection()
    return {"message": "All documents cleared"}


@router.post("/ingest/confluence")
async def ingest_confluence(session: AsyncSession = Depends(get_session)):
    """Fetch pages from Confluence and ingest them into the RAG system."""
    if not all([settings.confluence_base_url, settings.confluence_username, settings.confluence_api_token]):
        raise HTTPException(status_code=400, detail="Confluence credentials not configured in .env")

    base_url = settings.confluence_base_url.rstrip("/")
    credentials = b64encode(
        f"{settings.confluence_username}:{settings.confluence_api_token}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

    pages = []
    start = 0
    limit = 50
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            resp = await client.get(
                f"{base_url}/rest/api/content",
                headers=headers,
                params={"type": "page", "start": start, "limit": limit, "expand": "body.storage"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Confluence returned {resp.status_code}: {resp.text}")
            data = resp.json()
            results = data.get("results", [])
            pages.extend(results)
            if len(results) < limit:
                break
            start += limit

    if not pages:
        return {"message": "No pages found in Confluence", "ingested": 0}

    ingested = 0
    qdrant_service = get_qdrant_service()
    for page in pages:
        title = page.get("title", "Untitled")
        body_html = page.get("body", {}).get("storage", {}).get("value", "")
        # Strip HTML tags for plain text
        import re
        content = re.sub(r"<[^>]+>", " ", body_html).strip()
        content = re.sub(r"\s+", " ", content)
        if not content:
            continue

        source_url = f"{base_url}/pages/{page.get('id', '')}"
        db_doc = await crud.create_document(
            session,
            title=title,
            content=content,
            source=source_url,
            metadata={"confluence_id": page.get("id"), "space": page.get("space", {}).get("key", "")},
        )
        embedding = await embed_text(content)
        qdrant_service.upsert_document(
            doc_id=db_doc.id,
            embedding=embedding,
            metadata={"title": title, "content": content, "metadata": db_doc.metadata_json or {}},
        )
        ingested += 1

    return {"message": f"Ingested {ingested} pages from Confluence", "ingested": ingested}

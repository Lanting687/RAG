import hashlib
from typing import List
from fastapi import APIRouter, HTTPException
from app.schemas import DocumentCreate, DocumentReadFull
from app.utils.rag import embed_text, chunk_text
from app.utils.qdrant_service import get_qdrant_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=List[DocumentReadFull])
async def list_documents():
    docs = await get_qdrant_service().list_documents()
    return [
        DocumentReadFull(
            id=d["id"],
            title=d["title"],
            content=d["content"],
            source=d.get("source"),
            metadata=d.get("metadata"),
        )
        for d in docs
    ]


@router.post("/", response_model=DocumentReadFull)
async def create_document(doc: DocumentCreate):
    qdrant = get_qdrant_service()
    doc_id = int(hashlib.md5(f"{doc.title}{doc.content}".encode()).hexdigest(), 16) % (10 ** 9)
    chunks = chunk_text(doc.content)
    for chunk_idx, chunk in enumerate(chunks):
        embedding = await embed_text(chunk)
        await qdrant.upsert_document(
            doc_id=doc_id * 10000 + chunk_idx,
            embedding=embedding,
            metadata={
                "title": doc.title,
                "content": chunk,
                "source": doc.source,
                "metadata": {
                    **(doc.metadata or {}),
                    "doc_id": doc_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                },
            },
        )
    return DocumentReadFull(id=doc_id, title=doc.title, content=doc.content, source=doc.source, metadata=doc.metadata)


@router.delete("/", status_code=200)
async def clear_documents():
    await get_qdrant_service().clear_collection()
    return {"message": "All documents cleared"}


@router.delete("/{doc_id}", status_code=200)
async def delete_document(doc_id: int):
    await get_qdrant_service().delete_by_doc_id(doc_id)
    return {"message": f"Document {doc_id} deleted"}

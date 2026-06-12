from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas import ChatRequest, ChatResponse, DocumentRead
from app.utils.rag import retrieve_relevant_documents, ask_gemini

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, session: AsyncSession = Depends(get_session)):
    try:
        relevant = await retrieve_relevant_documents(request.question, top_k=4)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vector search failed: {str(e)}") from e
    
    if not relevant:
        raise HTTPException(status_code=404, detail="No knowledge documents available. Ingest documents first.")

    try:
        snippets = [f"Title: {doc.title}\nContent: {doc.content}" for doc in relevant]
        answer = await ask_gemini(request.question, snippets)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        answer=answer,
        sources=[DocumentRead(
            id=doc.id,
            title=doc.title,
            content=doc.content,
            metadata=doc.metadata_json,
        ) for doc in relevant],
    )

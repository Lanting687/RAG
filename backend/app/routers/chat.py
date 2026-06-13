from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import ChatRequest, ChatResponse, DocumentRead
from app.utils.rag import retrieve_relevant_documents, ask_gemini

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),):
    # 1. Validate input
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    # 2. Retrieve relevant documents
    try:
        relevant = await retrieve_relevant_documents(
            request.question,
            top_k=8
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Vector search failed: {str(exc)}"
        )

    # 3. No relevant documents found
    if not relevant:
        return ChatResponse(
            answer=(
                "I couldn't find any relevant information in the audit "
                "knowledge base for this question. "
                "Please ask an audit-related question or upload additional documents."
            ),
            sources=[]
        )

    # 4. Generate answer with Gemini
    try:
        snippets = [
            f"Title: {doc.title}\nContent: {doc.content}"
            for doc in relevant
        ]

        answer = await ask_gemini(
            request.question,
            snippets
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM request failed: {str(exc)}"
        )

    # 5. Return answer + sources
    return ChatResponse(
        answer=answer,
        sources=[
            DocumentRead(
                id=doc.id,
                title=doc.title,
                content=doc.content,
                metadata=doc.metadata_json,
            )
            for doc in relevant
        ],
    )
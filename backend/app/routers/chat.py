import logging
from fastapi import APIRouter, HTTPException
from app.schemas import ChatRequest, ChatResponse, DocumentRead
from app.utils.rag import retrieve_relevant_documents, ask_gemini, ask_gemini_with_grounding, is_audit_related

logger = logging.getLogger(__name__)
router = APIRouter()

CONFIDENCE_THRESHOLD = 0.65
NON_AUDIT_RESPONSE = "Please ask audit-related questions only."


def _is_confident(docs) -> bool:
    return bool(docs) and max(doc.score for doc in docs) >= CONFIDENCE_THRESHOLD


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    logger.info("Question received: %r", request.question)

    if not await is_audit_related(request.question):
        logger.info("Rejected as non-audit-related")
        return ChatResponse(answer=NON_AUDIT_RESPONSE, sources=[])

    try:
        relevant = await retrieve_relevant_documents(request.question, top_k=8)
    except Exception as exc:
        logger.error("Vector search failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Vector search failed: {exc}")

    top_score = max((doc.score for doc in relevant), default=0.0)
    logger.info("Retrieved %d docs, top score=%.3f", len(relevant), top_score)

    if _is_confident(relevant):
        logger.info("Confidence threshold met — answering from Qdrant context")
        try:
            snippets = [f"Title: {doc.title}\nContent: {doc.content}" for doc in relevant]
            answer = await ask_gemini(request.question, snippets)
        except RuntimeError as exc:
            logger.error("Gemini chat failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

        return ChatResponse(
            answer=answer,
            sources=[
                DocumentRead(id=doc.id, title=doc.title, content=doc.content, metadata=doc.metadata_json)
                for doc in relevant
            ],
        )

    logger.info("Confidence threshold not met — falling back to Gemini web grounding")
    try:
        answer = await ask_gemini_with_grounding(request.question)
    except RuntimeError as exc:
        logger.error("Gemini grounding failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

    return ChatResponse(answer=answer, sources=[])

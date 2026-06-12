import asyncio
from typing import List
import httpx
from app.config import settings
from app.utils.qdrant_service import get_qdrant_service


def _build_headers(endpoint: str) -> dict:
    endpoint_str = str(endpoint)
    headers = {"Content-Type": "application/json"}
    if "?key=" not in endpoint_str:
        headers["Authorization"] = f"Bearer {settings.gemini_api_key}"
    return headers


def _validate_endpoint(endpoint: str, service_name: str) -> None:
    if "example.com" in endpoint or "YOUR_API_KEY" in endpoint:
        raise RuntimeError(
            f"{service_name} endpoint is not configured. "
            "Update .env with a valid GEMINI_API_KEY and endpoint URL."
        )


async def embed_text(text: str) -> List[float]:
    endpoint = str(settings.gemini_embeddings_endpoint)
    _validate_endpoint(endpoint, "Embeddings")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                endpoint,
                headers=_build_headers(endpoint),
                json={"content": {"parts": [{"text": text}]}},
            )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise RuntimeError(f"Embedding service request failed: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Embedding service returned {exc.response.status_code}: {exc.response.text}") from exc

        data = response.json()
        # Handle embedContent response format
        if "embedding" in data:
            return data["embedding"].get("values", [])
        raise ValueError("Unable to parse embedding response")

async def retrieve_relevant_documents(query: str, top_k: int = 4):
    """Retrieve relevant documents using Qdrant vector search."""
    query_embedding = await embed_text(query)
    qdrant_service = get_qdrant_service()
    
    # Search using Qdrant
    results = qdrant_service.search(query_embedding, top_k=top_k)
    
    # Convert results back to document-like objects
    # Create a simple object that mimics the Document model
    class DocumentResult:
        def __init__(self, result_dict):
            self.id = result_dict["id"]
            self.title = result_dict["title"]
            self.content = result_dict["content"]
            self.metadata_json = result_dict["metadata"]
            self.embedding = result_dict["embedding"] if "embedding" in result_dict else None
            self.score = result_dict.get("score", 0.0)
    
    # Convert results to document-like objects
    retrieved_docs = []
    for result in results:
        doc = DocumentResult(result)
        retrieved_docs.append(doc)
    
    return retrieved_docs

def build_system_prompt() -> str:
    return (
        "You are an audit assistant for Big 4 accountancy firms. "
        "Answer questions using only the provided audit knowledge documents. "
        "When applicable, reference the source documents by title."
    )


async def ask_gemini(question: str, snippets: List[str]) -> str:
    """Ask Gemini with retry/backoff and fallback model endpoints.

    Tries the configured endpoint first; on 503/429 it will retry a few times
    and then attempt any fallback models configured in `GEMINI_CHAT_FALLBACK_MODELS`.
    """
    context = "\n\n".join(snippets)
    prompt_text = (
        f"{build_system_prompt()}\n\n"
        f"Audit knowledge context:\n{context}\n\n"
        f"Question: {question}\nAnswer:"
    )

    chat_payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt_text}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800,
        }
    }

    # Build list of candidate endpoints (primary + fallbacks)
    primary_endpoint = str(settings.gemini_chat_endpoint)
    _validate_endpoint(primary_endpoint, "Chat")

    def _replace_model_in_endpoint(endpoint: str, model: str) -> str:
        if "/models/" not in endpoint:
            raise RuntimeError(
                f"Cannot substitute model in endpoint '{endpoint}': no '/models/' segment found."
            )
        prefix = endpoint.split("/models/")[0]
        rest = endpoint.split("/models/")[1]
        if ":" not in rest:
            raise RuntimeError(
                f"Cannot substitute model in endpoint '{endpoint}': expected '<model>:<action>' after /models/."
            )
        suffix = rest.split(":", 1)[1]
        return f"{prefix}/models/{model}:{suffix}"

    candidate_models: List[str] = []
    # Try to extract current model from the primary endpoint
    try:
        rest = primary_endpoint.split("/models/")[1]
        current_model = rest.split(":", 1)[0]
        candidate_models.append(current_model)
    except Exception:
        # fallback to default
        candidate_models.append("gemini-2.5-flash")

    if settings.gemini_chat_fallback_models:
        for m in str(settings.gemini_chat_fallback_models).split(','):
            m = m.strip()
            if m and m not in candidate_models:
                candidate_models.append(m)

    # Default extra fallbacks if none configured
    for default_m in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"]:
        if default_m not in candidate_models:
            candidate_models.append(default_m)

    retry_attempts = 3
    base_backoff = 1.0

    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in candidate_models:
            endpoint = _replace_model_in_endpoint(primary_endpoint, model)
            for attempt in range(1, retry_attempts + 1):
                try:
                    response = await client.post(
                        endpoint,
                        headers=_build_headers(endpoint),
                        json=chat_payload,
                    )
                    if response.status_code in (503, 429):
                        # temporary, retry with backoff
                        wait = base_backoff * (2 ** (attempt - 1))
                        await asyncio.sleep(wait)
                        continue
                    response.raise_for_status()
                    content = response.json()

                    # Handle Gemini API v1beta response format
                    if "candidates" in content and content["candidates"]:
                        candidate = content["candidates"][0]
                        if "content" in candidate and "parts" in candidate["content"]:
                            parts = candidate["content"]["parts"]
                            if parts and "text" in parts[0]:
                                return parts[0]["text"]

                    # If no expected fields, return empty string
                    return ""

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    # Retry on 503/429, otherwise break and try next model
                    if status in (503, 429):
                        wait = base_backoff * (2 ** (attempt - 1))
                        await asyncio.sleep(wait)
                        continue
                    # Non-retryable status: break to try next model
                    break
                except httpx.RequestError:
                    # network error - retry a few times
                    wait = base_backoff * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)
                    continue

    raise RuntimeError("All Gemini chat endpoints failed or returned no content")

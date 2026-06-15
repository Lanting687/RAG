import asyncio
from typing import List
import httpx
from app.config import settings
from app.utils.qdrant_service import get_qdrant_service


def _build_headers(endpoint: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if "?key=" not in str(endpoint):
        headers["Authorization"] = f"Bearer {settings.gemini_api_key}"
    return headers


def _validate_endpoint(endpoint: str, service_name: str) -> None:
    if "example.com" in endpoint or "YOUR_API_KEY" in endpoint:
        raise RuntimeError(f"{service_name} endpoint is not configured.")


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    step = chunk_size - overlap
    return [text[i:i + chunk_size].strip() for i in range(0, len(text), step) if text[i:i + chunk_size].strip()]


async def embed_text(text: str, client: httpx.AsyncClient | None = None) -> List[float]:
    endpoint = str(settings.gemini_embeddings_endpoint)
    _validate_endpoint(endpoint, "Embeddings")

    async def _do_request(c: httpx.AsyncClient) -> List[float]:
        try:
            response = await c.post(
                endpoint,
                headers=_build_headers(endpoint),
                json={"content": {"parts": [{"text": text}]}},
            )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise RuntimeError(f"Embedding request failed: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Embedding service returned {exc.response.status_code}: {exc.response.text}") from exc

        data = response.json()
        if "embedding" in data:
            return data["embedding"].get("values", [])
        raise ValueError("Unable to parse embedding response")

    if client is not None:
        return await _do_request(client)
    async with httpx.AsyncClient(timeout=30.0) as owned_client:
        return await _do_request(owned_client)


async def retrieve_relevant_documents(query: str, top_k: int = 4):
    query_embedding = await embed_text(query)
    results = await get_qdrant_service().search(query_embedding, top_k=top_k)

    class Doc:
        def __init__(self, r):
            self.id = r["id"]
            self.title = r["title"]
            self.content = r["content"]
            self.metadata_json = r["metadata"]
            self.score = r.get("score", 0.0)

    return [Doc(r) for r in results]


def build_system_prompt() -> str:
    return (
        "You are a senior audit advisor at a Big 4 accountancy firm with deep expertise in auditing standards, "
        "risk assessment, and regulatory compliance. "
        "Your role is to reason through audit questions and give clear, expert guidance — not to quote documents verbatim. "
        "Use the provided knowledge context as your evidence base, but synthesize it into a direct, intelligent answer. "
        "Explain the 'why' behind requirements, highlight practical implications, and connect related concepts where relevant. "
        "Cite source document titles to support your points, but lead with your own analysis."
    )


async def ask_gemini(question: str, snippets: List[str]) -> str:
    context = "\n\n".join(snippets)
    prompt_text = (
        f"{build_system_prompt()}\n\n"
        "--- AUDIT KNOWLEDGE CONTEXT ---\n"
        f"{context}\n"
        "--- END CONTEXT ---\n\n"
        f"Question: {question}\n\n"
        "Instructions:\n"
        "- Answer the question directly and concisely first, then elaborate.\n"
        "- Synthesize and interpret the context — do not copy it verbatim.\n"
        "- Explain the reasoning or rationale behind key requirements.\n"
        "- If there are practical considerations or common pitfalls, mention them.\n"
        "- Use bullet points only where they add clarity, not as a default format.\n"
        "- If the context does not contain enough information to answer confidently, say so.\n\n"
        "Answer:"
    )

    chat_payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 8192},
    }

    primary_endpoint = str(settings.gemini_chat_endpoint)
    _validate_endpoint(primary_endpoint, "Chat")

    def _replace_model(endpoint: str, model: str) -> str:
        prefix = endpoint.split("/models/")[0]
        suffix = endpoint.split("/models/")[1].split(":", 1)[1]
        return f"{prefix}/models/{model}:{suffix}"

    candidate_models: List[str] = []
    try:
        candidate_models.append(primary_endpoint.split("/models/")[1].split(":", 1)[0])
    except Exception:
        candidate_models.append("gemini-2.5-flash")

    if settings.gemini_chat_fallback_models:
        for m in str(settings.gemini_chat_fallback_models).split(","):
            m = m.strip()
            if m and m not in candidate_models:
                candidate_models.append(m)

    for default_m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-pro"]:
        if default_m not in candidate_models:
            candidate_models.append(default_m)

    errors: list[str] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for model in candidate_models:
            try:
                endpoint = _replace_model(primary_endpoint, model)
            except Exception as exc:
                errors.append(f"{model}: could not build URL ({exc})")
                continue
            safe_url = endpoint.split("?key=")[0] if "?key=" in endpoint else endpoint
            for attempt in range(1, 4):
                try:
                    response = await client.post(endpoint, headers=_build_headers(endpoint), json=chat_payload)
                    if response.status_code in (503, 429):
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue
                    response.raise_for_status()
                    content = response.json()
                    if "candidates" in content and content["candidates"]:
                        parts = content["candidates"][0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"]
                    errors.append(f"{model}: empty response from {safe_url}")
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (503, 429):
                        await asyncio.sleep(2 ** (attempt - 1))
                        continue
                    errors.append(f"{model}: HTTP {exc.response.status_code} ({safe_url})")
                    break
                except httpx.RequestError as exc:
                    errors.append(f"{model}: {exc}")
                    await asyncio.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"All Gemini endpoints failed: {'; '.join(errors)}")

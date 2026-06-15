"""Qdrant client using direct HTTP calls — no qdrant-client library."""
from typing import List
import httpx
from app.config import settings


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if settings.qdrant_api_key:
        h["api-key"] = settings.qdrant_api_key
    return h


class QdrantService:
    def __init__(self):
        self.base = settings.qdrant_url.rstrip("/")
        self.collection = settings.qdrant_collection_name
        self.vector_size: int | None = None

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{self.base}{path}", headers=_headers())
            r.raise_for_status()
            return r.json()

    async def _put(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.put(f"{self.base}{path}", headers=_headers(), json=body)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{self.base}{path}", headers=_headers(), json=body)
            r.raise_for_status()
            return r.json()

    async def _delete(self, path: str, body: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.request("DELETE", f"{self.base}{path}", headers=_headers(), json=body)
            r.raise_for_status()
            return r.json()

    async def ensure_ready(self):
        try:
            data = await self._get(f"/collections/{self.collection}")
            self.vector_size = data["result"]["config"]["params"]["vectors"]["size"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise

    async def _ensure_collection(self, dim: int):
        if self.vector_size is not None:
            return
        try:
            await self._put(f"/collections/{self.collection}",
                            {"vectors": {"size": dim, "distance": "Cosine"}})
            self.vector_size = dim
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                data = await self._get(f"/collections/{self.collection}")
                self.vector_size = data["result"]["config"]["params"]["vectors"]["size"]
            else:
                raise

    async def upsert_document(self, doc_id: int, embedding: List[float], metadata: dict):
        await self._ensure_collection(len(embedding))
        await self._put(f"/collections/{self.collection}/points",
                        {"points": [{"id": doc_id, "vector": embedding, "payload": metadata}]})

    async def search(self, embedding: List[float], top_k: int = 4) -> List[dict]:
        try:
            data = await self._post(f"/collections/{self.collection}/points/query", {
                "query": embedding,
                "limit": top_k,
                "score_threshold": 0.5,
                "with_payload": True,
            })
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        return [
            {
                "id": r["id"],
                "score": r["score"],
                "title": r["payload"].get("title", ""),
                "content": r["payload"].get("content", ""),
                "metadata": r["payload"].get("metadata", {}),
            }
            for r in data.get("result", {}).get("points", [])
        ]

    async def list_documents(self) -> List[dict]:
        results = []
        offset = None
        while True:
            body: dict = {
                "filter": {"must": [{"key": "metadata.chunk_index", "match": {"value": 0}}]},
                "limit": 100,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            data = await self._post(f"/collections/{self.collection}/points/scroll", body)
            result = data.get("result", {})
            for p in result.get("points", []):
                meta = p["payload"].get("metadata", {})
                results.append({
                    "id": meta.get("doc_id", p["id"]),
                    "title": p["payload"].get("title", ""),
                    "content": p["payload"].get("content", ""),
                    "source": p["payload"].get("source"),
                    "metadata": meta,
                })
            offset = result.get("next_page_offset")
            if offset is None:
                break
        return results

    async def delete_by_doc_id(self, doc_id: int):
        await self._post(f"/collections/{self.collection}/points/delete",
                         {"filter": {"must": [{"key": "metadata.doc_id", "match": {"value": doc_id}}]}})

    async def clear_collection(self):
        try:
            await self._delete(f"/collections/{self.collection}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
        self.vector_size = None


_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service

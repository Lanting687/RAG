"""Qdrant vector database service for semantic search."""
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.config import settings


class QdrantService:
    """Service for managing vector storage and retrieval using Qdrant."""

    def __init__(self):
        """Initialize Qdrant client."""
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key
        )
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = None  # Will be set on first upsert
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        collection_names = [col.name for col in collections]

        if self.collection_name not in collection_names:
            self.collection_exists = False
        else:
            self.collection_exists = True
            collection_info = self.client.get_collection(self.collection_name)
            if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params'):
                self.vector_size = collection_info.config.params.vectors.size

    def _create_collection_if_needed(self, embedding_dim: int):
        """Create collection with the correct embedding dimension."""
        if not self.collection_exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
            )
            self.collection_exists = True
            self.vector_size = embedding_dim
            print(f"✓ Created Qdrant collection with {embedding_dim}-dim embeddings")

    def upsert_document(self, doc_id: int, embedding: List[float], metadata: dict):
        """Insert or update a document vector with metadata."""
        embedding_dim = len(embedding) if isinstance(embedding, list) else 0

        if embedding_dim == 0:
            raise ValueError("Invalid embedding: empty or not a list")

        self._create_collection_if_needed(embedding_dim)

        if self.vector_size and embedding_dim != self.vector_size:
            raise ValueError(f"Embedding dimension mismatch: expected {self.vector_size}, got {embedding_dim}")

        point = PointStruct(
            id=doc_id,
            vector=embedding,
            payload=metadata
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

    def upsert_documents(self, documents: List[dict]):
        """Batch insert or update document vectors.

        Args:
            documents: List of dicts with keys: id, embedding, title, content, metadata
        """
        if not documents:
            return

        valid_docs = []
        embedding_dims = {}
        skipped = 0

        for doc in documents:
            embedding = doc["embedding"]

            if not isinstance(embedding, list) or len(embedding) == 0:
                print(f"⚠ Skipping '{doc['title']}': invalid embedding (not a list or empty)")
                skipped += 1
                continue

            dim = len(embedding)
            if dim not in embedding_dims:
                embedding_dims[dim] = 0
            embedding_dims[dim] += 1

            valid_docs.append((doc, dim))

        if not valid_docs:
            print(f"⚠ No valid documents to upsert (skipped {skipped})")
            return

        valid_dims = {d: c for d, c in embedding_dims.items() if d >= 100}

        if not valid_dims:
            print(f"⚠ All embeddings appear to be placeholders (dimension < 100), skipping")
            return

        target_dim = max(valid_dims, key=valid_dims.get)
        print(f"✓ Using {target_dim}-dimensional embeddings ({valid_dims[target_dim]} documents)")

        self._create_collection_if_needed(target_dim)

        points = []
        for doc, dim in valid_docs:
            if dim != target_dim:
                print(f"⚠ Skipping '{doc['title']}': dimension mismatch (expected {target_dim}, got {dim})")
                skipped += 1
                continue

            point = PointStruct(
                id=doc["id"],
                vector=doc["embedding"],
                payload={
                    "title": doc["title"],
                    "content": doc["content"],
                    "metadata": doc.get("metadata", {}),
                }
            )
            points.append(point)

        if not points:
            print(f"⚠ No documents matched target dimension {target_dim}")
            return

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        print(f"✓ Upserted {len(points)} documents to Qdrant")

        if skipped > 0:
            print(f"⚠ Skipped {skipped} documents with mismatched dimensions")

    def search(self, embedding: List[float], top_k: int = 4) -> List[dict]:
        """Search for similar documents."""
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=top_k,
            score_threshold=0.5,
        )

        return [
            {
                "id": result.id,
                "score": result.score,
                "title": result.payload.get("title", ""),
                "content": result.payload.get("content", ""),
                "metadata": result.payload.get("metadata", {}),
            }
            for result in results
        ]

    def delete_document(self, doc_id: int):
        """Delete a document from the collection."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[doc_id]
        )

    def clear_collection(self):
        """Clear all documents from the collection by recreating it."""
        if self.collection_exists and self.vector_size:
            self.client.delete_collection(self.collection_name)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        elif self.collection_exists:
            self.client.delete_collection(self.collection_name)
            self.collection_exists = False
            self.vector_size = None


# Global instance
_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    """Get or create the global Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service

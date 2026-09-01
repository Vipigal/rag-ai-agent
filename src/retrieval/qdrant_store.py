from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, ScoredPoint, VectorParams

from domain.models import Chunk, RetrievedChunk


class QdrantVectorStore:
    def __init__(self, client: QdrantClient, collection: str, vector_size: int) -> None:
        self._client = client
        self._collection = collection
        if not client.collection_exists(collection):
            client.create_collection(
                collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"got {len(chunks)} chunks but {len(vectors)} vectors; "
                "each chunk must be paired with exactly one vector"
            )
        self._client.upsert(
            self._collection,
            points=[
                PointStruct(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "document_id": chunk.document_id,
                        "filename": chunk.filename,
                        "text": chunk.text,
                        "page": chunk.page,
                        "section": chunk.section,
                        "index_in_doc": chunk.index_in_doc,
                        "kind": chunk.kind,
                        "metadata": chunk.metadata,
                    },
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        points = self._client.query_points(
            self._collection, query=vector, limit=k, with_payload=True
        ).points
        return [
            RetrievedChunk(chunk=self._to_chunk(point), score=point.score)
            for point in points
        ]

    def count(self) -> int:
        return self._client.count(self._collection).count

    def _to_chunk(self, point: ScoredPoint) -> Chunk:
        payload = point.payload
        if payload is None:
            raise ValueError(
                f"point {point.id} in collection '{self._collection}' has no payload; "
                "it was not written through this store"
            )
        return Chunk(
            id=str(point.id),
            document_id=payload["document_id"],
            filename=payload["filename"],
            text=payload["text"],
            page=payload["page"],
            section=payload["section"],
            index_in_doc=payload["index_in_doc"],
            kind=payload["kind"],
            metadata=payload["metadata"],
        )

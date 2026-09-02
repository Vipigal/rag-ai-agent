from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    MultiVectorComparator,
    MultiVectorConfig,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from domain.models import Chunk, RetrievedChunk


MAX_FLOATS_PER_UPSERT = 750_000


class QdrantVectorStore:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        vector_size: int,
        max_floats_per_upsert: int = MAX_FLOATS_PER_UPSERT,
    ) -> None:
        self._client = client
        self._collection = collection
        self._max_vectors_per_upsert = max(1, max_floats_per_upsert // vector_size)
        if client.collection_exists(collection):
            _require_compatible(client, collection, vector_size)
        else:
            client.create_collection(
                collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(
                        comparator=MultiVectorComparator.MAX_SIM
                    ),
                ),
            )

    def add(self, chunks: list[Chunk], vectors: list[list[list[float]]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"got {len(chunks)} chunks but {len(vectors)} vector groups; "
                "each chunk must be paired with the vectors of its units"
            )
        for chunk, unit_vectors in zip(chunks, vectors, strict=True):
            if not unit_vectors:
                raise ValueError(f"chunk {chunk.id} has no unit vectors; at least one is required")
        points = [
            PointStruct(
                id=chunk.id,
                vector=unit_vectors,
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
            for chunk, unit_vectors in zip(chunks, vectors, strict=True)
        ]
        for batch in _batches(points, self._max_vectors_per_upsert):
            self._client.upsert(self._collection, points=batch)

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        points = self._client.query_points(
            self._collection, query=[vector], limit=k, with_payload=True
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


def _require_compatible(client: QdrantClient, collection: str, vector_size: int) -> None:
    params = client.get_collection(collection).config.params.vectors
    if not isinstance(params, VectorParams) or params.multivector_config is None:
        raise ValueError(
            f"collection '{collection}' was created without multivector support; "
            "delete it so it is recreated with one vector per unit"
        )
    if params.size != vector_size:
        raise ValueError(
            f"collection '{collection}' holds {params.size}-dimensional vectors but the "
            f"configured embedding model produces {vector_size}; delete it so it is recreated"
        )


def _batches(points: list[PointStruct], max_vectors: int) -> list[list[PointStruct]]:
    batches: list[list[PointStruct]] = []
    current: list[PointStruct] = []
    size = 0
    for point in points:
        units = len(point.vector) if isinstance(point.vector, list) else 1
        if current and size + units > max_vectors:
            batches.append(current)
            current, size = [], 0
        current.append(point)
        size += units
    if current:
        batches.append(current)
    return batches

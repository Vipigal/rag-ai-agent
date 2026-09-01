from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from domain.models import Chunk


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

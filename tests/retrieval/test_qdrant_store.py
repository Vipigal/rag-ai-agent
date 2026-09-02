from typing import cast

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from domain.models import Chunk, chunk_id
from retrieval.qdrant_store import QdrantVectorStore

DOC_ID = "c" * 64


def make_chunk(index: int, text: str) -> Chunk:
    return Chunk(
        id=chunk_id(DOC_ID, index),
        document_id=DOC_ID,
        filename="manual.pdf",
        text=text,
        page=index + 1,
        section="1 Intro",
        index_in_doc=index,
        metadata={"lang": "pt"},
    )


@pytest.fixture
def client():
    return QdrantClient(":memory:")


@pytest.fixture
def store(client):
    return QdrantVectorStore(client, collection="chunks", vector_size=3)


def test_add_persists_chunk_payload_and_vector(client, store):
    chunk = make_chunk(0, "Motor rated at 2.3 kW.")

    store.add([chunk], [[[0.1, 0.2, 0.3], [0.0, 1.0, 0.0]]])

    points = client.retrieve("chunks", ids=[chunk.id], with_payload=True, with_vectors=True)
    assert len(points) == 1
    assert points[0].payload == {
        "document_id": DOC_ID,
        "filename": "manual.pdf",
        "text": "Motor rated at 2.3 kW.",
        "page": 1,
        "section": "1 Intro",
        "index_in_doc": 0,
        "kind": "text",
        "metadata": {"lang": "pt"},
    }
    assert points[0].vector == [
        pytest.approx([0.26726, 0.53452, 0.80178], abs=1e-4),
        pytest.approx([0.0, 1.0, 0.0], abs=1e-4),
    ]


def test_re_adding_same_chunks_does_not_duplicate(client, store):
    chunks = [make_chunk(0, "first"), make_chunk(1, "second")]
    vectors = [[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]]

    store.add(chunks, vectors)
    store.add(chunks, vectors)

    assert client.count("chunks").count == 2


def test_mismatched_chunks_and_vectors_are_rejected(store):
    with pytest.raises(ValueError):
        store.add([make_chunk(0, "lonely")], [])


def test_a_chunk_without_unit_vectors_is_rejected(store):
    with pytest.raises(ValueError):
        store.add([make_chunk(0, "empty")], [[]])


def test_search_returns_ranked_retrieved_chunks_with_reconstructed_payload(store):
    close = make_chunk(0, "graxa polyrex")
    far = make_chunk(1, "flange tipo C")
    store.add([close, far], [[[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]]])

    results = store.search([0.9, 0.1, 0.0], k=2)

    assert [result.chunk for result in results] == [close, far]
    assert results[0].score > results[1].score
    assert results[0].retrieval_source == "seed"


def test_search_returns_at_most_k_results(store):
    chunks = [make_chunk(index, f"chunk {index}") for index in range(3)]
    store.add(chunks, [[[1.0, 0.0, 0.0]], [[0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0]]])

    assert len(store.search([1.0, 0.0, 0.0], k=2)) == 2


def test_search_scores_a_chunk_by_its_best_matching_unit(store):
    mixed = make_chunk(0, "prose then table row")
    single = make_chunk(1, "prose only")
    store.add([mixed, single], [[[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]], [[0.0, 0.9, 0.1]]])

    results = store.search([1.0, 0.0, 0.0], k=2)

    assert [result.chunk for result in results] == [mixed, single]
    assert results[0].score == pytest.approx(1.0, abs=1e-4)


def test_existing_single_vector_collection_is_refused_with_the_fix_named(client):
    client.create_collection("legacy", vectors_config=VectorParams(size=3, distance=Distance.COSINE))

    with pytest.raises(ValueError, match="legacy"):
        QdrantVectorStore(client, collection="legacy", vector_size=3)


def test_count_reflects_stored_points(store):
    assert store.count() == 0

    store.add([make_chunk(0, "x")], [[[0.1, 0.2, 0.3]]])

    assert store.count() == 1


class UpsertSpy:
    def __init__(self, client: QdrantClient) -> None:
        self._client = client
        self.batches: list[int] = []

    def upsert(self, collection_name: str, points: list, **kwargs):
        self.batches.append(sum(len(point.vector) for point in points))
        return self._client.upsert(collection_name, points, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._client, name)


def test_add_upserts_in_batches_bounded_by_floats_per_request(client):
    spy = UpsertSpy(client)
    store = QdrantVectorStore(
        cast(QdrantClient, spy), collection="chunks", vector_size=3, max_floats_per_upsert=15
    )
    chunks = [make_chunk(index, f"page {index}") for index in range(4)]
    vectors = [[[1.0, 0.0, 0.0]] * units for units in (3, 3, 6, 1)]

    store.add(chunks, vectors)

    assert spy.batches == [3, 3, 6, 1]
    assert client.count("chunks").count == 4


def test_existing_collection_with_another_vector_size_is_refused(client):
    QdrantVectorStore(client, collection="chunks", vector_size=3)

    with pytest.raises(ValueError, match="chunks"):
        QdrantVectorStore(client, collection="chunks", vector_size=4)

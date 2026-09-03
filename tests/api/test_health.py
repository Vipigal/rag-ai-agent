import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException

from api.composition import get_vector_store
from api.main import app
from retrieval.qdrant_store import QdrantVectorStore


@pytest.fixture(autouse=True)
def default_models(monkeypatch: pytest.MonkeyPatch):
    for name in ("LLM_MODEL", "EMBEDDING_MODEL", "QDRANT_URL"):
        monkeypatch.delenv(name, raising=False)
    yield
    app.dependency_overrides.clear()


def test_health_reports_the_vector_store_and_the_configured_models():
    store = QdrantVectorStore(QdrantClient(":memory:"), collection="chunks", vector_size=3)
    app.dependency_overrides[get_vector_store] = lambda: store

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "vector_store": "ok",
        "indexed_chunks": 0,
        "llm_model": "openai:gpt-5-mini",
        "embedding_model": "google:gemini-embedding-001",
    }


def test_health_is_503_naming_the_vector_store_url_when_qdrant_is_unreachable():
    def unreachable() -> QdrantVectorStore:
        raise ResponseHandlingException(ConnectionError("[Errno 111] Connection refused"))

    app.dependency_overrides[get_vector_store] = unreachable

    response = TestClient(app, raise_server_exceptions=False).get("/health")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "vector store unavailable" in detail
    assert "http://localhost:6333" in detail
    assert "Connection refused" in detail

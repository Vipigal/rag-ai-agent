import httpx2
import openai
import pytest
from fastapi.testclient import TestClient

from api.composition import get_ingestion_service
from api.main import app
from domain.models import IngestionResult

PDF_ONE = ("one.pdf", b"%PDF-1.4 fake one", "application/pdf")
PDF_TWO = ("two.pdf", b"%PDF-1.4 fake two", "application/pdf")


class FakeIngestionService:
    def __init__(self, result: IngestionResult) -> None:
        self.result = result
        self.received: list[tuple[str, bytes]] = []

    def ingest(self, files: list[tuple[str, bytes]]) -> IngestionResult:
        self.received.extend(files)
        return self.result


@pytest.fixture
def service():
    fake = FakeIngestionService(IngestionResult(documents_indexed=2, total_chunks=128))
    app.dependency_overrides[get_ingestion_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_uploading_pdfs_returns_the_challenge_contract(service):
    response = TestClient(app).post(
        "/documents", files=[("files", PDF_ONE), ("files", PDF_TWO)]
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Documents processed successfully",
        "documents_indexed": 2,
        "total_chunks": 128,
    }
    assert service.received == [
        ("one.pdf", b"%PDF-1.4 fake one"),
        ("two.pdf", b"%PDF-1.4 fake two"),
    ]


def test_non_pdf_upload_is_rejected_naming_the_file_and_nothing_is_ingested(service):
    response = TestClient(app).post(
        "/documents",
        files=[("files", PDF_ONE), ("files", ("notes.txt", b"plain text", "text/plain"))],
    )

    assert response.status_code == 422
    assert "notes.txt" in response.json()["detail"]
    assert service.received == []


def test_request_without_files_field_is_rejected(service):
    response = TestClient(app).post("/documents")

    assert response.status_code == 422


def test_embedding_provider_failure_maps_to_502(service):
    def explode(files):
        raise openai.APIConnectionError(
            request=httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
        )

    service.ingest = explode

    response = TestClient(app, raise_server_exceptions=False).post(
        "/documents", files=[("files", PDF_ONE)]
    )

    assert response.status_code == 502
    assert "embedding" in response.json()["detail"].lower()

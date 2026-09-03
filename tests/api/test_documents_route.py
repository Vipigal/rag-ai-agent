import asyncio
import logging

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import UserError
from qdrant_client.http.exceptions import ResponseHandlingException

from api.composition import get_ingestion_service
from api.main import app
from domain.errors import UnreadableDocument
from domain.models import IngestionResult
from retrieval.qdrant_store import IncompatibleCollection

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
    assert "provider" in response.json()["detail"].lower()


def _failing(service, exc: Exception):
    def explode(files):
        raise exc

    service.ingest = explode
    return TestClient(app, raise_server_exceptions=False).post("/documents", files=[("files", PDF_ONE)])


def test_an_unreadable_pdf_is_a_422_naming_the_file_and_the_reason(service):
    response = _failing(service, UnreadableDocument("scan.pdf", "Failed to open stream"))

    assert response.status_code == 422
    assert response.json()["detail"] == "'scan.pdf' could not be read as a PDF: Failed to open stream"


def test_an_unreachable_vector_store_is_a_503_naming_its_url(service, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")

    response = _failing(service, ResponseHandlingException(ConnectionError("[Errno 111] Connection refused")))

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "vector store unavailable at http://qdrant:6333: [Errno 111] Connection refused"
    )


def test_an_incompatible_collection_is_a_503_carrying_the_fix(service):
    response = _failing(
        service,
        IncompatibleCollection("collection 'chunks' holds 1536-dimensional vectors but the configured embedding model produces 3072; delete it so it is recreated"),
    )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("vector store collection incompatible: collection 'chunks'")
    assert "delete it" in response.json()["detail"]


def test_a_missing_provider_key_is_a_503_naming_the_variable_this_repo_documents(service):
    response = _failing(
        service,
        UserError("Set the `GOOGLE_API_KEY` environment variable or pass it via `GoogleProvider(api_key=...)` to use the Gemini API."),
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail.startswith("provider not configured: ")
    assert "GEMINI_API_KEY" in detail
    assert "GOOGLE_API_KEY" not in detail


def test_any_other_failure_is_a_500_that_names_the_exception_and_is_logged(service, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.ERROR, logger="api.errors")

    response = _failing(service, ZeroDivisionError("division by zero"))

    assert response.status_code == 500
    assert response.json()["detail"] == "internal error: ZeroDivisionError: division by zero"
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.exc_info is not None
    assert "ZeroDivisionError" in record.getMessage()


def test_the_pipeline_runs_off_the_event_loop_so_sync_adapters_can_drive_their_own(service):
    def ingest(files):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return IngestionResult(documents_indexed=1, total_chunks=9)
        raise AssertionError("ingest() ran on the server's event loop")

    service.ingest = ingest

    response = TestClient(app, raise_server_exceptions=False).post(
        "/documents", files=[("files", PDF_ONE)]
    )

    assert response.status_code == 200
    assert response.json()["total_chunks"] == 9

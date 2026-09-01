import pymupdf
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from api.composition import get_ingestion_service
from api.main import app
from domain.services.ingestion_pipeline import IngestionPipelineService
from ingestion.chunking import fixed_size_chunks
from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor
from retrieval.qdrant_store import QdrantVectorStore


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]


def make_pdf(marker: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), marker)
    return doc.tobytes()


def test_uploaded_pdf_lands_in_the_vector_store_with_provenance():
    qdrant = QdrantClient(":memory:")
    service = IngestionPipelineService(
        extractor=Pymupdf4llmExtractor(),
        chunker=fixed_size_chunks,
        embedder=FakeEmbedder(),
        store=QdrantVectorStore(qdrant, collection="chunks", vector_size=3),
    )
    app.dependency_overrides[get_ingestion_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/documents",
            files=[
                ("files", ("motor.pdf", make_pdf("the motor draws 2.3 kW"), "application/pdf"))
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Documents processed successfully"
    assert body["documents_indexed"] == 1
    assert body["total_chunks"] >= 1

    points, _ = qdrant.scroll("chunks", with_payload=True, limit=10)
    assert len(points) == body["total_chunks"]
    assert {point.payload["filename"] for point in points} == {"motor.pdf"}
    assert any("the motor draws 2.3 kW" in point.payload["text"] for point in points)
    assert all(point.payload["page"] == 1 for point in points)

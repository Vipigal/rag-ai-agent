import pymupdf
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from api.composition import get_ingestion_service
from api.main import app
from domain.services.ingestion_pipeline import IngestionPipelineService
from ingestion.chunking import page_chunks
from ingestion.embedding_units import embedding_units
from ingestion.pymupdf4llm_extractor import Pymupdf4llmExtractor
from retrieval.qdrant_store import QdrantVectorStore


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.5]


def make_pdf(marker: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), marker)
    return doc.tobytes()


def test_uploaded_pdf_lands_in_the_vector_store_with_provenance():
    qdrant = QdrantClient(":memory:")
    service = IngestionPipelineService(
        extractor=Pymupdf4llmExtractor(),
        chunker=page_chunks,
        unit_splitter=embedding_units,
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
    payloads: list[dict] = []
    for point in points:
        assert point.payload is not None
        payloads.append(point.payload)
    assert {payload["filename"] for payload in payloads} == {"motor.pdf"}
    assert any("the motor draws 2.3 kW" in payload["text"] for payload in payloads)
    assert all(payload["page"] == 1 for payload in payloads)

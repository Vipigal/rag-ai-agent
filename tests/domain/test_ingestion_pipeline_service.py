import logging

import pytest

from domain.errors import UnreadableDocument
from domain.models import Chunk, Document, Page, RetrievedChunk, chunk_id
from domain.services.ingestion_pipeline import IngestionPipelineService

SHA_ONE = "f315915be2378786af1785ccc6a226aad15ad69d96465ec0105b186066cb2681"
SHA_TWO = "ebb284661409282f456c3d8815d094ea65244de208327b739e618de0bb3fd63a"


class FakeExtractor:
    def extract(self, data: bytes, filename: str) -> list[Page]:
        return [Page(number=1, text=f"contents of {filename}", section=None)]


def fake_chunker(document: Document, pages: list[Page]) -> list[Chunk]:
    return [
        Chunk(
            id=chunk_id(document.id, i),
            document_id=document.id,
            filename=document.filename,
            text=f"{page.text} [part {i}]",
            page=page.number,
            section=page.section,
            index_in_doc=i,
        )
        for page in pages
        for i in (0, 1)
    ]


def fake_unit_splitter(chunk: Chunk) -> list[str]:
    return [block for block in chunk.text.split("\n\n") if block]


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectors: list[list[list[float]]] = []

    def add(self, chunks: list[Chunk], vectors: list[list[list[float]]]) -> None:
        self.chunks.extend(chunks)
        self.vectors.extend(vectors)

    def search(self, vector: list[float], k: int) -> list[RetrievedChunk]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


def make_service(store: FakeVectorStore) -> IngestionPipelineService:
    return IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=fake_chunker,
        embedder=FakeEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=store,
    )


def test_document_without_chunks_is_counted_but_never_embedded():
    store = FakeVectorStore()

    class RejectEmptyEmbedder:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            assert texts, "embed_documents must not be called with no texts"
            return [[1.0]] * len(texts)

        def embed_query(self, text: str) -> list[float]:
            return [1.0]

    service = IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=lambda document, pages: [],
        embedder=RejectEmptyEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=store,
    )

    result = service.ingest([("blank.pdf", b"%PDF blank")])

    assert result.documents_indexed == 1
    assert result.total_chunks == 0
    assert store.chunks == []


def test_ingest_reports_documents_and_chunks_indexed():
    result = make_service(FakeVectorStore()).ingest(
        [("one.pdf", b"%PDF fake one"), ("two.pdf", b"%PDF fake two")]
    )

    assert result.documents_indexed == 2
    assert result.total_chunks == 4


def test_ingest_stores_chunks_paired_with_their_embeddings():
    store = FakeVectorStore()

    make_service(store).ingest([("one.pdf", b"%PDF fake one")])

    assert [c.text for c in store.chunks] == [
        "contents of one.pdf [part 0]",
        "contents of one.pdf [part 1]",
    ]
    assert store.vectors == [
        [[float(len(unit))] for unit in fake_unit_splitter(c)] for c in store.chunks
    ]


def test_ingest_derives_document_identity_from_content():
    store = FakeVectorStore()

    make_service(store).ingest(
        [("one.pdf", b"%PDF fake one"), ("two.pdf", b"%PDF fake two")]
    )

    assert {c.document_id for c in store.chunks} == {SHA_ONE, SHA_TWO}
    assert {c.filename for c in store.chunks} == {"one.pdf", "two.pdf"}


def make_clock():
    ticks = iter(float(i) for i in range(100))
    return lambda: next(ticks)


def test_ingest_logs_progress_per_file_and_totals(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="domain.services.ingestion_pipeline")
    service = IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=fake_chunker,
        embedder=FakeEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=FakeVectorStore(),
        clock=make_clock(),
    )

    service.ingest([("one.pdf", b"%PDF fake one"), ("two.pdf", b"%PDF fake two")])

    assert [record.getMessage() for record in caplog.records] == [
        "ingesting 2 file(s)",
        "one.pdf: extracting (0.0 MB)",
        "one.pdf: 1 page(s) extracted in 1.0s",
        "two.pdf: extracting (0.0 MB)",
        "two.pdf: 1 page(s) extracted in 1.0s",
        "one.pdf: 2 chunk(s) as 2 unit(s) embedded and indexed in 1.0s",
        "two.pdf: 2 chunk(s) as 2 unit(s) embedded and indexed in 1.0s",
        "done: 2 document(s), 4 chunk(s) indexed in 9.0s",
    ]


class ExtractorRejecting:
    def __init__(self, filename: str) -> None:
        self._filename = filename

    def extract(self, data: bytes, filename: str) -> list[Page]:
        if filename == self._filename:
            raise UnreadableDocument(filename, "Failed to open stream")
        return [Page(number=1, text=f"contents of {filename}", section=None)]


def test_an_unreadable_file_aborts_the_upload_before_anything_is_embedded_or_stored():
    store = FakeVectorStore()

    class RecordingEmbedder(FakeEmbedder):
        calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            RecordingEmbedder.calls += 1
            return super().embed_documents(texts)

    service = IngestionPipelineService(
        extractor=ExtractorRejecting("two.pdf"),
        chunker=fake_chunker,
        embedder=RecordingEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=store,
    )

    with pytest.raises(UnreadableDocument, match="two.pdf"):
        service.ingest([("one.pdf", b"%PDF fake one"), ("two.pdf", b"%PDF fake two")])

    assert store.chunks == []
    assert RecordingEmbedder.calls == 0


def test_ingest_logs_when_a_document_yields_no_text(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="domain.services.ingestion_pipeline")
    service = IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=lambda document, pages: [],
        embedder=FakeEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=FakeVectorStore(),
        clock=make_clock(),
    )

    service.ingest([("blank.pdf", b"%PDF blank")])

    assert "blank.pdf: no text extracted, nothing to index" in [
        record.getMessage() for record in caplog.records
    ]


def test_ingest_embeds_every_unit_and_stores_them_grouped_per_chunk():
    store = FakeVectorStore()
    two_block_chunker = lambda document, pages: [
        Chunk(
            id=chunk_id(document.id, 0),
            document_id=document.id,
            filename=document.filename,
            text="first block\n\nsecond block\n\nthird block",
            page=1,
            section=None,
            index_in_doc=0,
        )
    ]
    service = IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=two_block_chunker,
        embedder=FakeEmbedder(),
        unit_splitter=fake_unit_splitter,
        store=store,
    )

    service.ingest([("one.pdf", b"%PDF fake one")])

    assert len(store.vectors) == 1
    assert len(store.vectors[0]) == 3

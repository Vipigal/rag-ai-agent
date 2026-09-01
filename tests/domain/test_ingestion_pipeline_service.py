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


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectors: list[list[float]] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
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
        store=store,
    )


def test_document_without_chunks_is_counted_but_never_embedded():
    store = FakeVectorStore()

    class RejectEmptyEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            assert texts, "embed must not be called with no texts"
            return [[1.0]] * len(texts)

    service = IngestionPipelineService(
        extractor=FakeExtractor(),
        chunker=lambda document, pages: [],
        embedder=RejectEmptyEmbedder(),
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
    assert store.vectors == [[float(len(c.text))] for c in store.chunks]


def test_ingest_derives_document_identity_from_content():
    store = FakeVectorStore()

    make_service(store).ingest(
        [("one.pdf", b"%PDF fake one"), ("two.pdf", b"%PDF fake two")]
    )

    assert {c.document_id for c in store.chunks} == {SHA_ONE, SHA_TWO}
    assert {c.filename for c in store.chunks} == {"one.pdf", "two.pdf"}

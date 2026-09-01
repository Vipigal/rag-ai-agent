import hashlib

from domain.models import Document, IngestionResult
from domain.ports import Chunker, EmbeddingModel, PdfExtractor, VectorStore


class IngestionPipelineService:
    def __init__(
        self,
        extractor: PdfExtractor,
        chunker: Chunker,
        embedder: EmbeddingModel,
        store: VectorStore,
    ) -> None:
        self._extractor = extractor
        self._chunker = chunker
        self._embedder = embedder
        self._store = store

    def ingest(self, files: list[tuple[str, bytes]]) -> IngestionResult:
        total_chunks = 0
        for filename, data in files:
            document = Document(id=hashlib.sha256(data).hexdigest(), filename=filename)
            pages = self._extractor.extract(data, filename)
            chunks = self._chunker(document, pages)
            if chunks:
                vectors = self._embedder.embed([chunk.text for chunk in chunks])
                self._store.add(chunks, vectors)
            total_chunks += len(chunks)
        return IngestionResult(documents_indexed=len(files), total_chunks=total_chunks)

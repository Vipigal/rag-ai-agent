import hashlib
import logging
import time
from collections.abc import Callable

from domain.models import Document, IngestionResult
from domain.ports import Chunker, EmbeddingModel, PdfExtractor, VectorStore

log = logging.getLogger(__name__)

MEGABYTE = 1024 * 1024


class IngestionPipelineService:
    def __init__(
        self,
        extractor: PdfExtractor,
        chunker: Chunker,
        embedder: EmbeddingModel,
        store: VectorStore,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._extractor = extractor
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._clock = clock

    def ingest(self, files: list[tuple[str, bytes]]) -> IngestionResult:
        started = self._clock()
        log.info("ingesting %d file(s)", len(files))
        total_chunks = 0
        for filename, data in files:
            total_chunks += self._ingest_one(filename, data)
        log.info(
            "done: %d document(s), %d chunk(s) indexed in %.1fs",
            len(files),
            total_chunks,
            self._clock() - started,
        )
        return IngestionResult(documents_indexed=len(files), total_chunks=total_chunks)

    def _ingest_one(self, filename: str, data: bytes) -> int:
        document = Document(id=hashlib.sha256(data).hexdigest(), filename=filename)
        log.info("%s: extracting (%.1f MB)", filename, len(data) / MEGABYTE)
        extract_started = self._clock()
        pages = self._extractor.extract(data, filename)
        extracted_at = self._clock()
        log.info(
            "%s: %d page(s) extracted in %.1fs",
            filename,
            len(pages),
            extracted_at - extract_started,
        )
        chunks = self._chunker(document, pages)
        if not chunks:
            log.info("%s: no text extracted, nothing to index", filename)
            return 0
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        self._store.add(chunks, vectors)
        log.info(
            "%s: %d chunk(s) embedded and indexed in %.1fs",
            filename,
            len(chunks),
            self._clock() - extracted_at,
        )
        return len(chunks)

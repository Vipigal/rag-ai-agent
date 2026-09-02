import hashlib
import logging
import time
from collections.abc import Callable

from domain.models import Document, IngestionResult
from domain.ports import Chunker, EmbeddingModel, PdfExtractor, UnitSplitter, VectorStore

log = logging.getLogger(__name__)

MEGABYTE = 1024 * 1024


class IngestionPipelineService:
    def __init__(
        self,
        extractor: PdfExtractor,
        chunker: Chunker,
        unit_splitter: UnitSplitter,
        embedder: EmbeddingModel,
        store: VectorStore,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._extractor = extractor
        self._chunker = chunker
        self._unit_splitter = unit_splitter
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
        units = [self._unit_splitter(chunk) for chunk in chunks]
        vectors = self._embedder.embed_documents(
            [unit for chunk_units in units for unit in chunk_units]
        )
        self._store.add(chunks, _regroup(vectors, [len(chunk_units) for chunk_units in units]))
        log.info(
            "%s: %d chunk(s) as %d unit(s) embedded and indexed in %.1fs",
            filename,
            len(chunks),
            len(vectors),
            self._clock() - extracted_at,
        )
        return len(chunks)


def _regroup(vectors: list[list[float]], sizes: list[int]) -> list[list[list[float]]]:
    grouped: list[list[list[float]]] = []
    offset = 0
    for size in sizes:
        grouped.append(vectors[offset : offset + size])
        offset += size
    return grouped

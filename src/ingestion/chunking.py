from domain.models import Chunk, Document, Page, chunk_id


def fixed_size_chunks(
    document: Document,
    pages: list[Page],
    size: int = 1000,
    overlap: int = 200,
) -> list[Chunk]:
    step = size - overlap
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text.strip():
            continue
        for start in range(0, len(page.text), step):
            piece = page.text[start : start + size]
            chunks.append(
                Chunk(
                    id=chunk_id(document.id, len(chunks)),
                    document_id=document.id,
                    filename=document.filename,
                    text=piece,
                    page=page.number,
                    section=page.section,
                    index_in_doc=len(chunks),
                )
            )
            if start + size >= len(page.text):
                break
    return chunks

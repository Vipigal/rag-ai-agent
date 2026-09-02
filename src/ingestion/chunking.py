from domain.models import Chunk, Document, Page, chunk_id


def page_chunks(document: Document, pages: list[Page]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                id=chunk_id(document.id, len(chunks)),
                document_id=document.id,
                filename=document.filename,
                text=text,
                page=page.number,
                section=page.section,
                index_in_doc=len(chunks),
            )
        )
    return chunks

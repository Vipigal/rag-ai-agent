import uuid

from domain.models import Document, Page
from ingestion.chunking import page_chunks

DOC = Document(id="a" * 64, filename="manual.pdf")


def test_chunk_ids_are_deterministic_uuids_scoped_to_document():
    pages = [Page(number=1, text="first", section=None), Page(number=2, text="second", section=None)]
    other_doc = Document(id="b" * 64, filename="manual.pdf")

    first = page_chunks(DOC, pages)
    second = page_chunks(DOC, pages)
    other = page_chunks(other_doc, pages)

    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first)
    assert {c.id for c in first}.isdisjoint({c.id for c in other})
    for chunk in first:
        uuid.UUID(chunk.id)


def test_every_page_with_text_becomes_exactly_one_chunk():
    pages = [
        Page(number=1, text="# Handling\n\nUse correct equipment.\n\n|Frame|Grease|\n|---|---|\n|132|20|", section=None),
        Page(number=2, text="   \n\n", section=None),
        Page(number=3, text="Third page text. \n", section="5 > 5.1 Power"),
    ]

    chunks = page_chunks(DOC, pages)

    assert [(c.page, c.index_in_doc) for c in chunks] == [(1, 0), (3, 1)]
    assert chunks[0].text == pages[0].text
    assert chunks[1].text == "Third page text."


def test_chunk_carries_the_page_provenance():
    pages = [Page(number=3, text="Motor rated at 2.3 kW.", section="5 > 5.1 Power")]

    chunks = page_chunks(DOC, pages)

    chunk = chunks[0]
    assert chunk.document_id == DOC.id
    assert chunk.filename == "manual.pdf"
    assert chunk.page == 3
    assert chunk.section == "5 > 5.1 Power"
    assert chunk.kind == "text"
    assert chunk.metadata == {}

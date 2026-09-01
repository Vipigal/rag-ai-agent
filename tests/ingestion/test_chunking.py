import uuid

from domain.models import Document, Page
from ingestion.chunking import fixed_size_chunks

DOC = Document(id="a" * 64, filename="manual.pdf")


def test_chunk_ids_are_deterministic_uuids_scoped_to_document():
    pages = [Page(number=1, text="abcdefghijklmnopqrst", section=None)]
    other_doc = Document(id="b" * 64, filename="manual.pdf")

    first = fixed_size_chunks(DOC, pages, size=10, overlap=3)
    second = fixed_size_chunks(DOC, pages, size=10, overlap=3)
    other = fixed_size_chunks(other_doc, pages, size=10, overlap=3)

    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first)
    assert {c.id for c in first}.isdisjoint({c.id for c in other})
    for chunk in first:
        uuid.UUID(chunk.id)


def test_long_page_splits_into_overlapping_chunks():
    pages = [Page(number=1, text="abcdefghijklmnopqrst", section=None)]

    chunks = fixed_size_chunks(DOC, pages, size=10, overlap=3)

    assert [c.text for c in chunks] == ["abcdefghij", "hijklmnopq", "opqrst"]
    assert [c.index_in_doc for c in chunks] == [0, 1, 2]
    assert all(c.page == 1 for c in chunks)


def test_index_runs_across_pages_and_blank_pages_yield_no_chunks():
    pages = [
        Page(number=1, text="first page", section=None),
        Page(number=2, text="   ", section=None),
        Page(number=3, text="third page", section=None),
    ]

    chunks = fixed_size_chunks(DOC, pages, size=1000, overlap=200)

    assert [(c.page, c.index_in_doc) for c in chunks] == [(1, 0), (3, 1)]


def test_short_page_becomes_single_chunk_with_provenance():
    pages = [Page(number=3, text="Motor rated at 2.3 kW.", section="5 > 5.1 Power")]

    chunks = fixed_size_chunks(DOC, pages, size=1000, overlap=200)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == "Motor rated at 2.3 kW."
    assert chunk.document_id == DOC.id
    assert chunk.filename == "manual.pdf"
    assert chunk.page == 3
    assert chunk.section == "5 > 5.1 Power"
    assert chunk.index_in_doc == 0
    assert chunk.kind == "text"
    assert chunk.metadata == {}

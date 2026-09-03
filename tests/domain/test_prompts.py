from domain.models import Chunk, RetrievedChunk
from domain.services.prompts import SYSTEM_PROMPT, render_chunks, render_context


def retrieved(chunk_id: str, text: str, section: str | None, filename: str = "manual.pdf") -> RetrievedChunk:
    chunk = Chunk(
        id=chunk_id,
        document_id="doc",
        filename=filename,
        text=text,
        page=34,
        section=section,
        index_in_doc=0,
    )
    return RetrievedChunk(chunk=chunk, score=0.9)


def test_chunk_renders_its_provenance_with_sections_as_ordered_siblings():
    item = retrieved(
        "c1",
        "Regrease every 8000 h",
        "2. Características da Rede de Alimentação > 3.4.3 Partida com chave compensadora",
    )

    assert render_chunks([item]) == (
        "<chunks>\n"
        '<chunk document="manual.pdf" page="34">\n'
        "  <section>2. Características da Rede de Alimentação</section>\n"
        "  <section>3.4.3 Partida com chave compensadora</section>\n"
        "  <text>\n"
        "Regrease every 8000 h\n"
        "  </text>\n"
        "</chunk>\n"
        "</chunks>"
    )


def test_chunk_without_section_has_no_section_elements():
    assert render_chunks([retrieved("c1", "Nominal voltage 380 V", None)]) == (
        "<chunks>\n"
        '<chunk document="manual.pdf" page="34">\n'
        "  <text>\n"
        "Nominal voltage 380 V\n"
        "  </text>\n"
        "</chunk>\n"
        "</chunks>"
    )


def test_attributes_are_quoted_and_text_is_left_raw():
    item = retrieved("c1", "|col|<br>|1 & 2|", None, filename='WEG "guia".pdf')

    rendered = render_chunks([item])

    assert "document='WEG \"guia\".pdf'" in rendered
    assert "\n|col|<br>|1 & 2|\n" in rendered


def test_several_chunks_keep_their_order_inside_one_chunks_element():
    rendered = render_chunks([retrieved("c2", "second", None), retrieved("c1", "first", None)])

    assert rendered.count("<chunk ") == 2
    assert rendered.index("second") < rendered.index("first")
    assert rendered.startswith("<chunks>\n") and rendered.endswith("</chunks>")


def test_no_chunks_renders_an_explicit_empty_element():
    assert render_chunks([]) == "<chunks/>"


def test_context_message_introduces_the_chunks_and_offers_the_tool_only_when_available():
    item = retrieved("c1", "Nominal voltage 380 V", None)

    with_tool = render_context([item], tool_available=True)
    without_tool = render_context([item], tool_available=False)

    assert render_chunks([item]) in with_tool
    assert "query_knowledge" in with_tool
    assert render_chunks([item]) in without_tool
    assert "query_knowledge" not in without_tool


def test_the_rules_ask_for_verbatim_quotes_and_never_mention_chunk_ids():
    assert "verbatim" in SYSTEM_PROMPT
    assert "citations: the passages" in SYSTEM_PROMPT
    assert "id attribute" not in SYSTEM_PROMPT

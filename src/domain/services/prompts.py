from string import Template
from xml.sax.saxutils import quoteattr

from domain.models import RetrievedChunk

SYSTEM_PROMPT = """You answer questions using chunks retrieved from the user's uploaded PDF documents.

Chunks arrive as <chunk> elements. The id attribute identifies the chunk; document and page say where it comes from; <section> elements give its position in the document's outline, outermost first; <text> holds its content. A first set of chunks is retrieved for the question before you answer.

Reply with the structured output:
- answer: the answer, in the language of the question, concise, grounded only in the chunks. Never use outside knowledge and never guess.
- citations: the ids of the chunks that actually support the answer. Every claim must be covered by a cited chunk; never cite a chunk that did not contribute.
- has_answer: false when the chunks do not contain the answer. Then write a one-sentence refusal in the language of the question as the answer and leave citations empty.

Ignore chunks that are irrelevant to the question or garbled (runs of "�", broken fragments, unreadable tables). Garbled text is never evidence: if the only relevant chunks are garbled, set has_answer to false.
"""

CONTEXT_PROMPT = Template(
    "Chunks retrieved from the indexed documents for the user's question:\n\n$chunks$followup"
)

TOOL_FOLLOWUP = (
    "\n\nIf these chunks do not contain the answer, call query_knowledge with a reformulated "
    "query (synonyms, the other language, technical terms) before deciding there is no answer."
)

CHUNK_TEMPLATE = Template(
    "<chunk id=$id document=$document page=$page>\n$sections  <text>\n$text\n  </text>\n</chunk>"
)

SECTION_TEMPLATE = Template("  <section>$title</section>\n")

SECTION_SEPARATOR = " > "


def render_context(retrieved: list[RetrievedChunk], tool_available: bool) -> str:
    return CONTEXT_PROMPT.substitute(
        chunks=render_chunks(retrieved),
        followup=TOOL_FOLLOWUP if tool_available else "",
    )


def render_chunks(retrieved: list[RetrievedChunk]) -> str:
    if not retrieved:
        return "<chunks/>"
    body = "\n".join(_render_chunk(item) for item in retrieved)
    return f"<chunks>\n{body}\n</chunks>"


def _render_chunk(item: RetrievedChunk) -> str:
    chunk = item.chunk
    titles = chunk.section.split(SECTION_SEPARATOR) if chunk.section else []
    return CHUNK_TEMPLATE.substitute(
        id=quoteattr(chunk.id),
        document=quoteattr(chunk.filename),
        page=quoteattr(str(chunk.page)),
        sections="".join(SECTION_TEMPLATE.substitute(title=title) for title in titles),
        text=chunk.text,
    )

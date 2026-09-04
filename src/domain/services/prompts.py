from string import Template
from xml.sax.saxutils import quoteattr

from domain.models import SECTION_SEPARATOR, RetrievedChunk

SYSTEM_PROMPT = """You answer questions using chunks retrieved from the user's uploaded PDF documents.

Chunks arrive as <chunk> elements: document and page say where the chunk comes from; <section> elements give its position in the document's outline, outermost first; <text> holds its content. A first set of chunks is retrieved for the question before you answer.

Reply with the structured output:
- answer: the answer, in the language of the question, concise, grounded only in the chunks. Never use outside knowledge and never guess.
- citations: the passages of the chunks that support the answer, copied verbatim from <text> — the exact words, numbers, units and spacing, character for character, never paraphrased, never translated, never abridged (no "..." and no omitted middle). One contiguous passage per citation: a sentence or a few sentences, or a table row (put the table's header row on its own line above it). Where a page prints the same content in several languages, one passage covers one language: never continue a passage into its translation. Quote the minimal passage that supports each claim and cover every claim; never cite text that did not contribute. When a passage is hard to copy exactly, cite a shorter one you can copy exactly rather than an approximation of the longer.
- has_answer: false when the chunks do not contain the answer. Then write a one-sentence refusal in the language of the question as the answer and leave citations empty.

Answer in the language of the user's question. The chunks are a multilingual corpus and a single page may mirror the same content in several languages; that never changes the language you answer in — read in whatever language the chunks use and write the answer, refusals included, in the question's. Only citations keep the language of the source.

Ignore chunks that are irrelevant to the question or garbled (runs of "�", broken fragments, unreadable tables). Garbled text is never evidence: if the only relevant chunks are garbled, set has_answer to false.
"""

CONTEXT_PROMPT = Template(
    "Chunks retrieved from the indexed documents for the user's question:"
    "\n\n$chunks$followup$language"
)

LANGUAGE_REMINDER = (
    "\n\nThe chunks above are in whatever language their documents use. Your answer goes in "
    "the language of the question that follows, not in theirs; only the citations keep the "
    "source's words."
)

TOOL_FOLLOWUP = (
    "\n\nIf these chunks do not contain the answer, call query_knowledge with a reformulated "
    "query (synonyms, the other language, technical terms) before deciding there is no answer."
)

CHUNK_TEMPLATE = Template(
    "<chunk document=$document page=$page>\n$sections  <text>\n$text\n  </text>\n</chunk>"
)

SECTION_TEMPLATE = Template("  <section>$title</section>\n")



def render_context(retrieved: list[RetrievedChunk], tool_available: bool) -> str:
    return CONTEXT_PROMPT.substitute(
        chunks=render_chunks(retrieved),
        followup=TOOL_FOLLOWUP if tool_available else "",
        language=LANGUAGE_REMINDER,
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
        document=quoteattr(chunk.filename),
        page=quoteattr(str(chunk.page)),
        sections="".join(SECTION_TEMPLATE.substitute(title=title) for title in titles),
        text=chunk.text,
    )

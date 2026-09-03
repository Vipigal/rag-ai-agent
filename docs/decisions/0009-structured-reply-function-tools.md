---
type: Decision
title: 0009 — Structured agent reply, function-derived tools, chunk ids as citation handles
description: The agent's final answer is a provider-enforced structured output (AgentReply with answer, citations as chunk ids, has_answer) instead of the [i]/NO_ANSWER text protocol; tools are Python functions whose schema the adapter derives, replacing the hand-written ToolSpec; the numbered-excerpt registry is gone — chunk ids are the citation handles; retrieved chunks reach the model as an XML-rendered system message, not inside the user turn.
tags: [agent, llm, structured-output, tools, citations, prompt, pydantic-ai]
status: stable
generated: { by: claude_code/claude-fable-5, at: 2026-09-02T21:53:05Z }
verified: { by: human:vinicius, at: 2026-09-02T02:40:00Z }
sources:
  - id: decision-0008
    resource: /docs/decisions/0008-question-agent-baseline.md
    title: 0008 — Question agent baseline
  - id: spec
    resource: /specs/question-agent-design.md
    title: Question Agent — Design & Implementation Plan
  - id: arch
    resource: /docs/architecture.md
    title: System Architecture — Ports & Adapters Lite
  - id: ingestion
    resource: /src/ingestion/ingestion.md
    title: Ingestion Module
  - id: pai-direct
    resource: https://pydantic.dev/docs/ai/core-concepts/direct/
    title: PydanticAI docs — Direct model requests
  - id: openai-structured
    resource: https://platform.openai.com/docs/guides/structured-outputs
    title: OpenAI — Structured Outputs (strict JSON schema)
---

# Context

> **Amended by [Decision 0013](/docs/decisions/0013-citations-as-quotes.md)**
> (2026-09-02): citations are no longer chunk ids but passages quoted
> verbatim from the chunks, resolved by containment; the `id` attribute
> left the `<chunk>` rendering and the seed fallback for uncited answers
> is gone. The structured reply, the function-derived tools and the XML
> context in a system message stand.

> **Amended by [Decision 0014](/docs/decisions/0014-error-semantics-and-startup-validation.md)**
> (2026-09-02): a reply that violates the schema is no longer a deliberate
> 500 — the adapter requests the model once more and, if the second reply
> is malformed too, raises `UnexpectedModelBehavior`, which the API maps to
> a 502 naming the model. Strict native output and the validation back
> into the dataclass stand.

[Decision 0008](/docs/decisions/0008-question-agent-baseline.md) fixed how
the agent reports what grounds its answer: the model writes `[i]`
markers inline, refuses with a `NO_ANSWER` sentinel, and declares its one
tool as a `ToolSpec` carrying a verbatim JSON schema.[^decision-0008] The
first implementation landed on 2026-09-01 exactly that way and worked in
the live smoke.[^spec] The owner's code review then raised four
objections, all of which held up under verification against the
installed `pydantic-ai-slim` 2.37.0:

1. **Text protocols fail probabilistically.** Extracting the decision
   ("did it answer? what did it cite?") from free text with regexes
   means a refusal without the sentinel silently becomes an answer, and
   a marker written as `(2)` or `[2]` in the wrong place is invisible.
   The model's output discipline is not a contract.
2. **A tool as a hand-written JSON schema** is error-prone and
   non-idiomatic; every current framework derives the schema from a
   typed Python function.
3. **"Excerpt" was an invented concept.** The numbered registry existed
   only to give the model short citation handles, and it introduced a
   second name for what is already a `Chunk`.
4. **Context inside the user turn** blurs provenance: the model cannot
   tell the question from the material we retrieved for it.

# Decision

## The final answer is a structured output

The domain declares the reply as a frozen stdlib dataclass:

```python
@dataclass(frozen=True)
class AgentReply:
    answer: str
    citations: list[str]
    has_answer: bool
```

The `LLM` port becomes `complete(messages, tools) -> Completion`, with
`Completion(message: Message, reply: AgentReply | None)` — `reply` is
set when the model produced a final answer, `message.tool_calls` when it
asked for a tool. The adapter derives the JSON schema with
`pydantic.TypeAdapter(AgentReply)`, requests **native, strict**
structured output (`output_mode="native"`, `strict=True` — the provider
constrains generation to the schema[^openai-structured]) alongside the
function tools in the same request,[^pai-direct] and validates the
response back into the dataclass. The domain never sees JSON or regexes.
The port is deliberately **not generic** over the output type: one type
exists today; a second caller generalizes it then.

## Tools are Python functions

The port takes `list[Tool]` where `Tool = Callable[..., str]`. The
adapter derives each `ToolDefinition` with
`pydantic_ai.Tool(fn, strict=True).tool_def`: name from the function,
description from its docstring, parameter descriptions from the
docstring's `Args:` section. `ToolSpec` leaves the domain. The domain
still owns the loop (architecture rule 9[^arch]): it dispatches each
`ToolCall` to the function of that name and appends the result as a
`tool` message. The tool's description therefore lives as the
function's docstring — the only prompt text outside `prompts.py`, and
runtime data rather than a comment.

## Chunk ids are the citation handles

No numbering. Every chunk shown to the model carries its `chunk.id`;
`AgentReply.citations` lists the ids that ground the answer. The
per-request memory of what the model has seen is a
`dict[str, RetrievedChunk]` — insertion-ordered and deduplicated by
construction, one `setdefault` per retrieved result. Resolution is a
lookup: unknown ids are dropped; `has_answer=True` with no valid
citation falls back to the seed results (0008's rule, unchanged);
`has_answer=False` yields empty references and the model's refusal
sentence as the answer.

## Retrieved chunks are a system message rendered as XML

Three messages open every conversation: a system message with the rules,
a **second system message** holding the retrieved chunks — introduced
as what `query_knowledge` retrieved for the question, with the
invitation to call it again if insufficient — and the user message with
the bare question. For OpenAI's Responses API each system part is its
own `system` item (the API's "developer" message), so the separation is
real on the wire. Tool results use the same rendering. Each chunk is
rendered with everything ingestion knows about its origin:

```xml
<chunk id="3f9a…" document="WEG-guia-50032749.pdf" page="34">
  <section>2. Características da Rede de Alimentação</section>
  <section>3.4.3 Partida com chave compensadora</section>
  <text>…</text>
</chunk>
```

Sections are the breadcrumb levels as **ordered siblings, not nested**:
same information, less noise, and honest about the breadcrumb being a
reconstructed path that is known to go stale.[^ingestion] `kind` and
`metadata` render nothing until they carry data. Attributes are quoted
with `xml.sax.saxutils.quoteattr`; the text is left raw. Templates and
the renderer live in `src/domain/services/prompts.py` using the stdlib
`string.Template`.

# Alternatives rejected

- **Hardening the text protocol** (more regexes, lenient markers) —
  fights probability with more probability; the failure class stays.
- **Tool-mode output** (`output_mode="tool"`, a `final_result` tool) —
  portable to providers without native JSON-schema output, but it
  routes the answer through tool dispatch; native mode is
  provider-enforced on OpenAI and Gemini, the two providers this project
  plans for, and PydanticAI selects the mechanism per model.
- **A generic `complete[T]`** — one output type; interface tax today.
- **Numbered handles `[1..n]`** — shorter tokens, but they need the
  numbering concept that duplicated `Chunk`. UUID copy errors are the
  accepted risk; if citation precision shows them, the recorded
  hardening is a per-call `enum` on `citations` restricted to the ids
  already shown — strict mode supports it, making a hallucinated id
  impossible.
- **Seed context as a synthetic tool call** (fabricated assistant turn
  plus tool result) — would frame the seed exactly like tool results,
  but it invents a turn the model never produced, breaks when
  `QUERY_KNOWLEDGE_ENABLED=false` (a result for an undeclared tool), and
  confounds the tool-on/off eval with a framing difference.
- **`format_as_xml` or Jinja2 in the domain** — rule 1 keeps the domain
  stdlib-only;[^arch] two templates do not earn a dependency.
- **Rendering as a `Chunk` method** — entities are data with identity
  and no presentation behavior;[^arch] rendering for a prompt belongs
  with the prompt.
- **Escaping chunk text** — pymupdf4llm leaves markdown (`<br>`, pipes)
  in chunks; escaping would show the model `&lt;br&gt;`. The tags are
  prompt delimiters, not a document to be parsed.

# Consequences

- 0008's durable choices stand — PydanticAI direct, references are what
  the LLM cites, in-process eval surface, the config knobs. Its `[i]`
  and `NO_ANSWER` mechanism and the `ToolSpec` vocabulary are
  superseded by this record; 0008 carries a pointer.
- Domain vocabulary: `ToolSpec` removed; `AgentReply` and `Completion`
  added; `Tool` alias in `ports.py`; the `LLM` port signature changes.
- The adapter owns schema generation and validation (Pydantic is allowed
  there); `strict=True` on tools and output, with PydanticAI applying
  the OpenAI strict transformer (`additionalProperties: false`, all
  fields required).
- The prompt shape changes without an answer-layer eval to gate it — the
  live smoke is the check, and the first answer-eval baseline will be
  measured over this shape. The `AgentService` tests get simpler:
  fakes return `Completion(reply=AgentReply(...))`, no marker strings.
- Putting the section breadcrumb in the **embedding** as well
  (contextual headers at index time) is a separate, eval-gated
  ingestion experiment, not part of this decision.
- Serves _LLM Use_ (a schema-enforced protocol instead of text
  discipline), _Code Quality_ (no invented entity, idiomatic tools),
  _Functionality_ (a whole class of silent failures removed).

[^decision-0008]: 0008 — Question agent baseline: the `[i]` protocol, `NO_ANSWER` sentinel, seed fallback and `ToolSpec` vocabulary this record amends.

[^spec]: Question Agent — Design & Implementation Plan: the landed implementation and its live-smoke findings (2026-09-01).

[^arch]: System Architecture — rule 1 (stdlib-only domain), the entity definition, rule 9 (the loop lives in `AgentService`).

[^ingestion]: Ingestion Module — section breadcrumbs carry forward across pages and can go stale when TOC levels are inconsistent.

[^pai-direct]: PydanticAI docs — Direct model requests: `ModelRequestParameters` carries `function_tools` and `output_mode`/`output_object` in one call.

[^openai-structured]: OpenAI — Structured Outputs: strict JSON-schema mode constrains generation to the schema; supported keywords include `enum`.

from dataclasses import replace

from domain.models import AgentReply, Answer, Completion, Message, RetrievedChunk, ToolCall
from domain.ports import LLM, Retriever, Tool
from domain.services.prompts import SYSTEM_PROMPT, render_chunks, render_context


class AgentService:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        k: int,
        max_tool_rounds: int,
        tool_enabled: bool,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._k = k
        self._max_tool_rounds = max_tool_rounds
        self._tool_enabled = tool_enabled

    def answer(self, question: str) -> Answer:
        seen: dict[str, RetrievedChunk] = {}
        seed = self._retriever.retrieve(question, self._k)
        _remember(seen, seed)

        def query_knowledge(query: str) -> str:
            """Search the indexed documents for more chunks.

            Use it when the chunks already shown do not answer the question. Reformulate
            freely: synonyms, the other language, technical terms. Returns chunks you can
            cite by id.

            Args:
                query: The search query to run against the indexed documents.
            """
            results = self._retriever.retrieve(query, self._k)
            as_tool_results = [replace(item, retrieval_source="tool") for item in results]
            _remember(seen, as_tool_results)
            return render_chunks(as_tool_results)

        tools: list[Tool] = [query_knowledge] if self._tool_enabled else []
        rounds = 0
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="system",
                content=render_context(seed, tool_available=bool(self._offered(tools, rounds))),
            ),
            Message(role="user", content=question),
        ]

        completion = self._llm.complete(messages, self._offered(tools, rounds))
        while completion.reply is None and rounds < self._max_tool_rounds:
            messages.append(completion.message)
            messages.extend(_run_tool(call, tools) for call in completion.message.tool_calls)
            rounds += 1
            completion = self._llm.complete(messages, self._offered(tools, rounds))

        return _to_answer(_final_reply(completion), seen, seed)

    def _offered(self, tools: list[Tool], rounds: int) -> list[Tool]:
        return tools if rounds < self._max_tool_rounds else []


def _remember(seen: dict[str, RetrievedChunk], results: list[RetrievedChunk]) -> None:
    for item in results:
        seen.setdefault(item.chunk.id, item)


def _run_tool(call: ToolCall, tools: list[Tool]) -> Message:
    by_name = {tool.__name__: tool for tool in tools}
    tool = by_name.get(call.name)
    if tool is None:
        available = ", ".join(by_name) or "none"
        content = f"Unknown tool '{call.name}'. Available tools: {available}."
    else:
        content = tool(**call.arguments)
    return Message(role="tool", content=content, tool_call_id=call.id)


def _final_reply(completion: Completion) -> AgentReply:
    if completion.reply is None:
        raise RuntimeError(
            "the model kept requesting tools after the tool-round cap instead of replying"
        )
    return completion.reply


def _to_answer(reply: AgentReply, seen: dict[str, RetrievedChunk], seed: list[RetrievedChunk]) -> Answer:
    if not reply.has_answer:
        return Answer(text=reply.answer, references=[])
    return Answer(text=reply.answer, references=_cited(seen, reply.citations) or list(seed))


def _cited(seen: dict[str, RetrievedChunk], citations: list[str]) -> list[RetrievedChunk]:
    references: list[RetrievedChunk] = []
    for chunk_id in citations:
        item = seen.get(chunk_id)
        if item is not None and item not in references:
            references.append(item)
    return references

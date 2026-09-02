from collections.abc import Sequence

from pydantic_ai.embeddings import Embedder, EmbeddingSettings
from pydantic_ai.embeddings.result import EmbeddingResult, EmbedInputType
from pydantic_ai.embeddings.test import TestEmbeddingModel

from retrieval.pydantic_ai_embedder import PydanticAiEmbeddingModel


class RecordingModel(TestEmbeddingModel):
    def __init__(self) -> None:
        super().__init__(dimensions=4)
        self.calls: list[tuple[list[str], EmbedInputType]] = []

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts = [inputs] if isinstance(inputs, str) else list(inputs)
        self.calls.append((texts, input_type))
        return await super().embed(inputs, input_type=input_type, settings=settings)


def make() -> tuple[RecordingModel, PydanticAiEmbeddingModel]:
    model = RecordingModel()
    return model, PydanticAiEmbeddingModel(Embedder(model), max_batch=2)


def test_documents_are_embedded_in_order_in_batches_of_at_most_max_batch():
    model, embedder = make()

    vectors = embedder.embed_documents(["a", "bb", "ccc", "dddd", "eeeee"])

    assert [texts for texts, _ in model.calls] == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert {input_type for _, input_type in model.calls} == {"document"}
    assert len(vectors) == 5
    assert all(isinstance(vector, list) and len(vector) == 4 for vector in vectors)


def test_query_is_embedded_as_a_query_and_returns_one_vector():
    model, embedder = make()

    vector = embedder.embed_query("qual graxa usar?")

    assert model.calls == [(["qual graxa usar?"], "query")]
    assert isinstance(vector, list) and len(vector) == 4


def test_no_documents_means_no_provider_call():
    model, embedder = make()

    assert embedder.embed_documents([]) == []
    assert model.calls == []

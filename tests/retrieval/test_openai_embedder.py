from types import SimpleNamespace

from retrieval.openai_embedder import OpenaiEmbeddingModel


class FakeOpenAI:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.models: set[str] = set()
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model: str, input: list[str]) -> SimpleNamespace:
        self.models.add(model)
        self.batches.append(list(input))
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text))])
            for i, text in enumerate(input)
        ]
        return SimpleNamespace(data=list(reversed(data)))


def test_embeds_texts_in_input_order_even_if_api_reorders():
    embedder = OpenaiEmbeddingModel(FakeOpenAI(), model="text-embedding-3-small")

    vectors = embedder.embed(["a", "bb", "ccc"])

    assert vectors == [[1.0], [2.0], [3.0]]


def test_large_inputs_are_split_into_api_sized_batches():
    client = FakeOpenAI()
    embedder = OpenaiEmbeddingModel(client, model="text-embedding-3-small", max_batch=2)

    vectors = embedder.embed(["a", "bb", "ccc", "dddd", "eeeee"])

    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert client.batches == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert client.models == {"text-embedding-3-small"}

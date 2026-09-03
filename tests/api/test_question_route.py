import httpx
import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError, UnexpectedModelBehavior
from qdrant_client.http.exceptions import UnexpectedResponse

from api.composition import get_agent_service
from api.main import app
from domain.errors import ToolRoundsExhausted
from domain.models import Answer, Chunk, Reference

QUESTION = "What is the power consumption of the motor?"


def _reference(quote: str, page: int) -> Reference:
    chunk = Chunk(
        id=f"c{page}",
        document_id="doc",
        filename="manual.pdf",
        text=f"Page {page} text. {quote} More page text.",
        page=page,
        section=None,
        index_in_doc=0,
    )
    return Reference(chunk=chunk, quote=quote)


class FakeAgentService:
    def __init__(self, answer: Answer) -> None:
        self._answer = answer
        self.questions: list[str] = []

    def answer(self, question: str) -> Answer:
        self.questions.append(question)
        return self._answer


@pytest.fixture
def service():
    fake = FakeAgentService(
        Answer(
            text="The motor's power consumption is 2.3 kW.",
            references=[
                _reference("the motor xxx has requires 2.3kw to operate at a 60hz line frequency", 7),
                _reference("Nominal voltage 380 V", 3),
            ],
        )
    )
    app.dependency_overrides[get_agent_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_asking_a_question_returns_the_challenge_contract(service):
    response = TestClient(app).post("/question", json={"question": QUESTION})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "The motor's power consumption is 2.3 kW.",
        "references": [
            "the motor xxx has requires 2.3kw to operate at a 60hz line frequency",
            "Nominal voltage 380 V",
        ],
    }
    assert service.questions == [QUESTION]


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "   "}, {}])
def test_blank_or_missing_question_is_rejected_and_never_reaches_the_service(service, body):
    response = TestClient(app).post("/question", json=body)

    assert response.status_code == 422
    assert service.questions == []


def test_llm_provider_failure_maps_to_502(service):
    def explode(question: str) -> Answer:
        raise ModelHTTPError(status_code=503, model_name="gpt-5-mini", body={"error": "overloaded"})

    service.answer = explode

    response = TestClient(app, raise_server_exceptions=False).post(
        "/question", json={"question": QUESTION}
    )

    assert response.status_code == 502
    assert "gpt-5-mini" in response.json()["detail"]


def test_every_llm_provider_failing_maps_to_502_naming_each_model(service):
    def explode(question: str) -> Answer:
        raise FallbackExceptionGroup(
            "All models from FallbackModel failed",
            [
                ModelHTTPError(status_code=503, model_name="gpt-5-mini", body={"error": "down"}),
                ModelHTTPError(status_code=429, model_name="gemini-3.5-flash", body={"error": "quota"}),
            ],
        )

    service.answer = explode

    response = TestClient(app, raise_server_exceptions=False).post(
        "/question", json={"question": QUESTION}
    )

    assert response.status_code == 502
    assert "gpt-5-mini" in response.json()["detail"]
    assert "gemini-3.5-flash" in response.json()["detail"]


def _failing(service, exc: Exception):
    def explode(question: str) -> Answer:
        raise exc

    service.answer = explode
    return TestClient(app, raise_server_exceptions=False).post("/question", json={"question": QUESTION})


def test_a_malformed_reply_after_the_retry_is_a_502_saying_so(service):
    response = _failing(service, UnexpectedModelBehavior("the LLM returned a malformed reply twice", body="{oops"))

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM reply unusable: the LLM returned a malformed reply twice"


def test_exhausted_tool_rounds_are_a_502(service):
    response = _failing(service, ToolRoundsExhausted(3))

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "LLM reply unusable: the model kept requesting tools after 3 round(s) instead of replying"
    )


def test_a_vector_store_error_on_the_question_path_is_a_503(service):
    response = _failing(
        service,
        UnexpectedResponse(
            status_code=500, reason_phrase="Internal Server Error", content=b"boom", headers=httpx.Headers()
        ),
    )

    assert response.status_code == 503
    assert response.json()["detail"].startswith("vector store unavailable at http://localhost:6333: ")


def test_any_other_failure_on_the_question_path_is_a_500_that_names_the_exception(service):
    response = _failing(service, KeyError("page"))

    assert response.status_code == 500
    assert response.json()["detail"] == "internal error: KeyError: 'page'"


def test_openai_connection_failure_on_the_question_path_maps_to_502(service):
    def explode(question: str) -> Answer:
        raise openai.APIConnectionError(
            request=httpx2.Request("POST", "https://api.openai.com/v1/embeddings")
        )

    service.answer = explode

    response = TestClient(app, raise_server_exceptions=False).post(
        "/question", json={"question": QUESTION}
    )

    assert response.status_code == 502
    assert "provider" in response.json()["detail"].lower()

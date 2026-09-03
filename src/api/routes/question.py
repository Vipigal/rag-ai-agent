from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.composition import get_agent_service
from api.errors import error_responses
from domain.services.agent_service import AgentService

router = APIRouter()

EXAMPLE_QUESTION = "What is the power consumption of the motor?"


class QuestionRequest(BaseModel):
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
        Field(
            description="The question, in any language. The answer comes back in the same language.",
            examples=[EXAMPLE_QUESTION],
        ),
    ]


class QuestionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "answer": "The document gives an example motor as “100 cv (75 kW)” operating at 100% nominal power, so its power consumption is 75 kW.",
                    "references": [
                        "Um motor elétrico, trifásico de 100 cv (75 kW), IV polos, operando com 100% da potência nominal, com fator de potência original de 0,87 e rendimento de 93,5%."
                    ],
                },
                {
                    "answer": "Desculpe, não encontrei a informação sobre a capital da Austrália nos documentos fornecidos.",
                    "references": [],
                },
            ]
        }
    )

    answer: str = Field(
        description="The answer grounded in the indexed documents, or a one-sentence refusal "
        "in the question's language when they do not contain it."
    )
    references: list[str] = Field(
        description="The passages the answer quotes, copied verbatim from the indexed pages "
        "and verified against them. Empty when the answer is a refusal."
    )


@router.post(
    "/question",
    summary="Ask a question over the indexed documents",
    description=(
        "Retrieves the pages most relevant to the question, lets the LLM answer only from "
        "them (it may search the index again with a reformulated query, at most a few times), "
        "and returns the answer with the passages it quoted as `references`. Each reference is "
        "a verbatim excerpt found in an indexed page, never a whole page and never invented; "
        "a question the documents do not answer gets a refusal and an empty list.\n\n"
        "Typical latency is a few seconds: one or two LLM calls plus retrieval."
    ),
    tags=["questions"],
    response_model=QuestionResponse,
    response_description="An answer with the passages that ground it, or a refusal.",
    responses=error_responses(
        422, 500, 502, 503, examples={422: "question: String should have at least 1 character"}
    ),
)
def ask_question(
    request: QuestionRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> QuestionResponse:
    answer = service.answer(request.question)
    return QuestionResponse(
        answer=answer.text,
        references=[reference.quote for reference in answer.references],
    )

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints

from api.composition import get_agent_service
from domain.services.agent_service import AgentService

router = APIRouter()


class QuestionRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class QuestionResponse(BaseModel):
    answer: str
    references: list[str]


@router.post("/question", response_model=QuestionResponse)
def ask_question(
    request: QuestionRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> QuestionResponse:
    answer = service.answer(request.question)
    return QuestionResponse(
        answer=answer.text,
        references=[reference.quote for reference in answer.references],
    )

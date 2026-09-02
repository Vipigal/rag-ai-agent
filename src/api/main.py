import logging

import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelAPIError

from api.routes.documents import router as documents_router
from api.routes.question import router as question_router

logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger().setLevel(logging.INFO)

app = FastAPI(title="RAG Agent API")
app.include_router(documents_router)
app.include_router(question_router)


@app.exception_handler(openai.OpenAIError)
def openai_error_handler(request: Request, exc: openai.OpenAIError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"OpenAI provider error: {exc}"},
    )


@app.exception_handler(ModelAPIError)
def llm_error_handler(request: Request, exc: ModelAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"LLM provider error: {exc}"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

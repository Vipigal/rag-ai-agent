import logging
from typing import Any

import openai
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAPIError,
    UnexpectedModelBehavior,
    UserError,
)
from qdrant_client.http.exceptions import ApiException

from api.composition import qdrant_url
from domain.errors import ToolRoundsExhausted, UnreadableDocument
from retrieval.qdrant_store import IncompatibleCollection

log = logging.getLogger(__name__)

DOCUMENTED_KEY_NAMES = {"GOOGLE_API_KEY": "GEMINI_API_KEY"}


class ErrorResponse(BaseModel):
    detail: str = Field(
        description="What went wrong, in one sentence, naming the file, model, variable or "
        "dependency involved and, where there is one, the fix."
    )


ERROR_DESCRIPTIONS: dict[int, tuple[str, str]] = {
    422: (
        "The request was rejected before any work was done: invalid body, or an upload that is not a PDF or cannot be read as one. Nothing is indexed.",
        "'notes.txt' is not a PDF file; only PDFs are accepted",
    ),
    500: (
        "An unexpected failure. The exception type and message are returned and the traceback is in the server log.",
        "internal error: KeyError: 'page'",
    ),
    502: (
        "An LLM or embedding provider failed after any fallback, or the LLM's reply could not be used. The provider or model is named.",
        "every LLM provider failed: status_code: 503, model_name: gpt-5-mini, body: {'error': 'overloaded'}; status_code: 429, model_name: gemini-3.5-flash, body: {'error': 'quota'}",
    ),
    503: (
        "A dependency is unavailable or misconfigured: the vector store cannot be reached or its collection does not match the configured embedding model, or a provider API key is missing. The message names the fix.",
        "vector store unavailable at http://qdrant:6333: [Errno 111] Connection refused",
    ),
}


def error_responses(*codes: int, examples: dict[int, str] | None = None) -> dict[int | str, dict[str, Any]]:
    overrides = examples or {}
    return {
        code: {
            "model": ErrorResponse,
            "description": ERROR_DESCRIPTIONS[code][0],
            "content": {
                "application/json": {
                    "example": {"detail": overrides.get(code, ERROR_DESCRIPTIONS[code][1])}
                }
            },
        }
        for code in codes
    }


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(UnreadableDocument, _unreadable_document)
    app.add_exception_handler(openai.OpenAIError, _openai_error)
    app.add_exception_handler(ModelAPIError, _model_api_error)
    app.add_exception_handler(FallbackExceptionGroup, _fallback_error)
    app.add_exception_handler(UnexpectedModelBehavior, _unusable_reply)
    app.add_exception_handler(ToolRoundsExhausted, _unusable_reply)
    app.add_exception_handler(ApiException, _vector_store_unavailable)
    app.add_exception_handler(IncompatibleCollection, _incompatible_collection)
    app.add_exception_handler(UserError, _provider_not_configured)
    app.add_exception_handler(Exception, _internal_error)


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = [
        f"{'.'.join(str(part) for part in error['loc'][1:] or error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]
    return _error(422, "; ".join(problems))


def _unreadable_document(request: Request, exc: Exception) -> JSONResponse:
    return _error(422, str(exc))


def _openai_error(request: Request, exc: Exception) -> JSONResponse:
    return _error(502, f"OpenAI provider error: {exc}")


def _model_api_error(request: Request, exc: Exception) -> JSONResponse:
    return _error(502, f"LLM provider error: {exc}")


def _fallback_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, FallbackExceptionGroup)
    causes = "; ".join(str(cause) for cause in exc.exceptions)
    return _error(502, f"every LLM provider failed: {causes}")


def _unusable_reply(request: Request, exc: Exception) -> JSONResponse:
    message = exc.message if isinstance(exc, UnexpectedModelBehavior) else str(exc)
    return _error(502, f"LLM reply unusable: {message}")


def _vector_store_unavailable(request: Request, exc: Exception) -> JSONResponse:
    return _error(503, f"vector store unavailable at {qdrant_url()}: {exc}")


def _incompatible_collection(request: Request, exc: Exception) -> JSONResponse:
    return _error(503, f"vector store collection incompatible: {exc}")


def _provider_not_configured(request: Request, exc: Exception) -> JSONResponse:
    message = str(exc)
    for library_name, documented_name in DOCUMENTED_KEY_NAMES.items():
        message = message.replace(library_name, documented_name)
    return _error(503, f"provider not configured: {message}")


def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    detail = f"internal error: {type(exc).__name__}: {exc}"
    log.exception("%s %s failed: %s", request.method, request.url.path, detail, exc_info=exc)
    return _error(500, detail)

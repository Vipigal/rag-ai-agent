import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.composition import validate_configuration
from api.errors import register_exception_handlers
from api.routes.documents import router as documents_router
from api.routes.health import router as health_router
from api.routes.question import router as question_router

logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger().setLevel(logging.INFO)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    try:
        validate_configuration()
    except Exception as error:
        log.critical("startup failed: %s", error)
        raise
    yield

DESCRIPTION = """Question answering over PDF manuals, grounded in the documents you upload.

Two steps:

1. **`POST /documents`** — upload one or more PDFs. Each page is extracted, cleaned, chunked
   and embedded into the vector store. Re-uploading a file is idempotent.
2. **`POST /question`** — ask in any language. The relevant chunks are retrieved, the LLM
   answers only from them, and `references` carries the passages it quoted verbatim.
   When the documents do not support an answer the reply is a refusal with empty `references`.

`GET /health` tells you whether the vector store and the configured models are ready.

Every error body has the same shape, `{"detail": "..."}`, and the status says who is at
fault: `422` the request, `502` an LLM or embedding provider, `503` a dependency or the
configuration (the message names the fix), `500` anything unexpected (the exception is named).

Setup, examples and the design are in the repository README.
"""

TAGS = [
    {"name": "documents", "description": "Upload PDFs to be indexed."},
    {"name": "questions", "description": "Ask questions over the indexed documents."},
    {"name": "operations", "description": "Readiness and diagnostics."},
]

app = FastAPI(
    title="RAG Agent API",
    summary="Upload PDF manuals, ask questions, get answers with the passages they came from.",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(documents_router)
app.include_router(question_router)
app.include_router(health_router)

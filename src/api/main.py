import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes.documents import router as documents_router

app = FastAPI(title="RAG Agent API")
app.include_router(documents_router)


@app.exception_handler(openai.OpenAIError)
def openai_error_handler(request: Request, exc: openai.OpenAIError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"embedding provider error: {exc}"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

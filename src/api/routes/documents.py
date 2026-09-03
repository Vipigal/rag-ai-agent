from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from api.composition import get_ingestion_service
from domain.services.ingestion_pipeline import IngestionPipelineService

router = APIRouter()


class DocumentsResponse(BaseModel):
    message: str
    documents_indexed: int
    total_chunks: int


@router.post("/documents", response_model=DocumentsResponse)
def upload_documents(
    files: list[UploadFile],
    service: Annotated[IngestionPipelineService, Depends(get_ingestion_service)],
) -> DocumentsResponse:
    contents: list[tuple[str, bytes]] = []
    for file in files:
        data = file.file.read()
        if not data.startswith(b"%PDF"):
            raise HTTPException(
                status_code=422,
                detail=f"'{file.filename}' is not a PDF file; only PDFs are accepted",
            )
        contents.append((file.filename or "unnamed.pdf", data))

    result = service.ingest(contents)
    return DocumentsResponse(
        message="Documents processed successfully",
        documents_indexed=result.documents_indexed,
        total_chunks=result.total_chunks,
    )

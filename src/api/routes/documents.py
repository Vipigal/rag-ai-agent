from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from api.composition import get_ingestion_service
from api.errors import error_responses
from domain.services.ingestion_pipeline import IngestionPipelineService

router = APIRouter()


class DocumentsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "Documents processed successfully",
                    "documents_indexed": 2,
                    "total_chunks": 128,
                }
            ]
        }
    )

    message: str = Field(description="Always `Documents processed successfully` on success.")
    documents_indexed: int = Field(description="How many of the uploaded files were indexed.")
    total_chunks: int = Field(
        description="Chunks written to the vector store across all files. One chunk per page "
        "with text; a scanned PDF without a text layer contributes 0."
    )


@router.post(
    "/documents",
    summary="Upload and index PDF documents",
    description=(
        "Upload one or more PDF files as `multipart/form-data` under the field `files` "
        "(repeat the field for several). Each file is validated, its pages extracted and "
        "cleaned, one chunk per page is embedded and stored with its provenance (file, page, "
        "section). Uploading the same file again is idempotent: chunk ids are content-addressed.\n\n"
        "The upload is all-or-nothing: a file that is not a PDF, or cannot be read as one, "
        "rejects the whole request with `422` naming the file, and nothing is indexed. "
        "Indexing the four sample manuals takes about a minute; progress is logged per file."
    ),
    tags=["documents"],
    response_model=DocumentsResponse,
    response_description="Every file was indexed.",
    responses=error_responses(422, 500, 502, 503),
)
def upload_documents(
    files: Annotated[
        list[UploadFile],
        File(description="One or more PDF files. Repeat the field to upload several at once."),
    ],
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

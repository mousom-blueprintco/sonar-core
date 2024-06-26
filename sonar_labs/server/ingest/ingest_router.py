from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, Field
from pathlib import Path
import tempfile

from sonar_labs.server.ingest.ingest_service import IngestService
from sonar_labs.server.ingest.model import IngestedDoc
from sonar_labs.server.utils.auth import authenticated

ingest_router = APIRouter(prefix="/v1", dependencies=[Depends(authenticated)])


class IngestTextBody(BaseModel):
    file_name: str = Field(examples=["Avatar: The Last Airbender"])
    text: str = Field(
        examples=[
            "Avatar is set in an Asian and Arctic-inspired world in which some "
            "people can telekinetically manipulate one of the four elements—water, "
            "earth, fire or air—through practices known as 'bending', inspired by "
            "Chinese martial arts."
        ]
    )


class IngestResponse(BaseModel):
    object: Literal["list"]
    model: Literal["sonar-labs"]
    data: list[IngestedDoc]
    
class IngestCountResponse(BaseModel):
    object: Literal["count"]
    model: Literal["sonar-labs"]
    data: dict  


@ingest_router.post("/ingest", tags=["Ingestion"], deprecated=True)
def ingest(request: Request, file: UploadFile) -> IngestResponse:
    """Ingests and processes a file.

    Deprecated. Use ingest/file instead.
    """
    return ingest_file(request, file)


@ingest_router.post("/ingest/file", tags=["Ingestion"])
async def ingest_file(request: Request, file: UploadFile) -> IngestResponse:
    """Ingests and processes a file, storing its chunks to be used as context.

    The context obtained from files is later used in
    `/chat/completions`, `/completions`, and `/chunks` APIs.

    Most common document
    formats are supported, but you may be prompted to install an extra dependency to
    manage a specific file type.

    A file can generate different Documents (for example a PDF generates one Document
    per page). All Documents IDs are returned in the response, together with the
    extracted Metadata (which is later used to improve context retrieval). Those IDs
    can be used to filter the context used to create responses in
    `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    project_id = request.headers.get("X-Project-Id", None)
    user_id = request.headers.get("X-User-Id", None)
    file_id = request.headers.get("X-File-Id", None)
    org_id = request.headers.get("X-Org-Id", None)

    if not project_id or not user_id or not file_id:
        raise HTTPException(status_code=400, detail="projectId, userId, orgId and fileId are required")

    if file.filename is None:
        raise HTTPException(status_code=400, detail="No file name provided")

    doc_ids_to_delete = [
        ingested_document.doc_id 
        for ingested_document in service.list_ingested() 
        if ingested_document.doc_metadata and ingested_document.doc_metadata.get("file_name") == file.filename
        and ingested_document.doc_metadata.get("project_id") == project_id 
        and ingested_document.doc_metadata.get("user_id") == user_id
        and ingested_document.doc_metadata.get("org_id") == org_id
    ]
    
    for doc_id in doc_ids_to_delete:
        service.delete(doc_id)
    
    
    ingested_documents = service.ingest_bin_data(file.filename, file.file, file_id, project_id, user_id, org_id)
    return IngestResponse(object="list", model="sonar-labs", data=ingested_documents)

@ingest_router.post("/ingest/files", tags=["Ingestions"])
async def ingest_files(request: Request, files: list[UploadFile] = File(...), file_ids: list[str] = Form(...)) -> IngestResponse:
    """Ingests and processes multiple files, storing its chunks to be used as context.

    The context obtained from files is later used in
    `/chat/completions`, `/completions`, and `/chunks` APIs.

    Most common document
    formats are supported, but you may be prompted to install an extra dependency to
    manage a specific file type.

    All files can generate different Documents (for example a PDF generates one Document
    per page). All Documents IDs are returned in the response, together with the
    extracted Metadata (which is later used to improve context retrieval). Those IDs
    can be used to filter the context used to create responses in
    `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    temp_paths = []
    project_id = request.headers.get("X-Project-Id", None)
    user_id = request.headers.get("X-User-Id", None)
    org_id = request.headers.get("X-Org-Id", None)

    if not project_id or not user_id:
        raise HTTPException(status_code=400, detail="projectId, userId and orgId are required")
    try:
        # Create temporary files for each uploaded file
        # for file in files:
        #     temp_file = tempfile.NamedTemporaryFile(delete=False)
        #     temp_file.write(await file.read())
        #     temp_path = Path(temp_file.name)
        #     temp_paths.append((file.filename, temp_path))
        #     temp_file.close()
        
        for file, file_id in zip(files, file_ids):
               with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                   temp_file.write(await file.read())
                   temp_path = Path(temp_file.name)
                   temp_paths.append((file.filename, temp_path, file_id))

        service = request.state.injector.get(IngestService)

        # Remove all existing Documents with name identical to all newly uploaded files:
        # file_names = [name for name, _ in temp_paths]
        file_names = [name for name, _, _ in temp_paths]

        doc_ids_to_delete = [
            ingested_document.doc_id 
            for ingested_document in service.list_ingested() 
            if ingested_document.doc_metadata 
            and ingested_document.doc_metadata.get("file_name") in file_names 
            and ingested_document.doc_metadata.get("project_id") == project_id 
            and ingested_document.doc_metadata.get("user_id") == user_id
            and ingested_document.doc_metadata.get("org_id") == org_id
        ]

        for doc_id in doc_ids_to_delete:
            service.delete(doc_id)

        if not file_names:
            raise HTTPException(400, "No file name provided")

        # ingested_documents = service.bulk_ingest([(name, path) for name, path in temp_paths], project_id, user_id)
        ingested_documents = service.bulk_ingest([(name, path, file_id) for name, path, file_id in temp_paths], project_id, user_id, org_id)
        return IngestResponse(object= "list", model= "sonar-labs", data= ingested_documents)

    finally:
        # Clean up temporary files
        # for _, temp_path in temp_paths:
        #     temp_path.unlink()
        for _, temp_path, _ in temp_paths:
            temp_path.unlink()

    


@ingest_router.post("/ingest/text", tags=["Ingestion"])
def ingest_text(request: Request, body: IngestTextBody) -> IngestResponse:
    """Ingests and processes a text, storing its chunks to be used as context.

    The context obtained from files is later used in
    `/chat/completions`, `/completions`, and `/chunks` APIs.

    A Document will be generated with the given text. The Document
    ID is returned in the response, together with the
    extracted Metadata (which is later used to improve context retrieval). That ID
    can be used to filter the context used to create responses in
    `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    if len(body.file_name) == 0:
        raise HTTPException(400, "No file name provided")
    ingested_documents = service.ingest_text(body.file_name, body.text)
    return IngestResponse(object="list", model="sonar-labs", data=ingested_documents)


@ingest_router.get("/ingest/list", tags=["Ingestion"])
def list_ingested(request: Request) -> IngestResponse:
    """Lists already ingested Documents including their Document ID and metadata.

    Those IDs can be used to filter the context used to create responses
    in `/chat/completions`, `/completions`, and `/chunks` APIs.
    """
    service = request.state.injector.get(IngestService)
    ingested_documents = service.list_ingested()
    return IngestResponse(object="list", model="sonar-labs", data=ingested_documents)


@ingest_router.delete("/ingest/{doc_id}", tags=["Ingestion"])
def delete_ingested(request: Request, doc_id: str) -> None:
    """Delete the specified ingested Document.

    The `doc_id` can be obtained from the `GET /ingest/list` endpoint.
    The document will be effectively deleted from your storage context.
    """
    service = request.state.injector.get(IngestService)
    service.delete(doc_id)
    
@ingest_router.delete("/ingest/delete/{file_id}", tags=["Ingestion"])
def delete_ingested_doc(request: Request, file_id: str) -> None:
    """Delete the specified ingested Document.

    The `file_id` can be obtained from the `GET /ingest/list` endpoint.
    The document will be effectively deleted from your storage context.
    """
    
    project_id = request.headers.get("X-Project-Id", None)
    user_id = request.headers.get("X-User-Id", None)
    org_id = request.headers.get("X-Org-Id", None)
    if not project_id or not user_id or not org_id:
        raise HTTPException(status_code=400, detail="projectId, userId and orgId are required")
    
    service = request.state.injector.get(IngestService)
    
    doc_ids_to_delete = [
        ingested_document.doc_id 
        for ingested_document in service.list_ingested() 
        if ingested_document.doc_metadata and ingested_document.doc_metadata.get("file_id") == file_id
        and ingested_document.doc_metadata.get("project_id") == project_id 
        and ingested_document.doc_metadata.get("user_id") == user_id
        and ingested_document.doc_metadata.get("org_id") == org_id
    ]
    
    for doc_id in doc_ids_to_delete:
            service.delete(doc_id)
    

@ingest_router.get("/ingest/file/status", tags=["Ingestion"])
async def ingest_file_status(request: Request) -> IngestCountResponse:
    """get status for ingested Documents.
    """
    service = request.state.injector.get(IngestService)
    org_id = request.headers.get("X-Org-Id", None)
    project_id = request.headers.get("X-Project-Id", None)
    user_id = request.headers.get("X-User-Id", None)
    file_id = request.headers.get("X-File-Id", None)
    doc_count = request.headers.get("X-Doc-Count", None)
    

    if not project_id or not user_id or not file_id or not doc_count:
        raise HTTPException(status_code=400, detail="orgId, projectId, userId, fileId and docCount are required")

    doc_ids = [
    ingested_document.doc_id 
    for ingested_document in service.list_ingested()
    if (ingested_document.doc_metadata and 
        ingested_document.doc_metadata.get("file_id") == file_id and 
        ingested_document.doc_metadata.get("user_id") == user_id and 
        ingested_document.doc_metadata.get("project_id") == project_id and
        ingested_document.doc_metadata.get("org_id") == org_id)
    ]


    count_ingested_documents = len(doc_ids)
    print(count_ingested_documents)

    if count_ingested_documents == int(doc_count):
        return IngestCountResponse(
            object="count",
            model="sonar-labs",
            data={"count": count_ingested_documents, "status": True})   
    else:
        return IngestCountResponse(
            object="count",
            model="sonar-labs",
            data={"count": count_ingested_documents, "status": False})  
     

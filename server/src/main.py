import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, DIST_DIR
from .models import (
    KnowledgeDocumentPayload,
    RunRecord,
    RunRequest,
    RunResponse,
    WorkflowPayload,
    WorkflowRecord,
    WorkflowRunRequest,
    WorkflowValidationResult,
)
from .knowledge import delete_knowledge_document, knowledge_status, list_knowledge_documents, save_knowledge_document
from .logging_config import configure_logging
from .runner import get_provider_status, simulate_run
from .storage import WorkflowStore
from .validation import validate_workflow


configure_logging()
logger = logging.getLogger("workflow_studio.api")
app = FastAPI(title="Workflow Studio API", version="0.1.0")
store = WorkflowStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/provider-status")
def provider_status() -> dict[str, str | bool]:
    return get_provider_status()


@app.get("/api/knowledge/status")
def get_knowledge_status() -> dict[str, int | str]:
    return knowledge_status()


@app.get("/api/knowledge/documents")
def get_knowledge_documents() -> list[dict[str, int | str]]:
    return list_knowledge_documents()


@app.post("/api/knowledge/documents", status_code=201)
def upload_knowledge_document(payload: KnowledgeDocumentPayload) -> dict[str, int | str]:
    try:
        return save_knowledge_document(payload.filename, payload.content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/knowledge/documents/{filename}", status_code=204)
def remove_knowledge_document(filename: str) -> None:
    try:
        deleted = delete_knowledge_document(filename)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge document not found")


@app.get("/api/workflows", response_model=list[WorkflowRecord])
def list_workflows() -> list[WorkflowRecord]:
    return store.list_workflows()


def raise_on_validation_errors(payload: WorkflowPayload) -> WorkflowValidationResult:
    result = validate_workflow(payload)
    if result.errors:
        raise HTTPException(status_code=400, detail=result.model_dump())
    return result


@app.post("/api/workflows/validate", response_model=WorkflowValidationResult)
def validate_workflow_payload(payload: WorkflowPayload) -> WorkflowValidationResult:
    return validate_workflow(payload)


@app.post("/api/workflows", response_model=WorkflowRecord, status_code=201)
def create_workflow(payload: WorkflowPayload) -> WorkflowRecord:
    raise_on_validation_errors(payload)
    return store.create_workflow(payload)


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(workflow_id: str) -> WorkflowRecord:
    workflow = store.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def update_workflow(workflow_id: str, payload: WorkflowPayload) -> WorkflowRecord:
    raise_on_validation_errors(payload)
    workflow = store.update_workflow(workflow_id, payload)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.delete("/api/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str) -> None:
    if not store.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")


@app.post("/api/runs", response_model=RunResponse)
def run_workflow(payload: RunRequest) -> RunResponse:
    raise_on_validation_errors(payload.workflow)
    return simulate_run(payload.workflow, payload.input_text)


@app.get("/api/runs", response_model=list[RunRecord])
def list_runs(workflow_id: str | None = None) -> list[RunRecord]:
    return store.list_runs(workflow_id)


@app.delete("/api/runs", status_code=204)
def delete_runs(workflow_id: str | None = None) -> None:
    store.delete_runs(workflow_id)


@app.get("/api/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    if not store.delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")


@app.post("/api/workflows/{workflow_id}/runs", response_model=RunRecord, status_code=201)
def run_stored_workflow(workflow_id: str, payload: WorkflowRunRequest) -> RunRecord:
    workflow = store.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    raise_on_validation_errors(workflow)
    response = simulate_run(workflow, payload.input_text)
    return store.create_run(workflow.id, workflow.name, payload.input_text, response)


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")

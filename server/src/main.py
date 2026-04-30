import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, DIST_DIR
from .auth import AuthService, current_token, login, register, require_auth, set_auth_service
from .models import (
    AuthPayload,
    AuthResponse,
    KnowledgeDocumentPayload,
    RunRecord,
    RunRequest,
    RunResponse,
    WorkflowPayload,
    WorkflowRecord,
    WorkflowRunRequest,
    WorkflowValidationResult,
    UserRecord,
)
from .knowledge import delete_knowledge_document, knowledge_status, list_knowledge_documents, save_knowledge_document
from .logging_config import configure_logging
from .runner import get_provider_status, simulate_run
from .storage import default_store
from .validation import validate_workflow


configure_logging()
logger = logging.getLogger("workflow_studio.api")
app = FastAPI(title="Workflow Studio API", version="0.1.0")
store = default_store
auth_service = AuthService(store)
set_auth_service(auth_service)
default_user_id = auth_service.ensure_default_user()
store.assign_unowned_records(default_user_id)

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
def get_knowledge_status(user: UserRecord = Depends(require_auth)) -> dict[str, int | str]:
    return knowledge_status(user.id)


@app.get("/api/knowledge/documents")
def get_knowledge_documents(user: UserRecord = Depends(require_auth)) -> list[dict[str, int | str]]:
    return list_knowledge_documents(user.id)


@app.post("/api/knowledge/documents", status_code=201)
def upload_knowledge_document(
    payload: KnowledgeDocumentPayload,
    user: UserRecord = Depends(require_auth),
) -> dict[str, int | str]:
    try:
        return save_knowledge_document(payload.filename, payload.content, user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/knowledge/documents/{filename}", status_code=204)
def remove_knowledge_document(filename: str, user: UserRecord = Depends(require_auth)) -> None:
    try:
        deleted = delete_knowledge_document(filename, user.id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge document not found")


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register_user(payload: AuthPayload) -> AuthResponse:
    return register(payload)


@app.post("/api/auth/login", response_model=AuthResponse)
def login_user(payload: AuthPayload) -> AuthResponse:
    return login(payload)


@app.get("/api/auth/me", response_model=UserRecord)
def get_me(user: UserRecord = Depends(require_auth)) -> UserRecord:
    return user


@app.post("/api/auth/logout", status_code=204)
def logout_user(token: str = Depends(current_token)) -> None:
    auth_service.logout(token)


@app.get("/api/workflows", response_model=list[WorkflowRecord])
def list_workflows(user: UserRecord = Depends(require_auth)) -> list[WorkflowRecord]:
    return store.list_workflows(user.id)


def raise_on_validation_errors(payload: WorkflowPayload) -> WorkflowValidationResult:
    result = validate_workflow(payload)
    if result.errors:
        raise HTTPException(status_code=400, detail=result.model_dump())
    return result


@app.post("/api/workflows/validate", response_model=WorkflowValidationResult)
def validate_workflow_payload(
    payload: WorkflowPayload,
    _: UserRecord = Depends(require_auth),
) -> WorkflowValidationResult:
    return validate_workflow(payload)


@app.post("/api/workflows", response_model=WorkflowRecord, status_code=201)
def create_workflow(payload: WorkflowPayload, user: UserRecord = Depends(require_auth)) -> WorkflowRecord:
    raise_on_validation_errors(payload)
    return store.create_workflow(payload, user.id)


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(workflow_id: str, user: UserRecord = Depends(require_auth)) -> WorkflowRecord:
    workflow = store.get_workflow(workflow_id, user.id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def update_workflow(
    workflow_id: str,
    payload: WorkflowPayload,
    user: UserRecord = Depends(require_auth),
) -> WorkflowRecord:
    raise_on_validation_errors(payload)
    workflow = store.update_workflow(workflow_id, payload, user.id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.delete("/api/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, user: UserRecord = Depends(require_auth)) -> None:
    if not store.delete_workflow(workflow_id, user.id):
        raise HTTPException(status_code=404, detail="Workflow not found")


@app.post("/api/runs", response_model=RunResponse)
def run_workflow(payload: RunRequest, user: UserRecord = Depends(require_auth)) -> RunResponse:
    raise_on_validation_errors(payload.workflow)
    return simulate_run(payload.workflow, payload.input_text, user.id)


@app.get("/api/runs", response_model=list[RunRecord])
def list_runs(
    workflow_id: str | None = None,
    user: UserRecord = Depends(require_auth),
) -> list[RunRecord]:
    return store.list_runs(user.id, workflow_id)


@app.delete("/api/runs", status_code=204)
def delete_runs(workflow_id: str | None = None, user: UserRecord = Depends(require_auth)) -> None:
    store.delete_runs(user.id, workflow_id)


@app.get("/api/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str, user: UserRecord = Depends(require_auth)) -> RunRecord:
    run = store.get_run(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str, user: UserRecord = Depends(require_auth)) -> None:
    if not store.delete_run(run_id, user.id):
        raise HTTPException(status_code=404, detail="Run not found")


@app.post("/api/workflows/{workflow_id}/runs", response_model=RunRecord, status_code=201)
def run_stored_workflow(
    workflow_id: str,
    payload: WorkflowRunRequest,
    user: UserRecord = Depends(require_auth),
) -> RunRecord:
    workflow = store.get_workflow(workflow_id, user.id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    raise_on_validation_errors(workflow)
    response = simulate_run(workflow, payload.input_text, user.id)
    return store.create_run(workflow.id, user.id, workflow.name, payload.input_text, response)


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")

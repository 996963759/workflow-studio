import logging
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS, DIST_DIR
from .auth import AuthService, current_token, login, register, require_auth, set_auth_service
from .models import (
    AuthPayload,
    AuthResponse,
    KnowledgeDocumentPayload,
    ModelConfigPayload,
    ModelConfigRecord,
    ModelConfigTestResponse,
    RunRecord,
    RunJobRecord,
    RunRequest,
    RunResponse,
    WorkspaceCreatePayload,
    WorkspaceMemberPayload,
    WorkspaceMemberRecord,
    WorkspaceRecord,
    WorkflowPayload,
    WorkflowRecord,
    WorkflowRunRequest,
    WorkflowValidationResult,
    UserRecord,
)
from .jobs import RunJobQueue
from .external_rag import external_rag_status
from .knowledge import (
    delete_knowledge_document,
    knowledge_status,
    list_knowledge_documents,
    save_knowledge_document,
    set_knowledge_session_factory,
)
from .logging_config import configure_logging
from .runner import get_provider_status, simulate_run
from .storage import default_store
from .validation import validate_workflow


configure_logging()
logger = logging.getLogger("workflow_studio.api")
app = FastAPI(title="Workflow Studio API", version="0.1.0")
store = default_store
set_knowledge_session_factory(store.SessionLocal)
auth_service = AuthService(store)
set_auth_service(auth_service)
default_user_id = auth_service.ensure_default_user()
store.assign_unowned_records(default_user_id)
job_queue = RunJobQueue(store)

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
    database = store.engine.url.get_backend_name() if store.engine else "unknown"
    return {"status": "ok", "database": database, "queue_backend": job_queue.backend}


@app.get("/api/provider-status")
def provider_status() -> dict[str, str | bool]:
    status = get_provider_status()
    rag_status = external_rag_status()
    return {
        **status,
        "external_rag_enabled": rag_status.enabled,
        "external_rag_provider": rag_status.provider,
        "external_rag_base_url": rag_status.base_url,
    }


def resolve_workspace_id(user: UserRecord, workspace_id: str | None = Header(default=None, alias="X-Workspace-Id")) -> str:
    if workspace_id:
        if not store.can_access_workspace(workspace_id, user.id):
            raise HTTPException(status_code=403, detail="Workspace access denied")
        return workspace_id
    return store.ensure_default_workspace(user.id, user.username)


def require_workspace_role(minimum_role: str):
    def dependency(
        user: UserRecord = Depends(require_auth),
        workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    ) -> tuple[UserRecord, str]:
        resolved_workspace_id = resolve_workspace_id(user, workspace_id)
        if not store.can_access_workspace(resolved_workspace_id, user.id, minimum_role):
            raise HTTPException(status_code=403, detail="Insufficient workspace role")
        return user, resolved_workspace_id

    return dependency


WorkspaceContext = tuple[UserRecord, str]


def workspace_model_configs(workspace_id: str) -> dict[str, dict[str, str | bool]]:
    configs: dict[str, dict[str, str | bool]] = {}
    deepseek_config = store.get_runtime_model_config(workspace_id, "deepseek")
    if deepseek_config:
        configs["deepseek"] = deepseek_config
    return configs


@app.get("/api/workspaces", response_model=list[WorkspaceRecord])
def list_workspaces(user: UserRecord = Depends(require_auth)) -> list[WorkspaceRecord]:
    store.ensure_default_workspace(user.id, user.username)
    return store.list_workspaces(user.id)


@app.post("/api/workspaces", response_model=WorkspaceRecord, status_code=201)
def create_workspace(payload: WorkspaceCreatePayload, user: UserRecord = Depends(require_auth)) -> WorkspaceRecord:
    return store.create_workspace(user.id, payload.name)


@app.get("/api/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberRecord])
def list_workspace_members(workspace_id: str, user: UserRecord = Depends(require_auth)) -> list[WorkspaceMemberRecord]:
    members = store.list_workspace_members(workspace_id, user.id)
    if members is None:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return members


@app.post("/api/workspaces/{workspace_id}/members", response_model=WorkspaceMemberRecord)
def upsert_workspace_member(
    workspace_id: str,
    payload: WorkspaceMemberPayload,
    user: UserRecord = Depends(require_auth),
) -> WorkspaceMemberRecord:
    member = store.upsert_workspace_member(workspace_id, user.id, payload.username, payload.role)
    if member is None:
        raise HTTPException(status_code=404, detail="User not found or workspace access denied")
    return member


@app.get("/api/model-configs/{provider}", response_model=ModelConfigRecord)
def get_model_config(
    provider: str,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> ModelConfigRecord:
    if provider != "deepseek":
        raise HTTPException(status_code=400, detail="Unsupported model provider")
    user, workspace_id = context
    config = store.get_model_config(workspace_id, user.id, provider)
    if config is None:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return config


@app.put("/api/model-configs/{provider}", response_model=ModelConfigRecord)
def save_model_config(
    provider: str,
    payload: ModelConfigPayload,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> ModelConfigRecord:
    if provider != "deepseek":
        raise HTTPException(status_code=400, detail="Unsupported model provider")
    user, workspace_id = context
    try:
        config = store.upsert_model_config(workspace_id, user.id, provider, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if config is None:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return config


@app.post("/api/model-configs/{provider}/test", response_model=ModelConfigTestResponse)
def test_model_config(
    provider: str,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> ModelConfigTestResponse:
    if provider != "deepseek":
        raise HTTPException(status_code=400, detail="Unsupported model provider")
    _, workspace_id = context
    runtime_config = store.get_runtime_model_config(workspace_id, provider)
    if not runtime_config:
        return ModelConfigTestResponse(ok=False, message="当前团队空间还没有可用的 DeepSeek Key。", provider=provider, model="")
    return ModelConfigTestResponse(
        ok=True,
        message="DeepSeek 配置已保存。运行工作流时会优先使用当前团队空间配置。",
        provider=provider,
        model=str(runtime_config.get("model") or ""),
    )


@app.get("/api/knowledge/status")
def get_knowledge_status(context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> dict[str, int | str]:
    user, workspace_id = context
    return knowledge_status(user.id, workspace_id)


@app.get("/api/knowledge/documents")
def get_knowledge_documents(context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> list[dict[str, int | str]]:
    user, workspace_id = context
    return list_knowledge_documents(user.id, workspace_id)


@app.post("/api/knowledge/documents", status_code=201)
def upload_knowledge_document(
    payload: KnowledgeDocumentPayload,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> dict[str, int | str]:
    user, workspace_id = context
    try:
        return save_knowledge_document(payload.filename, payload.content, user.id, workspace_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/knowledge/documents/{filename}", status_code=204)
def remove_knowledge_document(
    filename: str,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> None:
    user, workspace_id = context
    try:
        deleted = delete_knowledge_document(filename, user.id, workspace_id)
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
def list_workflows(context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> list[WorkflowRecord]:
    user, workspace_id = context
    return store.list_workflows(user.id, workspace_id)


def raise_on_validation_errors(payload: WorkflowPayload) -> WorkflowValidationResult:
    result = validate_workflow(payload)
    if result.errors:
        raise HTTPException(status_code=400, detail=result.model_dump())
    return result


@app.post("/api/workflows/validate", response_model=WorkflowValidationResult)
def validate_workflow_payload(
    payload: WorkflowPayload,
    _: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> WorkflowValidationResult:
    return validate_workflow(payload)


@app.post("/api/workflows", response_model=WorkflowRecord, status_code=201)
def create_workflow(
    payload: WorkflowPayload,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> WorkflowRecord:
    user, workspace_id = context
    raise_on_validation_errors(payload)
    return store.create_workflow(payload, user.id, workspace_id)


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(
    workflow_id: str,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> WorkflowRecord:
    user, workspace_id = context
    workflow = store.get_workflow(workflow_id, user.id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def update_workflow(
    workflow_id: str,
    payload: WorkflowPayload,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> WorkflowRecord:
    user, workspace_id = context
    raise_on_validation_errors(payload)
    workflow = store.update_workflow(workflow_id, payload, user.id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.delete("/api/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, context: WorkspaceContext = Depends(require_workspace_role("editor"))) -> None:
    user, workspace_id = context
    if not store.delete_workflow(workflow_id, user.id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow not found")


@app.post("/api/runs", response_model=RunResponse)
def run_workflow(payload: RunRequest, context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> RunResponse:
    user, workspace_id = context
    raise_on_validation_errors(payload.workflow)
    return simulate_run(payload.workflow, payload.input_text, user.id, workspace_id, workspace_model_configs(workspace_id))


@app.get("/api/runs", response_model=list[RunRecord])
def list_runs(
    workflow_id: str | None = None,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> list[RunRecord]:
    user, workspace_id = context
    return store.list_runs(user.id, workflow_id, workspace_id)


@app.delete("/api/runs", status_code=204)
def delete_runs(
    workflow_id: str | None = None,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> None:
    user, workspace_id = context
    store.delete_runs(user.id, workflow_id, workspace_id)


@app.get("/api/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str, context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> RunRecord:
    user, workspace_id = context
    run = store.get_run(run_id, user.id, workspace_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str, context: WorkspaceContext = Depends(require_workspace_role("editor"))) -> None:
    user, workspace_id = context
    if not store.delete_run(run_id, user.id, workspace_id):
        raise HTTPException(status_code=404, detail="Run not found")


@app.post("/api/workflows/{workflow_id}/runs", response_model=RunRecord, status_code=201)
def run_stored_workflow(
    workflow_id: str,
    payload: WorkflowRunRequest,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> RunRecord:
    user, workspace_id = context
    workflow = store.get_workflow(workflow_id, user.id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    raise_on_validation_errors(workflow)
    response = simulate_run(workflow, payload.input_text, user.id, workspace_id, workspace_model_configs(workspace_id))
    return store.create_run(workflow.id, user.id, workflow.name, payload.input_text, response, workspace_id)


@app.post("/api/workflows/{workflow_id}/run-jobs", response_model=RunJobRecord, status_code=202)
def enqueue_stored_workflow_run(
    workflow_id: str,
    payload: WorkflowRunRequest,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> RunJobRecord:
    user, workspace_id = context
    workflow = store.get_workflow(workflow_id, user.id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    raise_on_validation_errors(workflow)
    return job_queue.enqueue(user.id, workspace_id, workflow_id, payload.input_text)


@app.get("/api/run-jobs", response_model=list[RunJobRecord])
def list_run_jobs(
    workflow_id: str | None = None,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> list[RunJobRecord]:
    user, workspace_id = context
    return store.list_run_jobs(user.id, workflow_id, workspace_id)


@app.get("/api/run-jobs/{job_id}", response_model=RunJobRecord)
def get_run_job(job_id: str, context: WorkspaceContext = Depends(require_workspace_role("viewer"))) -> RunJobRecord:
    user, workspace_id = context
    job = store.get_run_job(job_id, user.id, workspace_id)
    if not job:
        raise HTTPException(status_code=404, detail="Run job not found")
    return job


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")

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
    AuditLogRecord,
    KnowledgeDocumentPayload,
    ModelConfigPayload,
    ModelConfigRecord,
    ModelConfigTestResponse,
    RunRecord,
    RunJobRecord,
    RunRequest,
    RunResponse,
    WorkspaceCreatePayload,
    WorkspaceInvitationAcceptPayload,
    WorkspaceInvitationCreatePayload,
    WorkspaceInvitationRecord,
    WorkspaceMemberPayload,
    WorkspaceMemberRecord,
    WorkspaceRecord,
    WorkflowPayload,
    WorkflowRecord,
    WorkflowRunRequest,
    WorkflowVersionCreatePayload,
    WorkflowVersionRecord,
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
    aliyun_config = store.get_runtime_model_config(workspace_id, "aliyun")
    if aliyun_config:
        configs["aliyun"] = aliyun_config
    return configs


def ensure_supported_model_provider(provider: str) -> None:
    if provider not in {"deepseek", "aliyun"}:
        raise HTTPException(status_code=400, detail="Unsupported model provider")


@app.get("/api/workspaces", response_model=list[WorkspaceRecord])
def list_workspaces(user: UserRecord = Depends(require_auth)) -> list[WorkspaceRecord]:
    store.ensure_default_workspace(user.id, user.username)
    return store.list_workspaces(user.id)


@app.post("/api/workspaces", response_model=WorkspaceRecord, status_code=201)
def create_workspace(payload: WorkspaceCreatePayload, user: UserRecord = Depends(require_auth)) -> WorkspaceRecord:
    workspace = store.create_workspace(user.id, payload.name)
    store.append_audit_log(
        workspace.id,
        user.id,
        "workspace.create",
        "workspace",
        f"创建团队空间：{workspace.name}",
        workspace.id,
    )
    return workspace


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
    store.append_audit_log(
        workspace_id,
        user.id,
        "workspace.member_upsert",
        "workspace_member",
        f"设置成员 {member.username} 为 {member.role}",
        member.id,
        {"role": member.role},
    )
    return member


@app.get("/api/workspaces/{workspace_id}/invitations", response_model=list[WorkspaceInvitationRecord])
def list_workspace_invitations(
    workspace_id: str,
    user: UserRecord = Depends(require_auth),
) -> list[WorkspaceInvitationRecord]:
    invitations = store.list_workspace_invitations(workspace_id, user.id)
    if invitations is None:
        raise HTTPException(status_code=403, detail="Workspace owner access required")
    return invitations


@app.post("/api/workspaces/{workspace_id}/invitations", response_model=WorkspaceInvitationRecord, status_code=201)
def create_workspace_invitation(
    workspace_id: str,
    payload: WorkspaceInvitationCreatePayload,
    user: UserRecord = Depends(require_auth),
) -> WorkspaceInvitationRecord:
    invitation = store.create_workspace_invitation(workspace_id, user.id, payload.role)
    if invitation is None:
        raise HTTPException(status_code=403, detail="Workspace owner access required")
    store.append_audit_log(
        workspace_id,
        user.id,
        "workspace.invitation_create",
        "workspace_invitation",
        f"创建 {invitation.role} 邀请码",
        invitation.id,
        {"role": invitation.role},
    )
    return invitation


@app.post("/api/workspaces/invitations/accept", response_model=WorkspaceInvitationRecord)
def accept_workspace_invitation(
    payload: WorkspaceInvitationAcceptPayload,
    user: UserRecord = Depends(require_auth),
) -> WorkspaceInvitationRecord:
    invitation = store.accept_workspace_invitation(payload.code, user.id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found or no longer valid")
    store.append_audit_log(
        invitation.workspace_id,
        user.id,
        "workspace.invitation_accept",
        "workspace_invitation",
        f"接受团队空间邀请：{invitation.workspace_name or invitation.workspace_id}",
        invitation.id,
        {"role": invitation.role},
    )
    return invitation


@app.delete("/api/workspaces/{workspace_id}/invitations/{invitation_id}", response_model=WorkspaceInvitationRecord)
def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    user: UserRecord = Depends(require_auth),
) -> WorkspaceInvitationRecord:
    invitation = store.revoke_workspace_invitation(workspace_id, invitation_id, user.id)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found or workspace owner access required")
    store.append_audit_log(
        workspace_id,
        user.id,
        "workspace.invitation_revoke",
        "workspace_invitation",
        f"撤销 {invitation.role} 邀请码",
        invitation.id,
        {"role": invitation.role, "status": invitation.status},
    )
    return invitation


@app.get("/api/model-configs/{provider}", response_model=ModelConfigRecord)
def get_model_config(
    provider: str,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> ModelConfigRecord:
    ensure_supported_model_provider(provider)
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
    ensure_supported_model_provider(provider)
    user, workspace_id = context
    try:
        config = store.upsert_model_config(workspace_id, user.id, provider, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if config is None:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    store.append_audit_log(
        workspace_id,
        user.id,
        "model_config.save",
        "model_config",
        f"保存 {provider} 模型配置",
        provider,
        {"enabled": config.enabled, "model": config.model, "has_api_key": config.has_api_key},
    )
    return config


@app.post("/api/model-configs/{provider}/test", response_model=ModelConfigTestResponse)
def test_model_config(
    provider: str,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> ModelConfigTestResponse:
    ensure_supported_model_provider(provider)
    _, workspace_id = context
    runtime_config = store.get_runtime_model_config(workspace_id, provider)
    if not runtime_config:
        message = (
            "当前团队空间还没有可用的阿里云百炼 Key。"
            if provider == "aliyun"
            else "当前团队空间还没有可用的 DeepSeek Key。"
        )
        return ModelConfigTestResponse(ok=False, message=message, provider=provider, model="")
    label = "阿里云百炼" if provider == "aliyun" else "DeepSeek"
    return ModelConfigTestResponse(
        ok=True,
        message=f"{label} 配置已保存。运行工作流时会优先使用当前团队空间配置。",
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
    workflow = store.create_workflow(payload, user.id, workspace_id)
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.create",
        "workflow",
        f"创建工作流：{workflow.name}",
        workflow.id,
        {"version": workflow.version},
    )
    return workflow


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


@app.get("/api/workflows/{workflow_id}/versions", response_model=list[WorkflowVersionRecord])
def list_workflow_versions(
    workflow_id: str,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> list[WorkflowVersionRecord]:
    user, workspace_id = context
    versions = store.list_workflow_versions(workflow_id, user.id, workspace_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return versions


@app.post("/api/workflows/{workflow_id}/versions", response_model=WorkflowVersionRecord, status_code=201)
def create_workflow_version(
    workflow_id: str,
    payload: WorkflowVersionCreatePayload,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> WorkflowVersionRecord:
    user, workspace_id = context
    version = store.create_workflow_version(workflow_id, user.id, workspace_id, payload.note)
    if not version:
        raise HTTPException(status_code=404, detail="Workflow not found")
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.version_create",
        "workflow",
        f"保存工作流版本 #{version.sequence}：{version.name}",
        workflow_id,
        {"version_id": version.id, "sequence": version.sequence},
    )
    return version


@app.post("/api/workflows/{workflow_id}/versions/{version_id}/restore", response_model=WorkflowRecord)
def restore_workflow_version(
    workflow_id: str,
    version_id: str,
    context: WorkspaceContext = Depends(require_workspace_role("editor")),
) -> WorkflowRecord:
    user, workspace_id = context
    workflow = store.restore_workflow_version(workflow_id, version_id, user.id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.version_restore",
        "workflow",
        f"恢复工作流版本：{workflow.name}",
        workflow_id,
        {"version_id": version_id},
    )
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
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.update",
        "workflow",
        f"更新工作流：{workflow.name}",
        workflow.id,
        {"version": workflow.version},
    )
    return workflow


@app.delete("/api/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, context: WorkspaceContext = Depends(require_workspace_role("editor"))) -> None:
    user, workspace_id = context
    workflow = store.get_workflow(workflow_id, user.id, workspace_id)
    if not store.delete_workflow(workflow_id, user.id, workspace_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.delete",
        "workflow",
        f"删除工作流：{workflow.name if workflow else workflow_id}",
        workflow_id,
    )


@app.get("/api/audit-logs", response_model=list[AuditLogRecord])
def list_audit_logs(
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: int = 100,
    context: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> list[AuditLogRecord]:
    user, workspace_id = context
    logs = store.list_audit_logs(workspace_id, user.id, resource_type, resource_id, limit)
    if logs is None:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return logs


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
    run = store.create_run(workflow.id, user.id, workflow.name, payload.input_text, response, workspace_id)
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.run",
        "workflow",
        f"同步运行工作流：{workflow.name}",
        workflow.id,
        {"run_id": run.id, "status": run.status},
    )
    return run


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
    job = job_queue.enqueue(user.id, workspace_id, workflow_id, payload.input_text)
    store.append_audit_log(
        workspace_id,
        user.id,
        "workflow.run_enqueue",
        "workflow",
        f"异步入队工作流：{workflow.name}",
        workflow_id,
        {"job_id": job.id},
    )
    return job


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

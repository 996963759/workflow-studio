from typing import Any

from pydantic import BaseModel, Field


class WorkflowPayload(BaseModel):
    name: str = Field(min_length=1)
    version: str = "0.2.0"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    archived: bool = False


class WorkflowRecord(WorkflowPayload):
    id: str
    updated_at: str


class WorkflowVersionRecord(WorkflowPayload):
    id: str
    workflow_id: str
    sequence: int
    created_by: str
    created_at: str
    note: str | None = None


class WorkflowVersionCreatePayload(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class WorkflowIssue(BaseModel):
    id: str
    level: str
    message: str
    node_id: str | None = None


class WorkflowValidationResult(BaseModel):
    errors: list[WorkflowIssue] = Field(default_factory=list)
    warnings: list[WorkflowIssue] = Field(default_factory=list)
    valid: bool


class KnowledgeDocumentPayload(BaseModel):
    filename: str = Field(min_length=1)
    content: str = Field(default="")


class AuthPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserRecord(BaseModel):
    id: str
    username: str
    created_at: str


class WorkspaceRecord(BaseModel):
    id: str
    name: str
    owner_id: str
    role: str
    created_at: str


class WorkspaceCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WorkspaceMemberRecord(BaseModel):
    id: str
    username: str
    role: str
    created_at: str


class WorkspaceMemberPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: str = Field(pattern="^(owner|editor|viewer)$")


class WorkspaceInvitationCreatePayload(BaseModel):
    role: str = Field(pattern="^(owner|editor|viewer)$")


class WorkspaceInvitationAcceptPayload(BaseModel):
    code: str = Field(min_length=8, max_length=80)


class WorkspaceInvitationRecord(BaseModel):
    id: str
    workspace_id: str
    workspace_name: str | None = None
    code: str
    role: str
    status: str
    created_by: str
    created_by_username: str | None = None
    accepted_by: str | None = None
    accepted_by_username: str | None = None
    created_at: str
    expires_at: str
    accepted_at: str | None = None
    revoked_at: str | None = None


class ModelConfigPayload(BaseModel):
    enabled: bool = True
    model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=120)
    base_url: str = Field(default="https://api.deepseek.com", min_length=1, max_length=300)
    api_key: str | None = Field(default=None, max_length=300)


class ModelConfigRecord(BaseModel):
    provider: str
    enabled: bool
    model: str
    base_url: str | None = None
    has_api_key: bool
    masked_api_key: str | None = None
    updated_at: str | None = None


class ModelConfigTestResponse(BaseModel):
    ok: bool
    message: str
    provider: str
    model: str


class AuthResponse(BaseModel):
    token: str
    user: UserRecord


class RunRequest(BaseModel):
    workflow: WorkflowPayload
    input_text: str = ""


class WorkflowRunRequest(BaseModel):
    input_text: str = ""


class RunStep(BaseModel):
    node_id: str
    title: str
    status: str
    input: str
    output: str
    variable: str | None = None
    provider: str | None = None
    error: str | None = None


class RunResponse(BaseModel):
    status: str
    steps: list[RunStep]


class RunRecord(RunResponse):
    id: str
    workflow_id: str | None = None
    workflow_name: str
    input_text: str
    created_at: str


class RunJobRecord(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_text: str
    run_id: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class AuditLogRecord(BaseModel):
    id: str
    workspace_id: str
    actor_user_id: str
    actor_username: str
    action: str
    resource_type: str
    resource_id: str | None = None
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str

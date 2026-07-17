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
    publish_status: str = "draft"
    published_version_id: str | None = None
    published_at: str | None = None


class WorkflowVersionRecord(WorkflowPayload):
    id: str
    workflow_id: str
    sequence: int
    is_published: bool = False
    created_by: str
    created_at: str
    note: str | None = None


class WorkflowVersionCreatePayload(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class WorkflowPublishPayload(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class WorkflowVersionDiffItem(BaseModel):
    category: str
    change: str
    label: str
    before: str | None = None
    after: str | None = None


class WorkflowVersionDiffResponse(BaseModel):
    base_version: WorkflowVersionRecord
    target_version: WorkflowVersionRecord
    summary: dict[str, int] = Field(default_factory=dict)
    changes: list[WorkflowVersionDiffItem] = Field(default_factory=list)


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


class RagPreviewPayload(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=10)


class RagDiagnoseResponse(BaseModel):
    ok: bool
    provider: str = "PaiSmart RAG"
    base_url: str
    token_configured: bool
    result_count: int = 0
    message: str


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
    role: str = Field(pattern="^(owner|editor|viewer|customer)$")


class WorkspaceInvitationCreatePayload(BaseModel):
    role: str = Field(pattern="^(owner|editor|viewer|customer)$")


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


class WorkflowRouteRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=4000)


class WorkflowRouteRunRequest(WorkflowRouteRequest):
    workflow_id: str | None = None


class WorkflowRouteCandidate(BaseModel):
    workflow_id: str
    workflow_name: str
    score: float = Field(ge=0, le=1)


class WorkflowRouteDecision(BaseModel):
    workflow_id: str | None = None
    workflow_name: str | None = None
    reason: str
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool = False
    provider: str
    candidates: list[WorkflowRouteCandidate] = Field(default_factory=list)


class RunStep(BaseModel):
    node_id: str
    title: str
    status: str
    input: str
    output: str
    kind: str | None = None
    variable: str | None = None
    provider: str | None = None
    error: str | None = None
    duration_ms: int = 0
    attempt_count: int = 1


class RunResponse(BaseModel):
    status: str
    steps: list[RunStep]
    execution_mode: str = "development"


class RunRecord(RunResponse):
    id: str
    workflow_id: str | None = None
    workflow_name: str
    input_text: str
    created_at: str
    updated_at: str | None = None
    workflow_version: str | None = None
    cost_summary: dict[str, Any] = Field(default_factory=dict)


class WorkflowRouteRunResponse(BaseModel):
    route: WorkflowRouteDecision
    run: RunRecord | None = None


class CustomerChatHistoryMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)


class CustomerChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[CustomerChatHistoryMessage] = Field(default_factory=list, max_length=20)


class CustomerChatResponse(BaseModel):
    status: str = Field(pattern="^(completed|needs_clarification|error)$")
    reply: str
    run_id: str | None = None


class RunJobRecord(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_text: str
    run_id: str | None = None
    error: str | None = None
    execution_mode: str = "development"
    cancel_requested: bool = False
    workflow_version: str | None = None
    created_at: str
    updated_at: str


class EvaluationCasePayload(BaseModel):
    input_text: str = Field(min_length=1, max_length=4000)
    expected_output: str = Field(default="", max_length=4000)
    expected_keywords: list[str] = Field(default_factory=list)


class EvaluationDatasetPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    cases: list[EvaluationCasePayload] = Field(default_factory=list)


class EvaluationCaseRecord(EvaluationCasePayload):
    id: str
    created_at: str
    updated_at: str


class EvaluationDatasetRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    case_count: int = 0
    created_at: str
    updated_at: str
    cases: list[EvaluationCaseRecord] = Field(default_factory=list)


class EvaluationRunRequest(BaseModel):
    workflow_id: str = Field(min_length=1)


class EvaluationCaseResult(BaseModel):
    case_id: str
    input_text: str
    expected_keywords: list[str] = Field(default_factory=list)
    output: str
    passed: bool
    missing_keywords: list[str] = Field(default_factory=list)
    status: str
    duration_ms: int = 0
    run_id: str | None = None
    error: str | None = None


class EvaluationRunRecord(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str
    workflow_id: str
    workflow_name: str
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    average_duration_ms: int = 0
    created_by: str
    created_at: str
    results: list[EvaluationCaseResult] = Field(default_factory=list)


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


class RunMetricsRecord(BaseModel):
    total_runs: int = 0
    sampled_runs: int = 0
    ok_runs: int = 0
    error_runs: int = 0
    success_rate: float = 0
    average_duration_ms: int = 0
    average_step_count: float = 0
    billable_step_count: int = 0
    total_cost_units: int = 0
    average_cost_units: float = 0
    provider_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_failed_runs: list[RunRecord] = Field(default_factory=list)


class AdminOverviewRecord(BaseModel):
    status: str
    database: str
    queue_backend: str
    workspace: WorkspaceRecord
    counts: dict[str, int]
    settings: dict[str, Any]
    provider_status: dict[str, Any]
    knowledge_status: dict[str, int | str]
    run_metrics: RunMetricsRecord = Field(default_factory=RunMetricsRecord)
    recent_audit_logs: list[AuditLogRecord] = Field(default_factory=list)
    recent_run_jobs: list[RunJobRecord] = Field(default_factory=list)

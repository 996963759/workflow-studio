from typing import Any

from pydantic import BaseModel, Field


class WorkflowPayload(BaseModel):
    name: str = Field(min_length=1)
    version: str = "0.2.0"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRecord(WorkflowPayload):
    id: str
    updated_at: str


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

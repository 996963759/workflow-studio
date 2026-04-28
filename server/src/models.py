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


class RunRequest(BaseModel):
    workflow: WorkflowPayload
    input_text: str = ""


class RunStep(BaseModel):
    node_id: str
    title: str
    status: str
    input: str
    output: str
    variable: str | None = None


class RunResponse(BaseModel):
    status: str
    steps: list[RunStep]

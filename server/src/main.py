from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    RunRecord,
    RunRequest,
    RunResponse,
    WorkflowPayload,
    WorkflowRecord,
    WorkflowRunRequest,
    WorkflowValidationResult,
)
from .runner import simulate_run
from .storage import WorkflowStore
from .validation import validate_workflow


app = FastAPI(title="Workflow Studio API", version="0.1.0")
store = WorkflowStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
def list_runs() -> list[RunRecord]:
    return store.list_runs()


@app.get("/api/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/workflows/{workflow_id}/runs", response_model=RunRecord, status_code=201)
def run_stored_workflow(workflow_id: str, payload: WorkflowRunRequest) -> RunRecord:
    workflow = store.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    raise_on_validation_errors(workflow)
    response = simulate_run(workflow, payload.input_text)
    return store.create_run(workflow.id, workflow.name, payload.input_text, response)

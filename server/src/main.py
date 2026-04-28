from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import RunRequest, RunResponse, WorkflowPayload, WorkflowRecord
from .runner import simulate_run
from .storage import WorkflowStore


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


@app.post("/api/workflows", response_model=WorkflowRecord, status_code=201)
def create_workflow(payload: WorkflowPayload) -> WorkflowRecord:
    return store.create_workflow(payload)


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def get_workflow(workflow_id: str) -> WorkflowRecord:
    workflow = store.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowRecord)
def update_workflow(workflow_id: str, payload: WorkflowPayload) -> WorkflowRecord:
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
    return simulate_run(payload.workflow, payload.input_text)

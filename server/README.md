# Workflow Studio API

FastAPI backend for Workflow Studio. The current backend stores workflows in a local SQLite database, validates workflow structure, records workflow runs, and can call OpenAI for LLM nodes when `OPENAI_API_KEY` is configured.

## Setup

```powershell
python -m venv server/.venv
server\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

## Run

```powershell
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

Optional OpenAI runtime:

```powershell
$env:OPENAI_API_KEY="your OpenAI API key"
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

Without `OPENAI_API_KEY`, LLM nodes keep returning simulated output.

## Endpoints

- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflows/validate`
- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PUT /api/workflows/{workflow_id}`
- `DELETE /api/workflows/{workflow_id}`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs?workflow_id={workflow_id}`
- `DELETE /api/runs`
- `DELETE /api/runs?workflow_id={workflow_id}`
- `GET /api/runs/{run_id}`
- `DELETE /api/runs/{run_id}`
- `POST /api/workflows/{workflow_id}/runs`

`POST /api/workflows`, `PUT /api/workflows/{workflow_id}`, `POST /api/runs` and `POST /api/workflows/{workflow_id}/runs` reject workflows with validation errors and return HTTP 400 with the validation result in `detail`.

## Validation Rules

Errors:

- At least one input node is required.
- At least one output node is required.
- Cycles are not allowed.
- Output nodes must have an upstream node.
- Output variable names must be unique.

Warnings:

- Isolated nodes have no edges.
- Non-input nodes without upstream input are flagged.

## Storage

The SQLite database is created at:

```text
server/data/workflow_studio.db
```

The database file is ignored by Git.

## Smoke Test

With the API server running:

```powershell
server\.venv\Scripts\python.exe server/scripts/smoke_test.py
```

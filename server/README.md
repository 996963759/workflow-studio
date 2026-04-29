# Workflow Studio API

FastAPI backend for Workflow Studio. The current backend stores workflows in a local SQLite database, validates workflow structure, records workflow runs, searches local Markdown/TXT knowledge documents, can call DeepSeek or OpenAI for LLM nodes when an API key is configured, and can execute localhost HTTP tool nodes.

## Setup

```powershell
python -m venv server/.venv
server\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

## Run

```powershell
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

Optional DeepSeek runtime:

```powershell
$env:DEEPSEEK_API_KEY="your DeepSeek API key"
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

The default DeepSeek model is `deepseek-v4-flash`. Override it with:

```powershell
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

Optional OpenAI runtime:

```powershell
$env:OPENAI_API_KEY="your OpenAI API key"
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

DeepSeek is preferred when `DEEPSEEK_API_KEY` is present. Without DeepSeek or OpenAI keys, LLM nodes keep returning simulated output.

LLM nodes support per-node runtime options:

- `temperature`: 0 to 2
- `maxOutputTokens`: 1 to 32000
- `timeoutSeconds`: 5 to 300

Executable nodes support failure handling options:

- `failurePolicy`: `stop`, `continue`, or `skip_downstream`
- `retryCount`: 0 to 5

HTTP tool nodes can call `localhost`, `127.0.0.1`, or `::1` by default. Other hosts are blocked by validation and runtime checks.

Local knowledge documents live in:

```text
server/data/knowledge/
```

Supported file types are `.md` and `.txt`. Knowledge nodes use simple local keyword retrieval and do not require a vector database.

## Endpoints

- `GET /api/health`
- `GET /api/provider-status`
- `GET /api/knowledge/status`
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
- LLM node temperature, max output tokens, and timeout must stay within supported ranges.
- Node failure policy and retry count must stay within supported ranges.
- HTTP tool URLs must target `localhost`, `127.0.0.1`, or `::1`.
- HTTP tool headers and body must be JSON objects when provided.

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

If the API is running on another port:

```powershell
$env:BASE_URL="http://127.0.0.1:8001"
server\.venv\Scripts\python.exe server/scripts/smoke_test.py
```

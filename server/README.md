# Workflow Studio API

FastAPI backend for Workflow Studio. The current backend stores workflows in a local SQLite database and returns simulated workflow run steps.

## Setup

```powershell
python -m venv server/.venv
server\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
```

## Run

```powershell
server\.venv\Scripts\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000
```

## Endpoints

- `GET /api/health`
- `GET /api/workflows`
- `POST /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `PUT /api/workflows/{workflow_id}`
- `DELETE /api/workflows/{workflow_id}`
- `POST /api/runs`

## Storage

The SQLite database is created at:

```text
server/data/workflow_studio.db
```

The database file is ignored by Git.

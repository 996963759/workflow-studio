import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import RunRecord, RunResponse, WorkflowPayload, WorkflowRecord


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "workflow_studio.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    nodes_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
            }
            if "archived" not in columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT,
                    workflow_name TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def list_workflows(self) -> list[WorkflowRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, version, nodes_json, edges_json, archived, updated_at
                FROM workflows
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, version, nodes_json, edges_json, archived, updated_at
                FROM workflows
                WHERE id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def create_workflow(self, payload: WorkflowPayload) -> WorkflowRecord:
        workflow_id = str(uuid.uuid4())
        updated_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (id, name, version, nodes_json, edges_json, archived, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    payload.name,
                    payload.version,
                    json.dumps(payload.nodes, ensure_ascii=False),
                    json.dumps(payload.edges, ensure_ascii=False),
                    int(payload.archived),
                    updated_at,
                ),
            )
        return WorkflowRecord(id=workflow_id, updated_at=updated_at, **payload.model_dump())

    def update_workflow(self, workflow_id: str, payload: WorkflowPayload) -> WorkflowRecord | None:
        updated_at = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflows
                SET name = ?, version = ?, nodes_json = ?, edges_json = ?, archived = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.version,
                    json.dumps(payload.nodes, ensure_ascii=False),
                    json.dumps(payload.edges, ensure_ascii=False),
                    int(payload.archived),
                    updated_at,
                    workflow_id,
                ),
            )
        if cursor.rowcount == 0:
            return None
        return WorkflowRecord(id=workflow_id, updated_at=updated_at, **payload.model_dump())

    def delete_workflow(self, workflow_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        return cursor.rowcount > 0

    def create_run(
        self,
        workflow_id: str | None,
        workflow_name: str,
        input_text: str,
        response: RunResponse,
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (id, workflow_id, workflow_name, input_text, status, steps_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    workflow_id,
                    workflow_name,
                    input_text,
                    response.status,
                    json.dumps([step.model_dump() for step in response.steps], ensure_ascii=False),
                    created_at,
                ),
            )
        return RunRecord(
            id=run_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            input_text=input_text,
            created_at=created_at,
            status=response.status,
            steps=response.steps,
        )

    def list_runs(self, workflow_id: str | None = None) -> list[RunRecord]:
        with self._connect() as connection:
            if workflow_id:
                rows = connection.execute(
                    """
                    SELECT id, workflow_id, workflow_name, input_text, status, steps_json, created_at
                    FROM runs
                    WHERE workflow_id = ?
                    ORDER BY created_at DESC
                    """,
                    (workflow_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, workflow_id, workflow_name, input_text, status, steps_json, created_at
                    FROM runs
                    ORDER BY created_at DESC
                    """
                ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, workflow_id, workflow_name, input_text, status, steps_json, created_at
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        return self._row_to_run(row) if row else None

    def delete_run(self, run_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cursor.rowcount > 0

    def delete_runs(self, workflow_id: str | None = None) -> int:
        with self._connect() as connection:
            if workflow_id:
                cursor = connection.execute("DELETE FROM runs WHERE workflow_id = ?", (workflow_id,))
            else:
                cursor = connection.execute("DELETE FROM runs")
        return cursor.rowcount

    def _row_to_record(self, row: sqlite3.Row) -> WorkflowRecord:
        return WorkflowRecord(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            nodes=json.loads(row["nodes_json"]),
            edges=json.loads(row["edges_json"]),
            archived=bool(row["archived"]),
            updated_at=row["updated_at"],
        )

    def _row_to_run(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            workflow_id=row["workflow_id"],
            workflow_name=row["workflow_name"],
            input_text=row["input_text"],
            status=row["status"],
            steps=json.loads(row["steps_json"]),
            created_at=row["created_at"],
        )

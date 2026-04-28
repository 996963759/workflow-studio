import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import WorkflowPayload, WorkflowRecord


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
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list_workflows(self) -> list[WorkflowRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, version, nodes_json, edges_json, updated_at
                FROM workflows
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, version, nodes_json, edges_json, updated_at
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
                INSERT INTO workflows (id, name, version, nodes_json, edges_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    payload.name,
                    payload.version,
                    json.dumps(payload.nodes, ensure_ascii=False),
                    json.dumps(payload.edges, ensure_ascii=False),
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
                SET name = ?, version = ?, nodes_json = ?, edges_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    payload.version,
                    json.dumps(payload.nodes, ensure_ascii=False),
                    json.dumps(payload.edges, ensure_ascii=False),
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

    def _row_to_record(self, row: sqlite3.Row) -> WorkflowRecord:
        return WorkflowRecord(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            nodes=json.loads(row["nodes_json"]),
            edges=json.loads(row["edges_json"]),
            updated_at=row["updated_at"],
        )

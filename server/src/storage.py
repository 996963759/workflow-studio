import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_PATH, DATABASE_URL
from .db import SessionLocal, create_session_factory
from .models import RunRecord, RunResponse, WorkflowPayload, WorkflowRecord
from .orm import Base, DbRun, DbWorkflow


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_path_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.removeprefix("sqlite:///"))


class WorkflowStore:
    def __init__(
        self,
        db_path: Path | None = DATABASE_PATH,
        session_factory: sessionmaker[Session] | None = None,
        engine: Engine | None = None,
    ) -> None:
        if session_factory:
            self.db_path = db_path
            self.engine = engine
            self.SessionLocal = session_factory
        else:
            self.db_path = db_path
            if db_path:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                database_url = f"sqlite:///{db_path.as_posix()}"
            else:
                database_url = DATABASE_URL
            self.engine, self.SessionLocal = create_session_factory(database_url)
        self._init_db()

    def _connect(self) -> Session:
        return self.SessionLocal()

    def _init_db(self) -> None:
        if self.engine:
            Base.metadata.create_all(self.engine)
            sqlite_path = _sqlite_path_from_url(str(self.engine.url))
            if sqlite_path:
                self._migrate_sqlite_columns(sqlite_path)

    def _migrate_sqlite_columns(self, db_path: Path) -> None:
        with sqlite3.connect(db_path) as connection:
            workflow_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
            }
            if "archived" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            if "user_id" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN user_id TEXT")
            run_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "user_id" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN user_id TEXT")

    def assign_unowned_records(self, user_id: str) -> None:
        with self._connect() as session:
            session.execute(update(DbWorkflow).where(DbWorkflow.user_id.is_(None)).values(user_id=user_id))
            session.execute(update(DbRun).where(DbRun.user_id.is_(None)).values(user_id=user_id))
            session.commit()

    def list_workflows(self, user_id: str) -> list[WorkflowRecord]:
        with self._connect() as session:
            workflows = session.scalars(
                select(DbWorkflow)
                .where(DbWorkflow.user_id == user_id)
                .order_by(DbWorkflow.updated_at.desc())
            ).all()
        return [self._workflow_to_record(workflow) for workflow in workflows]

    def get_workflow(self, workflow_id: str, user_id: str) -> WorkflowRecord | None:
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.user_id == user_id)
            )
        return self._workflow_to_record(workflow) if workflow else None

    def create_workflow(self, payload: WorkflowPayload, user_id: str) -> WorkflowRecord:
        workflow_id = str(uuid.uuid4())
        updated_at = utc_now()
        workflow = DbWorkflow(
            id=workflow_id,
            user_id=user_id,
            name=payload.name,
            version=payload.version,
            nodes_json=json.dumps(payload.nodes, ensure_ascii=False),
            edges_json=json.dumps(payload.edges, ensure_ascii=False),
            archived=payload.archived,
            updated_at=updated_at,
        )
        with self._connect() as session:
            session.add(workflow)
            session.commit()
        return WorkflowRecord(id=workflow_id, updated_at=updated_at, **payload.model_dump())

    def update_workflow(self, workflow_id: str, payload: WorkflowPayload, user_id: str) -> WorkflowRecord | None:
        updated_at = utc_now()
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.user_id == user_id)
            )
            if not workflow:
                return None
            workflow.name = payload.name
            workflow.version = payload.version
            workflow.nodes_json = json.dumps(payload.nodes, ensure_ascii=False)
            workflow.edges_json = json.dumps(payload.edges, ensure_ascii=False)
            workflow.archived = payload.archived
            workflow.updated_at = updated_at
            session.commit()
        return WorkflowRecord(id=workflow_id, updated_at=updated_at, **payload.model_dump())

    def delete_workflow(self, workflow_id: str, user_id: str) -> bool:
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.user_id == user_id)
            )
            if not workflow:
                return False
            session.delete(workflow)
            session.execute(delete(DbRun).where(DbRun.workflow_id == workflow_id, DbRun.user_id == user_id))
            session.commit()
        return True

    def create_run(
        self,
        workflow_id: str | None,
        user_id: str,
        workflow_name: str,
        input_text: str,
        response: RunResponse,
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        created_at = utc_now()
        run = DbRun(
            id=run_id,
            user_id=user_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            input_text=input_text,
            status=response.status,
            steps_json=json.dumps([step.model_dump() for step in response.steps], ensure_ascii=False),
            created_at=created_at,
        )
        with self._connect() as session:
            session.add(run)
            session.commit()
        return RunRecord(
            id=run_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            input_text=input_text,
            created_at=created_at,
            status=response.status,
            steps=response.steps,
        )

    def list_runs(self, user_id: str, workflow_id: str | None = None) -> list[RunRecord]:
        with self._connect() as session:
            statement = select(DbRun).where(DbRun.user_id == user_id)
            if workflow_id:
                statement = statement.where(DbRun.workflow_id == workflow_id)
            runs = session.scalars(statement.order_by(DbRun.created_at.desc())).all()
        return [self._run_to_record(run) for run in runs]

    def get_run(self, run_id: str, user_id: str) -> RunRecord | None:
        with self._connect() as session:
            run = session.scalar(select(DbRun).where(DbRun.id == run_id, DbRun.user_id == user_id))
        return self._run_to_record(run) if run else None

    def delete_run(self, run_id: str, user_id: str) -> bool:
        with self._connect() as session:
            result = session.execute(delete(DbRun).where(DbRun.id == run_id, DbRun.user_id == user_id))
            session.commit()
        return result.rowcount > 0

    def delete_runs(self, user_id: str, workflow_id: str | None = None) -> int:
        with self._connect() as session:
            statement = delete(DbRun).where(DbRun.user_id == user_id)
            if workflow_id:
                statement = statement.where(DbRun.workflow_id == workflow_id)
            result = session.execute(statement)
            session.commit()
        return result.rowcount

    def _workflow_to_record(self, workflow: DbWorkflow) -> WorkflowRecord:
        return WorkflowRecord(
            id=workflow.id,
            name=workflow.name,
            version=workflow.version,
            nodes=json.loads(workflow.nodes_json),
            edges=json.loads(workflow.edges_json),
            archived=bool(workflow.archived),
            updated_at=workflow.updated_at,
        )

    def _run_to_record(self, run: DbRun) -> RunRecord:
        return RunRecord(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_name=run.workflow_name,
            input_text=run.input_text,
            status=run.status,
            steps=json.loads(run.steps_json),
            created_at=run.created_at,
        )


default_store = WorkflowStore(session_factory=SessionLocal, db_path=DATABASE_PATH)

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_PATH, DATABASE_URL
from .db import SessionLocal, create_session_factory, engine as default_engine
from .models import (
    RunJobRecord,
    RunRecord,
    RunResponse,
    WorkflowPayload,
    WorkflowRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from .orm import Base, DbRun, DbRunJob, DbUser, DbWorkflow, DbWorkspace, DbWorkspaceMember


ROLE_ORDER = {"viewer": 1, "editor": 2, "owner": 3}


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
            if "workspace_id" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN workspace_id TEXT")
            run_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "user_id" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN user_id TEXT")
            if "workspace_id" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN workspace_id TEXT")

    def assign_unowned_records(self, user_id: str) -> None:
        workspace_id = self.ensure_default_workspace(user_id)
        with self._connect() as session:
            session.execute(
                update(DbWorkflow)
                .where(DbWorkflow.user_id.is_(None))
                .values(user_id=user_id, workspace_id=workspace_id)
            )
            session.execute(
                update(DbWorkflow)
                .where(DbWorkflow.user_id == user_id, DbWorkflow.workspace_id.is_(None))
                .values(workspace_id=workspace_id)
            )
            session.execute(
                update(DbRun)
                .where(DbRun.user_id.is_(None))
                .values(user_id=user_id, workspace_id=workspace_id)
            )
            session.execute(
                update(DbRun)
                .where(DbRun.user_id == user_id, DbRun.workspace_id.is_(None))
                .values(workspace_id=workspace_id)
            )
            session.commit()

    def ensure_default_workspace(self, user_id: str, username: str | None = None) -> str:
        with self._connect() as session:
            existing = session.scalar(
                select(DbWorkspace)
                .join(DbWorkspaceMember, DbWorkspaceMember.workspace_id == DbWorkspace.id)
                .where(DbWorkspaceMember.user_id == user_id)
                .order_by(DbWorkspace.created_at.asc())
            )
            if existing:
                return existing.id
            workspace_id = str(uuid.uuid4())
            now = utc_now()
            session.add(
                DbWorkspace(
                    id=workspace_id,
                    name=f"{username or '个人'}的团队空间",
                    owner_id=user_id,
                    created_at=now,
                )
            )
            session.add(
                DbWorkspaceMember(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role="owner",
                    created_at=now,
                )
            )
            session.commit()
        return workspace_id

    def list_workspaces(self, user_id: str) -> list[WorkspaceRecord]:
        with self._connect() as session:
            rows = session.execute(
                select(DbWorkspace, DbWorkspaceMember.role)
                .join(DbWorkspaceMember, DbWorkspaceMember.workspace_id == DbWorkspace.id)
                .where(DbWorkspaceMember.user_id == user_id)
                .order_by(DbWorkspace.created_at.asc())
            ).all()
        return [
            WorkspaceRecord(
                id=workspace.id,
                name=workspace.name,
                owner_id=workspace.owner_id,
                role=role,
                created_at=workspace.created_at,
            )
            for workspace, role in rows
        ]

    def create_workspace(self, user_id: str, name: str) -> WorkspaceRecord:
        workspace_id = str(uuid.uuid4())
        now = utc_now()
        workspace = DbWorkspace(id=workspace_id, name=name.strip(), owner_id=user_id, created_at=now)
        member = DbWorkspaceMember(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            user_id=user_id,
            role="owner",
            created_at=now,
        )
        with self._connect() as session:
            session.add(workspace)
            session.add(member)
            session.commit()
        return WorkspaceRecord(id=workspace_id, name=workspace.name, owner_id=user_id, role="owner", created_at=now)

    def get_workspace_role(self, workspace_id: str, user_id: str) -> str | None:
        with self._connect() as session:
            return session.scalar(
                select(DbWorkspaceMember.role).where(
                    DbWorkspaceMember.workspace_id == workspace_id,
                    DbWorkspaceMember.user_id == user_id,
                )
            )

    def can_access_workspace(self, workspace_id: str, user_id: str, minimum_role: str = "viewer") -> bool:
        role = self.get_workspace_role(workspace_id, user_id)
        return bool(role and ROLE_ORDER[role] >= ROLE_ORDER[minimum_role])

    def list_workspace_members(self, workspace_id: str, user_id: str) -> list[WorkspaceMemberRecord] | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            rows = session.execute(
                select(DbUser, DbWorkspaceMember)
                .join(DbWorkspaceMember, DbWorkspaceMember.user_id == DbUser.id)
                .where(DbWorkspaceMember.workspace_id == workspace_id)
                .order_by(DbWorkspaceMember.created_at.asc())
            ).all()
        return [
            WorkspaceMemberRecord(
                id=user.id,
                username=user.username,
                role=member.role,
                created_at=member.created_at,
            )
            for user, member in rows
        ]

    def upsert_workspace_member(
        self,
        workspace_id: str,
        actor_user_id: str,
        username: str,
        role: str,
    ) -> WorkspaceMemberRecord | None:
        if not self.can_access_workspace(workspace_id, actor_user_id, "owner"):
            return None
        with self._connect() as session:
            user = session.scalar(select(DbUser).where(DbUser.username == username.strip().lower()))
            if not user:
                return None
            existing = session.scalar(
                select(DbWorkspaceMember).where(
                    DbWorkspaceMember.workspace_id == workspace_id,
                    DbWorkspaceMember.user_id == user.id,
                )
            )
            now = utc_now()
            if existing:
                existing.role = role
                member_created_at = existing.created_at
            else:
                member_created_at = now
                session.add(
                    DbWorkspaceMember(
                        id=str(uuid.uuid4()),
                        workspace_id=workspace_id,
                        user_id=user.id,
                        role=role,
                        created_at=now,
                    )
                )
            session.commit()
        return WorkspaceMemberRecord(id=user.id, username=user.username, role=role, created_at=member_created_at)

    def list_workflows(self, user_id: str, workspace_id: str | None = None) -> list[WorkflowRecord]:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            workflows = session.scalars(
                select(DbWorkflow)
                .where(DbWorkflow.workspace_id == workspace_id)
                .order_by(DbWorkflow.updated_at.desc())
            ).all()
        return [self._workflow_to_record(workflow) for workflow in workflows]

    def get_workflow(self, workflow_id: str, user_id: str, workspace_id: str | None = None) -> WorkflowRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
        return self._workflow_to_record(workflow) if workflow else None

    def create_workflow(self, payload: WorkflowPayload, user_id: str, workspace_id: str | None = None) -> WorkflowRecord:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        workflow_id = str(uuid.uuid4())
        updated_at = utc_now()
        workflow = DbWorkflow(
            id=workflow_id,
            user_id=user_id,
            workspace_id=workspace_id,
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

    def update_workflow(
        self,
        workflow_id: str,
        payload: WorkflowPayload,
        user_id: str,
        workspace_id: str | None = None,
    ) -> WorkflowRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        updated_at = utc_now()
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
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

    def delete_workflow(self, workflow_id: str, user_id: str, workspace_id: str | None = None) -> bool:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not workflow:
                return False
            session.delete(workflow)
            session.execute(delete(DbRun).where(DbRun.workflow_id == workflow_id, DbRun.workspace_id == workspace_id))
            session.commit()
        return True

    def create_run(
        self,
        workflow_id: str | None,
        user_id: str,
        workflow_name: str,
        input_text: str,
        response: RunResponse,
        workspace_id: str | None = None,
    ) -> RunRecord:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        run_id = str(uuid.uuid4())
        created_at = utc_now()
        run = DbRun(
            id=run_id,
            user_id=user_id,
            workspace_id=workspace_id,
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

    def list_runs(self, user_id: str, workflow_id: str | None = None, workspace_id: str | None = None) -> list[RunRecord]:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            statement = select(DbRun).where(DbRun.workspace_id == workspace_id)
            if workflow_id:
                statement = statement.where(DbRun.workflow_id == workflow_id)
            runs = session.scalars(statement.order_by(DbRun.created_at.desc())).all()
        return [self._run_to_record(run) for run in runs]

    def get_run(self, run_id: str, user_id: str, workspace_id: str | None = None) -> RunRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            run = session.scalar(select(DbRun).where(DbRun.id == run_id, DbRun.workspace_id == workspace_id))
        return self._run_to_record(run) if run else None

    def delete_run(self, run_id: str, user_id: str, workspace_id: str | None = None) -> bool:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            result = session.execute(delete(DbRun).where(DbRun.id == run_id, DbRun.workspace_id == workspace_id))
            session.commit()
        return result.rowcount > 0

    def delete_runs(self, user_id: str, workflow_id: str | None = None, workspace_id: str | None = None) -> int:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            statement = delete(DbRun).where(DbRun.workspace_id == workspace_id)
            if workflow_id:
                statement = statement.where(DbRun.workflow_id == workflow_id)
            result = session.execute(statement)
            session.commit()
        return result.rowcount

    def create_run_job(self, user_id: str, workspace_id: str, workflow_id: str, input_text: str) -> RunJobRecord:
        now = utc_now()
        job = DbRunJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            status="queued",
            input_text=input_text,
            run_id=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as session:
            session.add(job)
            session.commit()
        return self._job_to_record(job)

    def update_run_job(
        self,
        job_id: str,
        status: str,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as session:
            job = session.scalar(select(DbRunJob).where(DbRunJob.id == job_id))
            if not job:
                return
            job.status = status
            job.run_id = run_id
            job.error = error
            job.updated_at = utc_now()
            session.commit()

    def get_run_job(self, job_id: str, user_id: str, workspace_id: str | None = None) -> RunJobRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            job = session.scalar(
                select(DbRunJob).where(DbRunJob.id == job_id, DbRunJob.workspace_id == workspace_id)
            )
        return self._job_to_record(job) if job else None

    def list_run_jobs(
        self,
        user_id: str,
        workflow_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[RunJobRecord]:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            statement = select(DbRunJob).where(DbRunJob.workspace_id == workspace_id)
            if workflow_id:
                statement = statement.where(DbRunJob.workflow_id == workflow_id)
            jobs = session.scalars(statement.order_by(DbRunJob.created_at.desc())).all()
        return [self._job_to_record(job) for job in jobs]

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

    def _job_to_record(self, job: DbRunJob) -> RunJobRecord:
        return RunJobRecord(
            id=job.id,
            workflow_id=job.workflow_id,
            status=job.status,
            input_text=job.input_text,
            run_id=job.run_id,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


default_store = WorkflowStore(session_factory=SessionLocal, db_path=DATABASE_PATH, engine=default_engine)

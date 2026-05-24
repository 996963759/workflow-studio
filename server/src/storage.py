import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_PATH, DATABASE_URL, WORKSPACE_INVITATION_TTL_HOURS
from .db import SessionLocal, create_session_factory, engine as default_engine
from .models import (
    ModelConfigPayload,
    ModelConfigRecord,
    RunJobRecord,
    RunMetricsRecord,
    RunRecord,
    RunResponse,
    EvaluationCaseRecord,
    EvaluationCasePayload,
    EvaluationCaseResult,
    EvaluationDatasetPayload,
    EvaluationDatasetRecord,
    EvaluationRunRecord,
    WorkflowPayload,
    WorkflowPublishPayload,
    WorkflowRecord,
    WorkflowVersionDiffItem,
    WorkflowVersionDiffResponse,
    WorkflowVersionRecord,
    AuditLogRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
    WorkspaceInvitationRecord,
)
from .orm import (
    Base,
    DbAuditLog,
    DbEvaluationCase,
    DbEvaluationDataset,
    DbEvaluationRun,
    DbRun,
    DbRunJob,
    DbUser,
    DbWorkflow,
    DbWorkflowVersion,
    DbWorkspace,
    DbWorkspaceInvitation,
    DbWorkspaceMember,
    DbWorkspaceModelConfig,
)
from .secret_box import mask_secret, protect_secret, reveal_secret


ROLE_ORDER = {"viewer": 1, "editor": 2, "owner": 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def workspace_invitation_expires_at() -> str:
    ttl_hours = max(1, WORKSPACE_INVITATION_TTL_HOURS)
    return (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()


def _node_title(node: dict) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    label = data.get("label") or node.get("id") or "未命名节点"
    kind = data.get("kind") or "node"
    return f"{label}（{kind}）"


def _edge_title(edge: dict) -> str:
    return f"{edge.get('source', '?')} -> {edge.get('target', '?')}"


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_field_change(
    changes: list[WorkflowVersionDiffItem],
    category: str,
    label: str,
    before: object,
    after: object,
) -> None:
    if before == after:
        return
    changes.append(
        WorkflowVersionDiffItem(
            category=category,
            change="changed",
            label=label,
            before=str(before),
            after=str(after),
        )
    )


def diff_workflow_versions(
    base: WorkflowVersionRecord,
    target: WorkflowVersionRecord,
) -> list[WorkflowVersionDiffItem]:
    changes: list[WorkflowVersionDiffItem] = []
    _append_field_change(changes, "workflow", "工作流名称", base.name, target.name)
    _append_field_change(changes, "workflow", "定义版本", base.version, target.version)
    _append_field_change(changes, "workflow", "归档状态", base.archived, target.archived)

    base_nodes = {str(node.get("id")): node for node in base.nodes}
    target_nodes = {str(node.get("id")): node for node in target.nodes}
    for node_id in sorted(target_nodes.keys() - base_nodes.keys()):
        changes.append(WorkflowVersionDiffItem(category="node", change="added", label=_node_title(target_nodes[node_id]), after=_compact_json(target_nodes[node_id].get("data", {}))))
    for node_id in sorted(base_nodes.keys() - target_nodes.keys()):
        changes.append(WorkflowVersionDiffItem(category="node", change="removed", label=_node_title(base_nodes[node_id]), before=_compact_json(base_nodes[node_id].get("data", {}))))
    for node_id in sorted(base_nodes.keys() & target_nodes.keys()):
        before = base_nodes[node_id]
        after = target_nodes[node_id]
        if _compact_json(before) != _compact_json(after):
            changes.append(
                WorkflowVersionDiffItem(
                    category="node",
                    change="changed",
                    label=_node_title(after),
                    before=_compact_json(before.get("data", {})),
                    after=_compact_json(after.get("data", {})),
                )
            )

    base_edges = {str(edge.get("id")): edge for edge in base.edges}
    target_edges = {str(edge.get("id")): edge for edge in target.edges}
    for edge_id in sorted(target_edges.keys() - base_edges.keys()):
        changes.append(WorkflowVersionDiffItem(category="edge", change="added", label=_edge_title(target_edges[edge_id]), after=_compact_json(target_edges[edge_id])))
    for edge_id in sorted(base_edges.keys() - target_edges.keys()):
        changes.append(WorkflowVersionDiffItem(category="edge", change="removed", label=_edge_title(base_edges[edge_id]), before=_compact_json(base_edges[edge_id])))
    for edge_id in sorted(base_edges.keys() & target_edges.keys()):
        before = base_edges[edge_id]
        after = target_edges[edge_id]
        if _compact_json(before) != _compact_json(after):
            changes.append(
                WorkflowVersionDiffItem(
                    category="edge",
                    change="changed",
                    label=_edge_title(after),
                    before=_compact_json(before),
                    after=_compact_json(after),
                )
            )
    return changes


RUN_COST_UNITS_BY_KIND = {
    "llm": 10,
    "tts": 8,
    "image": 30,
    "knowledge": 3,
    "tool": 2,
}


def summarize_run_cost(steps: list[dict]) -> dict[str, object]:
    billable_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("status") != "skipped" and step.get("kind") in RUN_COST_UNITS_BY_KIND
    ]
    provider_breakdown: dict[str, int] = {}
    kind_breakdown: dict[str, int] = {}
    total_units = 0
    for step in billable_steps:
        kind = str(step.get("kind") or "unknown")
        units = RUN_COST_UNITS_BY_KIND.get(kind, 0) * max(1, int(step.get("attempt_count") or 1))
        total_units += units
        provider = str(step.get("provider") or kind)
        provider_breakdown[provider] = provider_breakdown.get(provider, 0) + units
        kind_breakdown[kind] = kind_breakdown.get(kind, 0) + units
    return {
        "billable_step_count": len(billable_steps),
        "cost_units": total_units,
        "provider_breakdown": provider_breakdown,
        "kind_breakdown": kind_breakdown,
        "note": "估算成本单位用于本地演示，不等同于真实云厂商账单。",
    }


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
            if "publish_status" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN publish_status TEXT NOT NULL DEFAULT 'draft'")
            if "published_version_id" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN published_version_id TEXT")
            if "published_at" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN published_at TEXT")
            workflow_version_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(workflow_versions)").fetchall()
            }
            if workflow_version_columns and "is_published" not in workflow_version_columns:
                connection.execute("ALTER TABLE workflow_versions ADD COLUMN is_published INTEGER NOT NULL DEFAULT 0")
            run_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "user_id" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN user_id TEXT")
            if "workspace_id" not in run_columns:
                connection.execute("ALTER TABLE runs ADD COLUMN workspace_id TEXT")
            session_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "expires_at" not in session_columns:
                connection.execute(
                    "ALTER TABLE sessions ADD COLUMN expires_at TEXT NOT NULL DEFAULT '9999-12-31T23:59:59+00:00'"
                )
            invitation_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(workspace_invitations)").fetchall()
            }
            if invitation_columns and "expires_at" not in invitation_columns:
                connection.execute(
                    "ALTER TABLE workspace_invitations ADD COLUMN expires_at TEXT NOT NULL DEFAULT '9999-12-31T23:59:59+00:00'"
                )
            dataset_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(evaluation_datasets)").fetchall()
            }
            if dataset_columns and "updated_at" not in dataset_columns:
                connection.execute("ALTER TABLE evaluation_datasets ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            case_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(evaluation_cases)").fetchall()
            }
            if case_columns and "updated_at" not in case_columns:
                connection.execute("ALTER TABLE evaluation_cases ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            run_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(evaluation_runs)").fetchall()
            }
            if run_columns and "average_duration_ms" not in run_columns:
                connection.execute("ALTER TABLE evaluation_runs ADD COLUMN average_duration_ms INTEGER NOT NULL DEFAULT 0")

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

    def get_workspace_record(self, workspace_id: str, user_id: str) -> WorkspaceRecord | None:
        with self._connect() as session:
            row = session.execute(
                select(DbWorkspace, DbWorkspaceMember.role)
                .join(DbWorkspaceMember, DbWorkspaceMember.workspace_id == DbWorkspace.id)
                .where(DbWorkspace.id == workspace_id, DbWorkspaceMember.user_id == user_id)
            ).one_or_none()
        if not row:
            return None
        workspace, role = row
        return WorkspaceRecord(
            id=workspace.id,
            name=workspace.name,
            owner_id=workspace.owner_id,
            role=role,
            created_at=workspace.created_at,
        )

    def get_workspace_overview_counts(self, workspace_id: str, user_id: str) -> dict[str, int] | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            return {
                "members": session.scalar(
                    select(func.count()).select_from(DbWorkspaceMember).where(DbWorkspaceMember.workspace_id == workspace_id)
                )
                or 0,
                "pending_invitations": session.scalar(
                    select(func.count()).select_from(DbWorkspaceInvitation).where(
                        DbWorkspaceInvitation.workspace_id == workspace_id,
                        DbWorkspaceInvitation.status == "pending",
                    )
                )
                or 0,
                "workflows": session.scalar(
                    select(func.count()).select_from(DbWorkflow).where(DbWorkflow.workspace_id == workspace_id)
                )
                or 0,
                "archived_workflows": session.scalar(
                    select(func.count()).select_from(DbWorkflow).where(
                        DbWorkflow.workspace_id == workspace_id,
                        DbWorkflow.archived.is_(True),
                    )
                )
                or 0,
                "runs": session.scalar(
                    select(func.count()).select_from(DbRun).where(DbRun.workspace_id == workspace_id)
                )
                or 0,
                "run_jobs": session.scalar(
                    select(func.count()).select_from(DbRunJob).where(DbRunJob.workspace_id == workspace_id)
                )
                or 0,
                "queued_run_jobs": session.scalar(
                    select(func.count()).select_from(DbRunJob).where(
                        DbRunJob.workspace_id == workspace_id,
                        DbRunJob.status == "queued",
                    )
                )
                or 0,
                "failed_run_jobs": session.scalar(
                    select(func.count()).select_from(DbRunJob).where(
                        DbRunJob.workspace_id == workspace_id,
                        DbRunJob.status == "failed",
                    )
                )
                or 0,
                "audit_logs": session.scalar(
                    select(func.count()).select_from(DbAuditLog).where(DbAuditLog.workspace_id == workspace_id)
                )
                or 0,
            }

    def get_workspace_run_metrics(self, workspace_id: str, user_id: str) -> RunMetricsRecord | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            total_runs = session.scalar(select(func.count()).select_from(DbRun).where(DbRun.workspace_id == workspace_id)) or 0
            rows = session.scalars(
                select(DbRun).where(DbRun.workspace_id == workspace_id).order_by(DbRun.created_at.desc()).limit(200)
            ).all()

        if total_runs == 0:
            return RunMetricsRecord()

        sampled_runs = len(rows)
        ok_runs = sum(1 for run in rows if run.status == "ok")
        error_runs = sum(1 for run in rows if run.status == "error")
        total_duration_ms = 0
        total_step_count = 0
        billable_step_count = 0
        total_cost_units = 0
        provider_breakdown: dict[str, int] = {}
        failed_runs: list[RunRecord] = []

        for run in rows:
            steps = json.loads(run.steps_json)
            total_step_count += len(steps)
            total_duration_ms += sum(int(step.get("duration_ms") or 0) for step in steps if isinstance(step, dict))
            cost_summary = summarize_run_cost(steps)
            billable_step_count += int(cost_summary["billable_step_count"])
            total_cost_units += int(cost_summary["cost_units"])
            for provider, units in dict(cost_summary["provider_breakdown"]).items():
                provider_breakdown[str(provider)] = provider_breakdown.get(str(provider), 0) + int(units)
            if run.status == "error" and len(failed_runs) < 3:
                failed_runs.append(self._run_to_record(run))

        return RunMetricsRecord(
            total_runs=total_runs,
            sampled_runs=sampled_runs,
            ok_runs=ok_runs,
            error_runs=error_runs,
            success_rate=round(ok_runs / sampled_runs * 100, 1),
            average_duration_ms=round(total_duration_ms / sampled_runs),
            average_step_count=round(total_step_count / sampled_runs, 1),
            billable_step_count=billable_step_count,
            total_cost_units=total_cost_units,
            average_cost_units=round(total_cost_units / sampled_runs, 1),
            provider_breakdown=provider_breakdown,
            recent_failed_runs=failed_runs,
        )

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

    def remove_workspace_member(
        self,
        workspace_id: str,
        actor_user_id: str,
        member_user_id: str,
    ) -> WorkspaceMemberRecord | None:
        if not self.can_access_workspace(workspace_id, actor_user_id, "owner"):
            return None
        if actor_user_id == member_user_id:
            return None
        with self._connect() as session:
            member = session.scalar(
                select(DbWorkspaceMember).where(
                    DbWorkspaceMember.workspace_id == workspace_id,
                    DbWorkspaceMember.user_id == member_user_id,
                )
            )
            user = session.scalar(select(DbUser).where(DbUser.id == member_user_id))
            if not member or not user:
                return None
            if member.role == "owner":
                owner_count = session.scalar(
                    select(func.count()).select_from(DbWorkspaceMember).where(
                        DbWorkspaceMember.workspace_id == workspace_id,
                        DbWorkspaceMember.role == "owner",
                    )
                )
                if (owner_count or 0) <= 1:
                    return None
            record = WorkspaceMemberRecord(
                id=user.id,
                username=user.username,
                role=member.role,
                created_at=member.created_at,
            )
            session.delete(member)
            session.commit()
        return record

    def _invitation_record(
        self,
        invitation: DbWorkspaceInvitation,
        workspace_name: str | None = None,
        created_by_username: str | None = None,
        accepted_by_username: str | None = None,
    ) -> WorkspaceInvitationRecord:
        return WorkspaceInvitationRecord(
            id=invitation.id,
            workspace_id=invitation.workspace_id,
            workspace_name=workspace_name,
            code=invitation.code,
            role=invitation.role,
            status=invitation.status,
            created_by=invitation.created_by,
            created_by_username=created_by_username,
            accepted_by=invitation.accepted_by,
            accepted_by_username=accepted_by_username,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            revoked_at=invitation.revoked_at,
        )

    def _expire_pending_invitation_if_needed(self, invitation: DbWorkspaceInvitation, now: datetime | None = None) -> bool:
        if invitation.status != "pending":
            return False
        expires_at = parse_timestamp(invitation.expires_at)
        if not expires_at or expires_at > (now or datetime.now(timezone.utc)):
            return False
        invitation.status = "expired"
        return True

    def list_workspace_invitations(self, workspace_id: str, actor_user_id: str) -> list[WorkspaceInvitationRecord] | None:
        if not self.can_access_workspace(workspace_id, actor_user_id, "owner"):
            return None
        with self._connect() as session:
            rows = session.execute(
                select(DbWorkspaceInvitation, DbWorkspace.name, DbUser.username)
                .join(DbWorkspace, DbWorkspace.id == DbWorkspaceInvitation.workspace_id)
                .join(DbUser, DbUser.id == DbWorkspaceInvitation.created_by)
                .where(DbWorkspaceInvitation.workspace_id == workspace_id)
                .order_by(DbWorkspaceInvitation.created_at.desc())
            ).all()
            accepted_ids = [invitation.accepted_by for invitation, _, _ in rows if invitation.accepted_by]
            accepted_usernames = (
                {
                    user_id: username
                    for user_id, username in session.execute(
                        select(DbUser.id, DbUser.username).where(DbUser.id.in_(accepted_ids))
                    ).all()
                }
                if accepted_ids
                else {}
            )
            changed = False
            now = datetime.now(timezone.utc)
            for invitation, _, _ in rows:
                changed = self._expire_pending_invitation_if_needed(invitation, now) or changed
            if changed:
                session.commit()
        return [
            self._invitation_record(
                invitation,
                workspace_name,
                created_by_username,
                accepted_usernames.get(invitation.accepted_by or ""),
            )
            for invitation, workspace_name, created_by_username in rows
        ]

    def create_workspace_invitation(
        self,
        workspace_id: str,
        actor_user_id: str,
        role: str,
    ) -> WorkspaceInvitationRecord | None:
        if not self.can_access_workspace(workspace_id, actor_user_id, "owner"):
            return None
        with self._connect() as session:
            workspace = session.scalar(select(DbWorkspace).where(DbWorkspace.id == workspace_id))
            creator = session.scalar(select(DbUser).where(DbUser.id == actor_user_id))
            if not workspace or not creator:
                return None
            now = utc_now()
            invitation = DbWorkspaceInvitation(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                code=uuid.uuid4().hex,
                role=role,
                status="pending",
                created_by=actor_user_id,
                created_at=now,
                expires_at=workspace_invitation_expires_at(),
            )
            session.add(invitation)
            record = self._invitation_record(invitation, workspace.name, creator.username)
            session.commit()
        return record

    def revoke_workspace_invitation(
        self,
        workspace_id: str,
        invitation_id: str,
        actor_user_id: str,
    ) -> WorkspaceInvitationRecord | None:
        if not self.can_access_workspace(workspace_id, actor_user_id, "owner"):
            return None
        with self._connect() as session:
            invitation = session.scalar(
                select(DbWorkspaceInvitation).where(
                    DbWorkspaceInvitation.id == invitation_id,
                    DbWorkspaceInvitation.workspace_id == workspace_id,
                )
            )
            if not invitation:
                return None
            if invitation.status == "pending":
                invitation.status = "revoked"
                invitation.revoked_at = utc_now()
            workspace_name = session.scalar(select(DbWorkspace.name).where(DbWorkspace.id == workspace_id))
            created_by_username = session.scalar(select(DbUser.username).where(DbUser.id == invitation.created_by))
            accepted_by_username = (
                session.scalar(select(DbUser.username).where(DbUser.id == invitation.accepted_by))
                if invitation.accepted_by
                else None
            )
            record = self._invitation_record(invitation, workspace_name, created_by_username, accepted_by_username)
            session.commit()
        return record

    def accept_workspace_invitation(self, code: str, user_id: str) -> WorkspaceInvitationRecord | None:
        with self._connect() as session:
            invitation = session.scalar(
                select(DbWorkspaceInvitation).where(
                    DbWorkspaceInvitation.code == code.strip(),
                    DbWorkspaceInvitation.status == "pending",
                )
            )
            if not invitation:
                return None
            if self._expire_pending_invitation_if_needed(invitation):
                session.commit()
                return None
            existing = session.scalar(
                select(DbWorkspaceMember).where(
                    DbWorkspaceMember.workspace_id == invitation.workspace_id,
                    DbWorkspaceMember.user_id == user_id,
                )
            )
            now = utc_now()
            if existing:
                if ROLE_ORDER[invitation.role] > ROLE_ORDER[existing.role]:
                    existing.role = invitation.role
            else:
                session.add(
                    DbWorkspaceMember(
                        id=str(uuid.uuid4()),
                        workspace_id=invitation.workspace_id,
                        user_id=user_id,
                        role=invitation.role,
                        created_at=now,
                    )
                )
            invitation.status = "accepted"
            invitation.accepted_by = user_id
            invitation.accepted_at = now
            workspace_name = session.scalar(select(DbWorkspace.name).where(DbWorkspace.id == invitation.workspace_id))
            created_by_username = session.scalar(select(DbUser.username).where(DbUser.id == invitation.created_by))
            accepted_by_username = session.scalar(select(DbUser.username).where(DbUser.id == user_id))
            record = self._invitation_record(invitation, workspace_name, created_by_username, accepted_by_username)
            session.commit()
        return record

    def get_model_config(self, workspace_id: str, user_id: str, provider: str) -> ModelConfigRecord | None:
        if not self.can_access_workspace(workspace_id, user_id, "viewer"):
            return None
        with self._connect() as session:
            row = session.scalar(
                select(DbWorkspaceModelConfig).where(
                    DbWorkspaceModelConfig.workspace_id == workspace_id,
                    DbWorkspaceModelConfig.provider == provider,
                )
            )
        if not row:
            default_model = {
                "aliyun": "cosyvoice-v2",
                "paismart": "hybrid",
            }.get(provider, "deepseek-v4-flash")
            default_base_url = {
                "aliyun": "https://dashscope.aliyuncs.com",
                "paismart": "http://127.0.0.1:8080",
            }.get(provider, "https://api.deepseek.com")
            return ModelConfigRecord(
                provider=provider,
                enabled=False,
                model=default_model,
                base_url=default_base_url,
                has_api_key=False,
                masked_api_key=None,
                updated_at=None,
            )
        masked = None
        has_api_key = bool(row.api_key_secret)
        if has_api_key:
            try:
                masked = mask_secret(reveal_secret(row.api_key_secret))
            except ValueError:
                masked = "****"
        return ModelConfigRecord(
            provider=row.provider,
            enabled=bool(row.enabled),
            model=row.model,
            base_url=row.base_url,
            has_api_key=has_api_key,
            masked_api_key=masked,
            updated_at=row.updated_at,
        )

    def upsert_model_config(
        self,
        workspace_id: str,
        user_id: str,
        provider: str,
        payload: ModelConfigPayload,
    ) -> ModelConfigRecord | None:
        if not self.can_access_workspace(workspace_id, user_id, "editor"):
            return None
        now = utc_now()
        with self._connect() as session:
            row = session.scalar(
                select(DbWorkspaceModelConfig).where(
                    DbWorkspaceModelConfig.workspace_id == workspace_id,
                    DbWorkspaceModelConfig.provider == provider,
                )
            )
            if row:
                row.enabled = payload.enabled
                row.model = payload.model.strip()
                row.base_url = payload.base_url.strip()
                if payload.api_key and payload.api_key.strip():
                    row.api_key_secret = protect_secret(payload.api_key.strip())
                row.updated_at = now
            else:
                if not payload.api_key or not payload.api_key.strip():
                    raise ValueError("API key is required when creating a model config")
                row = DbWorkspaceModelConfig(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    provider=provider,
                    model=payload.model.strip(),
                    base_url=payload.base_url.strip(),
                    api_key_secret=protect_secret(payload.api_key.strip()),
                    enabled=payload.enabled,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            session.commit()
        return self.get_model_config(workspace_id, user_id, provider)

    def get_runtime_model_config(self, workspace_id: str, provider: str) -> dict[str, str | bool] | None:
        with self._connect() as session:
            row = session.scalar(
                select(DbWorkspaceModelConfig).where(
                    DbWorkspaceModelConfig.workspace_id == workspace_id,
                    DbWorkspaceModelConfig.provider == provider,
                    DbWorkspaceModelConfig.enabled.is_(True),
                )
            )
        if not row:
            return None
        try:
            api_key = reveal_secret(row.api_key_secret)
        except ValueError:
            return None
        if not api_key:
            return None
        return {
            "provider": row.provider,
            "api_key": api_key,
            "model": row.model,
            "base_url": row.base_url or "",
            "enabled": bool(row.enabled),
        }

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
            publish_status="draft",
            published_version_id=None,
            published_at=None,
            updated_at=updated_at,
        )
        with self._connect() as session:
            session.add(workflow)
            session.flush()
            self._create_workflow_version(session, workflow, user_id, "创建工作流")
            session.commit()
        return self._workflow_to_record(workflow)

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
            workflow.publish_status = "changed" if workflow.published_version_id else "draft"
            workflow.updated_at = updated_at
            self._create_workflow_version(session, workflow, user_id, "更新工作流")
            session.commit()
        return self._workflow_to_record(workflow)

    def delete_workflow(self, workflow_id: str, user_id: str, workspace_id: str | None = None) -> bool:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not workflow:
                return False
            session.execute(delete(DbWorkflowVersion).where(DbWorkflowVersion.workflow_id == workflow_id))
            session.delete(workflow)
            session.execute(delete(DbRun).where(DbRun.workflow_id == workflow_id, DbRun.workspace_id == workspace_id))
            session.commit()
        return True

    def create_workflow_version(
        self,
        workflow_id: str,
        user_id: str,
        workspace_id: str | None = None,
        note: str | None = None,
    ) -> WorkflowVersionRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not workflow:
                return None
            version = self._create_workflow_version(session, workflow, user_id, note or "手动保存版本")
            session.commit()
        return self._workflow_version_to_record(version)

    def list_workflow_versions(
        self,
        workflow_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> list[WorkflowVersionRecord] | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            exists = session.scalar(
                select(DbWorkflow.id).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not exists:
                return None
            versions = session.scalars(
                select(DbWorkflowVersion)
                .where(DbWorkflowVersion.workflow_id == workflow_id, DbWorkflowVersion.workspace_id == workspace_id)
                .order_by(DbWorkflowVersion.sequence.desc())
            ).all()
        return [self._workflow_version_to_record(version) for version in versions]

    def compare_workflow_versions(
        self,
        workflow_id: str,
        base_version_id: str,
        target_version_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> WorkflowVersionDiffResponse | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            exists = session.scalar(
                select(DbWorkflow.id).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not exists:
                return None
            versions = session.scalars(
                select(DbWorkflowVersion).where(
                    DbWorkflowVersion.workflow_id == workflow_id,
                    DbWorkflowVersion.workspace_id == workspace_id,
                    DbWorkflowVersion.id.in_([base_version_id, target_version_id]),
                )
            ).all()
        version_by_id = {version.id: version for version in versions}
        base = version_by_id.get(base_version_id)
        target = version_by_id.get(target_version_id)
        if not base or not target:
            return None
        base_record = self._workflow_version_to_record(base)
        target_record = self._workflow_version_to_record(target)
        changes = diff_workflow_versions(base_record, target_record)
        summary = {
            "added": sum(1 for item in changes if item.change == "added"),
            "removed": sum(1 for item in changes if item.change == "removed"),
            "changed": sum(1 for item in changes if item.change == "changed"),
        }
        return WorkflowVersionDiffResponse(
            base_version=base_record,
            target_version=target_record,
            summary=summary,
            changes=changes,
        )

    def restore_workflow_version(
        self,
        workflow_id: str,
        version_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> WorkflowRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        updated_at = utc_now()
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            version = session.scalar(
                select(DbWorkflowVersion).where(
                    DbWorkflowVersion.id == version_id,
                    DbWorkflowVersion.workflow_id == workflow_id,
                    DbWorkflowVersion.workspace_id == workspace_id,
                )
            )
            if not workflow or not version:
                return None
            workflow.name = version.name
            workflow.version = version.version
            workflow.nodes_json = version.nodes_json
            workflow.edges_json = version.edges_json
            workflow.archived = bool(version.archived)
            workflow.publish_status = "changed" if workflow.published_version_id else "draft"
            workflow.updated_at = updated_at
            self._create_workflow_version(session, workflow, user_id, f"恢复到版本 #{version.sequence}")
            session.commit()
        return self._workflow_to_record(workflow)

    def publish_workflow(
        self,
        workflow_id: str,
        user_id: str,
        workspace_id: str | None = None,
        payload: WorkflowPublishPayload | None = None,
    ) -> tuple[WorkflowRecord, WorkflowVersionRecord] | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        published_at = utc_now()
        with self._connect() as session:
            workflow = session.scalar(
                select(DbWorkflow).where(DbWorkflow.id == workflow_id, DbWorkflow.workspace_id == workspace_id)
            )
            if not workflow:
                return None
            note = payload.note if payload else None
            version = self._create_workflow_version(session, workflow, user_id, note or "发布工作流", True)
            session.flush()
            workflow.publish_status = "published"
            workflow.published_version_id = version.id
            workflow.published_at = published_at
            workflow.updated_at = published_at
            session.commit()
        return self._workflow_to_record(workflow), self._workflow_version_to_record(version)

    def append_audit_log(
        self,
        workspace_id: str,
        actor_user_id: str,
        action: str,
        resource_type: str,
        summary: str,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLogRecord:
        now = utc_now()
        with self._connect() as session:
            username = session.scalar(select(DbUser.username).where(DbUser.id == actor_user_id)) or "unknown"
            row = DbAuditLog(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                actor_username=username,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                summary=summary,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                created_at=now,
            )
            session.add(row)
            session.commit()
        return self._audit_log_to_record(row)

    def list_audit_logs(
        self,
        workspace_id: str,
        user_id: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogRecord] | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            statement = select(DbAuditLog).where(DbAuditLog.workspace_id == workspace_id)
            if resource_type:
                statement = statement.where(DbAuditLog.resource_type == resource_type)
            if resource_id:
                statement = statement.where(DbAuditLog.resource_id == resource_id)
            rows = session.scalars(statement.order_by(DbAuditLog.created_at.desc()).limit(min(max(limit, 1), 200))).all()
        return [self._audit_log_to_record(row) for row in rows]

    def _create_workflow_version(
        self,
        session: Session,
        workflow: DbWorkflow,
        user_id: str,
        note: str | None = None,
        is_published: bool = False,
    ) -> DbWorkflowVersion:
        latest_sequence = session.scalar(
            select(func.max(DbWorkflowVersion.sequence)).where(DbWorkflowVersion.workflow_id == workflow.id)
        )
        row = DbWorkflowVersion(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            workspace_id=workflow.workspace_id or "",
            sequence=(latest_sequence or 0) + 1,
            name=workflow.name,
            version=workflow.version,
            nodes_json=workflow.nodes_json,
            edges_json=workflow.edges_json,
            archived=bool(workflow.archived),
            is_published=is_published,
            created_by=user_id,
            note=note,
            created_at=utc_now(),
        )
        session.add(row)
        return row

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
        steps = [step.model_dump() for step in response.steps]
        cost_summary = summarize_run_cost(steps)
        run = DbRun(
            id=run_id,
            user_id=user_id,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            input_text=input_text,
            status=response.status,
            steps_json=json.dumps(steps, ensure_ascii=False),
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
            cost_summary=cost_summary,
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

    def claim_run_job(self, job_id: str | None = None) -> RunJobRecord | None:
        with self._connect() as session:
            statement = select(DbRunJob).where(DbRunJob.status == "queued")
            if job_id:
                statement = statement.where(DbRunJob.id == job_id)
            statement = statement.order_by(DbRunJob.created_at.asc())
            if session.bind and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            job = session.scalar(statement)
            if not job:
                return None
            job.status = "running"
            job.error = None
            job.updated_at = utc_now()
            session.commit()
            return self._job_to_record(job)

    def requeue_interrupted_run_jobs(self) -> int:
        with self._connect() as session:
            result = session.execute(
                update(DbRunJob)
                .where(DbRunJob.status == "running", DbRunJob.run_id.is_(None))
                .values(
                    status="queued",
                    error="服务重启后已自动重新入队。",
                    updated_at=utc_now(),
                )
            )
            session.commit()
        return result.rowcount

    def cancel_run_job(self, job_id: str, user_id: str, workspace_id: str) -> RunJobRecord | None:
        with self._connect() as session:
            job = session.scalar(
                select(DbRunJob).where(
                    DbRunJob.id == job_id,
                    DbRunJob.workspace_id == workspace_id,
                )
            )
            if not job:
                return None
            if job.status != "queued":
                raise ValueError("Only queued jobs can be canceled")
            job.status = "canceled"
            job.error = "用户已取消任务。"
            job.updated_at = utc_now()
            session.commit()
            return self._job_to_record(job)

    def retry_run_job(self, job_id: str, user_id: str, workspace_id: str) -> RunJobRecord | None:
        with self._connect() as session:
            job = session.scalar(
                select(DbRunJob).where(
                    DbRunJob.id == job_id,
                    DbRunJob.workspace_id == workspace_id,
                )
            )
            if not job:
                return None
            if job.status != "failed":
                raise ValueError("Only failed jobs can be retried")
            job.status = "queued"
            job.run_id = None
            job.error = None
            job.updated_at = utc_now()
            session.commit()
            return self._job_to_record(job)

    def delete_terminal_run_jobs(
        self,
        user_id: str,
        workspace_id: str,
        workflow_id: str | None = None,
    ) -> int | None:
        if not self.can_access_workspace(workspace_id, user_id, "editor"):
            return None
        with self._connect() as session:
            statement = delete(DbRunJob).where(
                DbRunJob.workspace_id == workspace_id,
                DbRunJob.status.in_(["succeeded", "failed", "canceled"]),
            )
            if workflow_id:
                statement = statement.where(DbRunJob.workflow_id == workflow_id)
            result = session.execute(statement)
            session.commit()
        return result.rowcount

    def get_run_job(self, job_id: str, user_id: str, workspace_id: str | None = None) -> RunJobRecord | None:
        workspace_id = workspace_id or self.ensure_default_workspace(user_id)
        with self._connect() as session:
            job = session.scalar(
                select(DbRunJob).where(DbRunJob.id == job_id, DbRunJob.workspace_id == workspace_id)
            )
        return self._job_to_record(job) if job else None

    def get_run_job_user_id(self, job_id: str) -> str:
        with self._connect() as session:
            user_id = session.scalar(select(DbRunJob.user_id).where(DbRunJob.id == job_id))
        if not user_id:
            raise RuntimeError("Run job not found")
        return user_id

    def get_run_job_workspace_id(self, job_id: str) -> str:
        with self._connect() as session:
            workspace_id = session.scalar(select(DbRunJob.workspace_id).where(DbRunJob.id == job_id))
        if not workspace_id:
            raise RuntimeError("Run job not found")
        return workspace_id

    def get_workflow_for_job(self, workflow_id: str, job_id: str) -> WorkflowRecord | None:
        with self._connect() as session:
            job = session.scalar(select(DbRunJob).where(DbRunJob.id == job_id))
            if not job:
                return None
            workflow = session.scalar(
                select(DbWorkflow).where(
                    DbWorkflow.id == workflow_id,
                    DbWorkflow.workspace_id == job.workspace_id,
                )
            )
        return self._workflow_to_record(workflow) if workflow else None

    def get_runtime_model_config_for_job(self, job_id: str, provider: str) -> dict[str, str | bool] | None:
        workspace_id = self.get_run_job_workspace_id(job_id)
        return self.get_runtime_model_config(workspace_id, provider)

    def create_run_for_job(
        self,
        job_id: str,
        workflow_id: str | None,
        workflow_name: str,
        input_text: str,
        response: RunResponse,
    ) -> RunRecord:
        with self._connect() as session:
            job = session.scalar(select(DbRunJob).where(DbRunJob.id == job_id))
            if not job:
                raise RuntimeError("Run job not found")
            user_id = job.user_id
            workspace_id = job.workspace_id
        return self.create_run(workflow_id, user_id, workflow_name, input_text, response, workspace_id)

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

    def list_evaluation_datasets(self, user_id: str, workspace_id: str) -> list[EvaluationDatasetRecord] | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            datasets = session.scalars(
                select(DbEvaluationDataset)
                .where(DbEvaluationDataset.workspace_id == workspace_id)
                .order_by(DbEvaluationDataset.updated_at.desc())
            ).all()
            counts = dict(
                session.execute(
                    select(DbEvaluationCase.dataset_id, func.count())
                    .where(DbEvaluationCase.workspace_id == workspace_id)
                    .group_by(DbEvaluationCase.dataset_id)
                ).all()
            )
        return [self._evaluation_dataset_to_record(dataset, [], int(counts.get(dataset.id, 0))) for dataset in datasets]

    def get_evaluation_dataset(
        self,
        dataset_id: str,
        user_id: str,
        workspace_id: str,
    ) -> EvaluationDatasetRecord | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            dataset = session.scalar(
                select(DbEvaluationDataset).where(
                    DbEvaluationDataset.id == dataset_id,
                    DbEvaluationDataset.workspace_id == workspace_id,
                )
            )
            if not dataset:
                return None
            cases = session.scalars(
                select(DbEvaluationCase)
                .where(DbEvaluationCase.dataset_id == dataset_id, DbEvaluationCase.workspace_id == workspace_id)
                .order_by(DbEvaluationCase.created_at.asc())
            ).all()
        return self._evaluation_dataset_to_record(dataset, [self._evaluation_case_to_record(row) for row in cases], len(cases))

    def create_evaluation_dataset(
        self,
        payload: EvaluationDatasetPayload,
        user_id: str,
        workspace_id: str,
    ) -> EvaluationDatasetRecord | None:
        if not self.can_access_workspace(workspace_id, user_id, "editor"):
            return None
        now = utc_now()
        dataset = DbEvaluationDataset(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=payload.name.strip(),
            description=payload.description.strip(),
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as session:
            session.add(dataset)
            for case_payload in payload.cases:
                session.add(self._new_evaluation_case(dataset.id, workspace_id, case_payload, now))
            session.commit()
        return self.get_evaluation_dataset(dataset.id, user_id, workspace_id)

    def update_evaluation_dataset(
        self,
        dataset_id: str,
        payload: EvaluationDatasetPayload,
        user_id: str,
        workspace_id: str,
    ) -> EvaluationDatasetRecord | None:
        if not self.can_access_workspace(workspace_id, user_id, "editor"):
            return None
        now = utc_now()
        with self._connect() as session:
            dataset = session.scalar(
                select(DbEvaluationDataset).where(
                    DbEvaluationDataset.id == dataset_id,
                    DbEvaluationDataset.workspace_id == workspace_id,
                )
            )
            if not dataset:
                return None
            dataset.name = payload.name.strip()
            dataset.description = payload.description.strip()
            dataset.updated_at = now
            session.execute(delete(DbEvaluationCase).where(DbEvaluationCase.dataset_id == dataset_id))
            for case_payload in payload.cases:
                session.add(self._new_evaluation_case(dataset_id, workspace_id, case_payload, now))
            session.commit()
        return self.get_evaluation_dataset(dataset_id, user_id, workspace_id)

    def delete_evaluation_dataset(self, dataset_id: str, user_id: str, workspace_id: str) -> bool | None:
        if not self.can_access_workspace(workspace_id, user_id, "editor"):
            return None
        with self._connect() as session:
            dataset = session.scalar(
                select(DbEvaluationDataset).where(
                    DbEvaluationDataset.id == dataset_id,
                    DbEvaluationDataset.workspace_id == workspace_id,
                )
            )
            if not dataset:
                return False
            session.execute(delete(DbEvaluationRun).where(DbEvaluationRun.dataset_id == dataset_id))
            session.execute(delete(DbEvaluationCase).where(DbEvaluationCase.dataset_id == dataset_id))
            session.delete(dataset)
            session.commit()
        return True

    def create_evaluation_run(
        self,
        dataset: EvaluationDatasetRecord,
        workflow: WorkflowRecord,
        user_id: str,
        workspace_id: str,
        results: list[EvaluationCaseResult],
    ) -> EvaluationRunRecord:
        now = utc_now()
        total_cases = len(results)
        passed_cases = sum(1 for result in results if result.passed)
        failed_cases = total_cases - passed_cases
        average_duration_ms = round(sum(result.duration_ms for result in results) / total_cases) if total_cases else 0
        status = "passed" if total_cases > 0 and failed_cases == 0 else "failed"
        row = DbEvaluationRun(
            id=str(uuid.uuid4()),
            dataset_id=dataset.id,
            workspace_id=workspace_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status=status,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            average_duration_ms=average_duration_ms,
            results_json=json.dumps([result.model_dump() for result in results], ensure_ascii=False),
            created_by=user_id,
            created_at=now,
        )
        with self._connect() as session:
            session.add(row)
            session.commit()
        return self._evaluation_run_to_record(row, dataset.name)

    def list_evaluation_runs(
        self,
        user_id: str,
        workspace_id: str,
        dataset_id: str | None = None,
    ) -> list[EvaluationRunRecord] | None:
        if not self.can_access_workspace(workspace_id, user_id):
            return None
        with self._connect() as session:
            statement = (
                select(DbEvaluationRun, DbEvaluationDataset.name)
                .join(DbEvaluationDataset, DbEvaluationDataset.id == DbEvaluationRun.dataset_id)
                .where(DbEvaluationRun.workspace_id == workspace_id)
            )
            if dataset_id:
                statement = statement.where(DbEvaluationRun.dataset_id == dataset_id)
            rows = session.execute(statement.order_by(DbEvaluationRun.created_at.desc()).limit(100)).all()
        return [self._evaluation_run_to_record(run, dataset_name) for run, dataset_name in rows]

    def _new_evaluation_case(
        self,
        dataset_id: str,
        workspace_id: str,
        payload: EvaluationCasePayload,
        now: str,
    ) -> DbEvaluationCase:
        keywords = [keyword.strip() for keyword in payload.expected_keywords if keyword.strip()]
        return DbEvaluationCase(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            input_text=payload.input_text,
            expected_output=payload.expected_output,
            expected_keywords_json=json.dumps(keywords, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )

    def _workflow_to_record(self, workflow: DbWorkflow) -> WorkflowRecord:
        return WorkflowRecord(
            id=workflow.id,
            name=workflow.name,
            version=workflow.version,
            nodes=json.loads(workflow.nodes_json),
            edges=json.loads(workflow.edges_json),
            archived=bool(workflow.archived),
            publish_status=getattr(workflow, "publish_status", "draft") or "draft",
            published_version_id=getattr(workflow, "published_version_id", None),
            published_at=getattr(workflow, "published_at", None),
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
            cost_summary=summarize_run_cost(json.loads(run.steps_json)),
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

    def _evaluation_case_to_record(self, row: DbEvaluationCase) -> EvaluationCaseRecord:
        return EvaluationCaseRecord(
            id=row.id,
            input_text=row.input_text,
            expected_output=row.expected_output,
            expected_keywords=json.loads(row.expected_keywords_json),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _evaluation_dataset_to_record(
        self,
        row: DbEvaluationDataset,
        cases: list,
        case_count: int,
    ) -> EvaluationDatasetRecord:
        return EvaluationDatasetRecord(
            id=row.id,
            name=row.name,
            description=row.description,
            case_count=case_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
            cases=cases,
        )

    def _evaluation_run_to_record(self, row: DbEvaluationRun, dataset_name: str) -> EvaluationRunRecord:
        results = [EvaluationCaseResult(**item) for item in json.loads(row.results_json)]
        pass_rate = round((row.passed_cases / row.total_cases) * 100, 2) if row.total_cases else 0
        return EvaluationRunRecord(
            id=row.id,
            dataset_id=row.dataset_id,
            dataset_name=dataset_name,
            workflow_id=row.workflow_id,
            workflow_name=row.workflow_name,
            status=row.status,
            total_cases=row.total_cases,
            passed_cases=row.passed_cases,
            failed_cases=row.failed_cases,
            pass_rate=pass_rate,
            average_duration_ms=row.average_duration_ms,
            created_by=row.created_by,
            created_at=row.created_at,
            results=results,
        )

    def _workflow_version_to_record(self, version: DbWorkflowVersion) -> WorkflowVersionRecord:
        return WorkflowVersionRecord(
            id=version.id,
            workflow_id=version.workflow_id,
            sequence=version.sequence,
            name=version.name,
            version=version.version,
            nodes=json.loads(version.nodes_json),
            edges=json.loads(version.edges_json),
            archived=bool(version.archived),
            is_published=bool(getattr(version, "is_published", False)),
            created_by=version.created_by,
            note=version.note,
            created_at=version.created_at,
        )

    def _audit_log_to_record(self, row: DbAuditLog) -> AuditLogRecord:
        return AuditLogRecord(
            id=row.id,
            workspace_id=row.workspace_id,
            actor_user_id=row.actor_user_id,
            actor_username=row.actor_username,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            summary=row.summary,
            metadata=json.loads(row.metadata_json),
            created_at=row.created_at,
        )


default_store = WorkflowStore(session_factory=SessionLocal, db_path=DATABASE_PATH, engine=default_engine)

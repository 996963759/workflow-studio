"""durable runs and execution mode

Revision ID: 0010_durable_runs_execution_mode
Revises: 0009_evaluation_system
Create Date: 2026-07-16 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_durable_runs_execution_mode"
down_revision: Union[str, Sequence[str], None] = "0009_evaluation_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("workflow_snapshot_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("runs", sa.Column("workflow_version", sa.String(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("execution_mode", sa.String(), nullable=False, server_default="development"),
    )
    op.add_column("runs", sa.Column("updated_at", sa.String(), nullable=True))
    op.execute("UPDATE runs SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("runs", "updated_at", nullable=False)

    op.add_column("run_jobs", sa.Column("workflow_snapshot_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("run_jobs", sa.Column("workflow_version", sa.String(), nullable=True))
    op.add_column(
        "run_jobs",
        sa.Column("execution_mode", sa.String(), nullable=False, server_default="development"),
    )
    op.add_column(
        "run_jobs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE run_jobs AS job
        SET workflow_snapshot_json = json_build_object(
            'name', workflow.name,
            'version', workflow.version,
            'nodes', workflow.nodes_json::json,
            'edges', workflow.edges_json::json,
            'archived', workflow.archived
        )::text,
        workflow_version = workflow.version
        FROM workflows AS workflow
        WHERE workflow.id = job.workflow_id
        """
    )


def downgrade() -> None:
    op.drop_column("run_jobs", "cancel_requested")
    op.drop_column("run_jobs", "execution_mode")
    op.drop_column("run_jobs", "workflow_version")
    op.drop_column("run_jobs", "workflow_snapshot_json")
    op.drop_column("runs", "updated_at")
    op.drop_column("runs", "execution_mode")
    op.drop_column("runs", "workflow_version")
    op.drop_column("runs", "workflow_snapshot_json")

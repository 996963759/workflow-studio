"""workspaces jobs vectors

Revision ID: 0002_workspaces_jobs_vectors
Revises: 0001_initial_schema
Create Date: 2026-04-30 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_workspaces_jobs_vectors"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspaces_owner_id"), "workspaces", ["owner_id"], unique=False)
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspace_members_user_id"), "workspace_members", ["user_id"], unique=False)
    op.create_index(op.f("ix_workspace_members_workspace_id"), "workspace_members", ["workspace_id"], unique=False)
    op.add_column("workflows", sa.Column("workspace_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_workflows_workspace_id"), "workflows", ["workspace_id"], unique=False)
    op.add_column("runs", sa.Column("workspace_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_runs_workspace_id"), "runs", ["workspace_id"], unique=False)
    op.create_table(
        "run_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_jobs_run_id"), "run_jobs", ["run_id"], unique=False)
    op.create_index(op.f("ix_run_jobs_status"), "run_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_run_jobs_user_id"), "run_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_run_jobs_workflow_id"), "run_jobs", ["workflow_id"], unique=False)
    op.create_index(op.f("ix_run_jobs_workspace_id"), "run_jobs", ["workspace_id"], unique=False)
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("document_name", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_chunks_document_name"), "knowledge_chunks", ["document_name"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_user_id"), "knowledge_chunks", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_workspace_id"), "knowledge_chunks", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_chunks_workspace_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_user_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_name"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(op.f("ix_run_jobs_workspace_id"), table_name="run_jobs")
    op.drop_index(op.f("ix_run_jobs_workflow_id"), table_name="run_jobs")
    op.drop_index(op.f("ix_run_jobs_user_id"), table_name="run_jobs")
    op.drop_index(op.f("ix_run_jobs_status"), table_name="run_jobs")
    op.drop_index(op.f("ix_run_jobs_run_id"), table_name="run_jobs")
    op.drop_table("run_jobs")
    op.drop_index(op.f("ix_runs_workspace_id"), table_name="runs")
    op.drop_column("runs", "workspace_id")
    op.drop_index(op.f("ix_workflows_workspace_id"), table_name="workflows")
    op.drop_column("workflows", "workspace_id")
    op.drop_index(op.f("ix_workspace_members_workspace_id"), table_name="workspace_members")
    op.drop_index(op.f("ix_workspace_members_user_id"), table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index(op.f("ix_workspaces_owner_id"), table_name="workspaces")
    op.drop_table("workspaces")

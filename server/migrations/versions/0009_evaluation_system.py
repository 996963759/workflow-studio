"""evaluation system

Revision ID: 0009_evaluation_system
Revises: 0008_workflow_publish_state
Create Date: 2026-05-24 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_evaluation_system"
down_revision: Union[str, Sequence[str], None] = "0008_workflow_publish_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_datasets_created_by"), "evaluation_datasets", ["created_by"], unique=False)
    op.create_index(op.f("ix_evaluation_datasets_workspace_id"), "evaluation_datasets", ["workspace_id"], unique=False)

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("expected_keywords_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_cases_dataset_id"), "evaluation_cases", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_evaluation_cases_workspace_id"), "evaluation_cases", ["workspace_id"], unique=False)

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=True),
        sa.Column("workflow_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("average_duration_ms", sa.Integer(), nullable=False),
        sa.Column("results_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_runs_created_by"), "evaluation_runs", ["created_by"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_dataset_id"), "evaluation_runs", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_workflow_id"), "evaluation_runs", ["workflow_id"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_workspace_id"), "evaluation_runs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_runs_workspace_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_workflow_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_status"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_dataset_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_created_by"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(op.f("ix_evaluation_cases_workspace_id"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_dataset_id"), table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index(op.f("ix_evaluation_datasets_workspace_id"), table_name="evaluation_datasets")
    op.drop_index(op.f("ix_evaluation_datasets_created_by"), table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")


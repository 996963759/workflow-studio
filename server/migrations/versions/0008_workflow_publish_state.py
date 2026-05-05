"""workflow publish state

Revision ID: 0008_workflow_publish_state
Revises: 0007_invitation_expiration
Create Date: 2026-05-06 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_workflow_publish_state"
down_revision: Union[str, Sequence[str], None] = "0007_invitation_expiration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("publish_status", sa.String(), nullable=False, server_default="draft"))
    op.add_column("workflows", sa.Column("published_version_id", sa.String(), nullable=True))
    op.add_column("workflows", sa.Column("published_at", sa.String(), nullable=True))
    op.create_index(op.f("ix_workflows_published_version_id"), "workflows", ["published_version_id"], unique=False)
    op.add_column("workflow_versions", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("workflow_versions", "is_published")
    op.drop_index(op.f("ix_workflows_published_version_id"), table_name="workflows")
    op.drop_column("workflows", "published_at")
    op.drop_column("workflows", "published_version_id")
    op.drop_column("workflows", "publish_status")

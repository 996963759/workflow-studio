"""workspace invitations

Revision ID: 0006_workspace_invitations
Revises: 0005_session_expiration
Create Date: 2026-05-05 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_workspace_invitations"
down_revision: Union[str, Sequence[str], None] = "0005_session_expiration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("accepted_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("accepted_at", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_workspace_invitations_accepted_by"), "workspace_invitations", ["accepted_by"], unique=False)
    op.create_index(op.f("ix_workspace_invitations_code"), "workspace_invitations", ["code"], unique=False)
    op.create_index(op.f("ix_workspace_invitations_created_by"), "workspace_invitations", ["created_by"], unique=False)
    op.create_index(op.f("ix_workspace_invitations_workspace_id"), "workspace_invitations", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_invitations_workspace_id"), table_name="workspace_invitations")
    op.drop_index(op.f("ix_workspace_invitations_created_by"), table_name="workspace_invitations")
    op.drop_index(op.f("ix_workspace_invitations_code"), table_name="workspace_invitations")
    op.drop_index(op.f("ix_workspace_invitations_accepted_by"), table_name="workspace_invitations")
    op.drop_table("workspace_invitations")

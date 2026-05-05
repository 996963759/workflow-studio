"""invitation expiration

Revision ID: 0007_invitation_expiration
Revises: 0006_workspace_invitations
Create Date: 2026-05-05 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_invitation_expiration"
down_revision: Union[str, Sequence[str], None] = "0006_workspace_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_invitations",
        sa.Column(
            "expires_at",
            sa.String(),
            nullable=False,
            server_default="9999-12-31T23:59:59+00:00",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_invitations", "expires_at")

"""Remove the unused rep open/closed status.

Revision ID: 7a9c1d4e6b20
Revises: e14f7c2a9b30
Create Date: 2026-10-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a9c1d4e6b20"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e14f7c2a9b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user", "rep_is_open")


def downgrade() -> None:
    op.add_column(
        "user",
        sa.Column("rep_is_open", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

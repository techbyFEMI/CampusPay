"""add_developer_role_enum

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-06 13:20:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'Developer' value to PostgreSQL approles enum."""
    op.execute("ALTER TYPE approles ADD VALUE IF NOT EXISTS 'Developer'")


def downgrade() -> None:
    """Downgrade schema."""
    pass

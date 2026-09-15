"""add_rep_to_approles_enum

Revision ID: a1b2c3d4e5f6
Revises: e93a90ae97c2
Create Date: 2026-09-06 13:14:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e93a90ae97c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'Rep' value to PostgreSQL approles enum."""
    op.execute("ALTER TYPE approles ADD VALUE IF NOT EXISTS 'Rep'")


def downgrade() -> None:
    """Downgrade schema."""
    # Note: PostgreSQL does not support removing values from ENUMs easily.
    pass

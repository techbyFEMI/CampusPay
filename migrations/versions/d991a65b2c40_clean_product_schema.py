"""Build a clean pre-launch schema around Supabase identity and kobo balances.

Revision ID: d991a65b2c40
Revises: c86d4fa21b09
Create Date: 2026-10-07

This is an intentional clean-slate migration for the pre-launch product rebuild.
It drops the existing application tables and their data before creating the new
schema. Do not apply it to an environment whose data must be retained.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.models import Base


revision: str = "d991a65b2c40"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c86d4fa21b09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    legacy_tables = set(sa.inspect(bind).get_table_names())
    for table_name in ("wallet_ledger", "webhookEvents"):
        if table_name in legacy_tables:
            op.drop_table(table_name)
    Base.metadata.drop_all(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS orderstat")
        op.execute("DROP TYPE IF EXISTS payoutstat")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    raise RuntimeError(
        "This clean-slate schema rebuild is intentionally irreversible; restore a database backup instead."
    )

"""add_security_constraints_and_idempotency

Revision ID: a6e38354e809
Revises: 9e5d662e6660
Create Date: 2026-09-15 02:07:56.508854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6e38354e809'  # pragma: allowlist secret

down_revision: Union[str, Sequence[str], None] = '9e5d662e6660'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('order', sa.Column('idempotency_key', sa.String(), nullable=True))
    op.create_index(op.f('ix_order_idempotency_key'), 'order', ['idempotency_key'], unique=True)
    op.add_column('user', sa.Column('failed_pin_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('user', sa.Column('pin_locked_until', sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TABLE \"order\" ADD CONSTRAINT ck_orders_item_amount_positive CHECK (item_amount > 0)")
    op.execute("ALTER TABLE wallet ADD CONSTRAINT ck_wallets_available_balance_non_negative CHECK (available_balance >= 0)")
    op.execute("ALTER TABLE wallet ADD CONSTRAINT ck_wallets_locked_balance_non_negative CHECK (locked_balance >= 0)")
    op.execute("ALTER TABLE wallet_ledger ADD CONSTRAINT ck_wallet_ledger_amount_positive CHECK (amount > 0)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE wallet_ledger DROP CONSTRAINT IF EXISTS ck_wallet_ledger_amount_positive")
    op.execute("ALTER TABLE wallet DROP CONSTRAINT IF EXISTS ck_wallets_locked_balance_non_negative")
    op.execute("ALTER TABLE wallet DROP CONSTRAINT IF EXISTS ck_wallets_available_balance_non_negative")
    op.execute("ALTER TABLE \"order\" DROP CONSTRAINT IF EXISTS ck_orders_item_amount_positive")
    op.drop_column('user', 'pin_locked_until')
    op.drop_column('user', 'failed_pin_attempts')
    op.drop_index(op.f('ix_order_idempotency_key'), table_name='order')
    op.drop_column('order', 'idempotency_key')

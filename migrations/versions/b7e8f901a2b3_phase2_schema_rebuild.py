"""phase2 schema rebuild

Revision ID: b7e8f901a2b3
Revises: a6e38354e809
Create Date: 2026-10-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7e8f901a2b3'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = 'a6e38354e809'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. New Enums
    paymentstat_enum = sa.Enum('pending', 'approved', 'failed', name='paymentstat')
    deliverystat_enum = sa.Enum('awaiting_delivery', 'delivered', name='deliverystat')
    accounttype_enum = sa.Enum('student_wallet', 'rep_account', 'platform_revenue', 'external_paystack', name='accounttype')
    entrytype_enum = sa.Enum('debit', 'credit', name='entrytype')
    kycstat_enum = sa.Enum('pending', 'verified', 'failed', name='kycstat')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        paymentstat_enum.create(bind, checkfirst=True)
        deliverystat_enum.create(bind, checkfirst=True)
        accounttype_enum.create(bind, checkfirst=True)
        entrytype_enum.create(bind, checkfirst=True)
        kycstat_enum.create(bind, checkfirst=True)

    # 2. Update user table
    op.add_column('user', sa.Column('dva_account_number', sa.String(), nullable=True))
    op.add_column('user', sa.Column('dva_bank_name', sa.String(), nullable=True))
    op.add_column('user', sa.Column('nin_verification_ref', sa.String(), nullable=True))
    op.add_column('user', sa.Column('nin_verification_status', sa.Enum('pending', 'verified', 'failed', name='kycstat', create_type=False), nullable=True))
    op.add_column('user', sa.Column('bvn_verification_ref', sa.String(), nullable=True))
    op.add_column('user', sa.Column('bvn_verification_status', sa.Enum('pending', 'verified', 'failed', name='kycstat', create_type=False), nullable=True))

    # 3. Update product table
    op.add_column('product', sa.Column('price_kobo', sa.BigInteger(), nullable=True))

    # 4. Update wallet table
    op.add_column('wallet', sa.Column('balance_kobo', sa.BigInteger(), nullable=True, server_default='0'))

    # 5. Update webhookEvents table
    op.add_column('webhookEvents', sa.Column('amount_kobo', sa.BigInteger(), nullable=True))

    # 6. Update order table
    op.add_column('order', sa.Column('product_id', sa.String(), sa.ForeignKey('product.product_id'), nullable=True))
    op.add_column('order', sa.Column('item_price_kobo', sa.BigInteger(), nullable=True))
    op.add_column('order', sa.Column('fee_kobo', sa.BigInteger(), nullable=True))
    op.add_column('order', sa.Column('rep_share_kobo', sa.BigInteger(), nullable=True))
    op.add_column('order', sa.Column('campuspay_share_kobo', sa.BigInteger(), nullable=True))
    op.add_column('order', sa.Column('provider_cost_kobo', sa.BigInteger(), nullable=True, server_default='0'))
    op.add_column('order', sa.Column('payment_status', sa.Enum('pending', 'approved', 'failed', name='paymentstat', create_type=False), nullable=False, server_default='pending'))
    op.add_column('order', sa.Column('delivery_status', sa.Enum('awaiting_delivery', 'delivered', name='deliverystat', create_type=False), nullable=False, server_default='awaiting_delivery'))

    # 7. Update wallet_ledger table
    op.add_column('wallet_ledger', sa.Column('amount_kobo', sa.BigInteger(), nullable=True))

    # 8. Create ledger_accounts table
    op.create_table(
        'ledger_accounts',
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('account_type', sa.Enum('student_wallet', 'rep_account', 'platform_revenue', 'external_paystack', name='accounttype', create_type=False), nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('user.user_id'), nullable=True),
        sa.Column('balance_kobo', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='NGN'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('account_id'),
    )

    # 9. Create journals table
    op.create_table(
        'journals',
        sa.Column('journal_id', sa.String(), nullable=False),
        sa.Column('reference', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('journal_id'),
    )
    op.create_index('ix_journals_reference', 'journals', ['reference'])

    # 10. Create journal_entries table
    op.create_table(
        'journal_entries',
        sa.Column('entry_id', sa.String(), nullable=False),
        sa.Column('journal_id', sa.String(), sa.ForeignKey('journals.journal_id'), nullable=False),
        sa.Column('account_id', sa.String(), sa.ForeignKey('ledger_accounts.account_id'), nullable=False),
        sa.Column('entry_type', sa.Enum('debit', 'credit', name='entrytype', create_type=False), nullable=False),
        sa.Column('amount_kobo', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('entry_id'),
    )

    # 11. Create transfer_attempts table
    op.create_table(
        'transfer_attempts',
        sa.Column('transfer_attempt_id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), sa.ForeignKey('order.order_id'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('provider_reference', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('not_attempted', 'pending', 'success', 'failed', name='payoutstat', create_type=False), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('transfer_attempt_id'),
    )

    # 12. Create idempotency_keys table
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('caller_user_id', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == 'postgresql' else sa.JSON(), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('caller_user_id', 'idempotency_key', name='uq_idempotency_caller_key'),
    )
    op.create_index('ix_idempotency_keys_caller_user_id', 'idempotency_keys', ['caller_user_id'])


def downgrade() -> None:
    op.drop_index('ix_idempotency_keys_caller_user_id', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_table('transfer_attempts')
    op.drop_table('journal_entries')
    op.drop_index('ix_journals_reference', table_name='journals')
    op.drop_table('journals')
    op.drop_table('ledger_accounts')
    op.drop_column('wallet_ledger', 'amount_kobo')
    op.drop_column('order', 'delivery_status')
    op.drop_column('order', 'payment_status')
    op.drop_column('order', 'provider_cost_kobo')
    op.drop_column('order', 'campuspay_share_kobo')
    op.drop_column('order', 'rep_share_kobo')
    op.drop_column('order', 'fee_kobo')
    op.drop_column('order', 'item_price_kobo')
    op.drop_column('order', 'product_id')
    op.drop_column('webhookEvents', 'amount_kobo')
    op.drop_column('wallet_ledger', 'amount_kobo')
    op.drop_column('wallet', 'balance_kobo')
    op.drop_column('product', 'price_kobo')
    op.drop_column('user', 'bvn_verification_status')
    op.drop_column('user', 'bvn_verification_ref')
    op.drop_column('user', 'nin_verification_status')
    op.drop_column('user', 'nin_verification_ref')
    op.drop_column('user', 'dva_bank_name')
    op.drop_column('user', 'dva_account_number')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        for enum_name in ('kycstat', 'entrytype', 'accounttype', 'deliverystat', 'paymentstat'):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)

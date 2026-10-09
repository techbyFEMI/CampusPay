"""Tighten Phase 2 financial and transfer-attempt constraints.

Revision ID: c86d4fa21b09
Revises: b7e8f901a2b3
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c86d4fa21b09"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b7e8f901a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    op.add_column("user", sa.Column("nin_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("nin_hmac", sa.String(length=64), nullable=True))
    op.add_column("user", sa.Column("bvn_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("bvn_hmac", sa.String(length=64), nullable=True))
    op.add_column("order", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wallet_ledger", sa.Column("balance_before_kobo", sa.BigInteger(), nullable=True))
    op.add_column("wallet_ledger", sa.Column("balance_after_kobo", sa.BigInteger(), nullable=True))
    if is_postgresql:
        op.alter_column(
            "idempotency_keys",
            "response_status",
            existing_type=sa.Integer(),
            type_=sa.SmallInteger(),
        )
        transfer_attempt_status = sa.Enum(
            "pending", "success", "failed", name="transferattemptstat"
        )
        transfer_attempt_status.create(bind, checkfirst=True)
        op.execute(
            "ALTER TABLE transfer_attempts "
            "ALTER COLUMN status TYPE transferattemptstat "
            "USING (CASE status::text "
            "WHEN 'not_attempted' THEN 'pending' "
            "ELSE status::text END)::transferattemptstat"
        )

    # Phase 2 originally created a non-unique lookup index. The unique
    # constraint below is the authoritative idempotency guard for journals.
    op.drop_index("ix_journals_reference", table_name="journals")

    # SQLite stores SQLAlchemy enums as strings; PostgreSQL uses the new enum above.
    op.create_unique_constraint(
        "uq_transfer_attempt_order_number",
        "transfer_attempts",
        ["order_id", "attempt_number"],
    )
    op.create_unique_constraint(
        "uq_transfer_attempt_provider_ref",
        "transfer_attempts",
        ["provider_reference"],
    )
    op.create_check_constraint(
        "ck_transfer_attempt_status_valid",
        "transfer_attempts",
        "status IN ('pending', 'success', 'failed')",
    )
    op.create_check_constraint(
        "ck_transfer_attempt_number_range",
        "transfer_attempts",
        "attempt_number BETWEEN 1 AND 3",
    )
    op.create_unique_constraint(
        "uq_journals_reference", "journals", ["reference"]
    )
    op.create_unique_constraint(
        "uq_ledger_account_owner_type_currency",
        "ledger_accounts",
        ["account_type", "user_id", "currency"],
    )
    op.create_check_constraint(
        "ck_journal_entries_amount_positive",
        "journal_entries",
        "amount_kobo > 0",
    )
    op.create_check_constraint(
        "ck_products_price_kobo_non_negative",
        "product",
        "price_kobo IS NULL OR price_kobo >= 0",
    )
    op.create_check_constraint(
        "ck_wallets_balance_kobo_non_negative",
        "wallet",
        "balance_kobo IS NULL OR balance_kobo >= 0",
    )
    op.create_check_constraint(
        "ck_wallet_ledger_amount_kobo_positive",
        "wallet_ledger",
        "amount_kobo IS NULL OR amount_kobo > 0",
    )
    op.create_check_constraint(
        "ck_wallet_ledger_direction_valid",
        "wallet_ledger",
        "direction IN ('credit', 'debit')",
    )
    op.create_check_constraint(
        "ck_webhook_events_amount_kobo_non_negative",
        "webhookEvents",
        "amount_kobo IS NULL OR amount_kobo >= 0",
    )
    op.create_check_constraint(
        "ck_orders_item_price_kobo_positive",
        "order",
        "item_price_kobo IS NULL OR item_price_kobo > 0",
    )
    op.create_check_constraint(
        "ck_orders_fee_kobo_range",
        "order",
        "fee_kobo IS NULL OR (fee_kobo >= 0 AND fee_kobo <= 5000)",
    )
    op.create_check_constraint(
        "ck_orders_provider_cost_kobo_non_negative",
        "order",
        "provider_cost_kobo IS NULL OR provider_cost_kobo >= 0",
    )
    op.create_check_constraint(
        "ck_orders_shares_non_negative",
        "order",
        "(rep_share_kobo IS NULL OR rep_share_kobo >= 0) AND "
        "(campuspay_share_kobo IS NULL OR campuspay_share_kobo >= 0)",
    )
    op.create_check_constraint(
        "ck_orders_shares_within_fee",
        "order",
        "(rep_share_kobo IS NULL OR campuspay_share_kobo IS NULL OR "
        "rep_share_kobo + campuspay_share_kobo <= fee_kobo)",
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    op.drop_constraint("ck_orders_shares_within_fee", "order", type_="check")
    op.drop_constraint("ck_orders_shares_non_negative", "order", type_="check")
    op.drop_constraint("ck_orders_provider_cost_kobo_non_negative", "order", type_="check")
    op.drop_constraint("ck_orders_fee_kobo_range", "order", type_="check")
    op.drop_constraint("ck_orders_item_price_kobo_positive", "order", type_="check")
    op.drop_constraint("ck_wallet_ledger_direction_valid", "wallet_ledger", type_="check")
    op.drop_constraint("ck_wallet_ledger_amount_kobo_positive", "wallet_ledger", type_="check")
    op.drop_constraint("ck_wallets_balance_kobo_non_negative", "wallet", type_="check")
    op.drop_constraint("ck_webhook_events_amount_kobo_non_negative", "webhookEvents", type_="check")
    op.drop_constraint("ck_products_price_kobo_non_negative", "product", type_="check")
    op.drop_constraint("ck_journal_entries_amount_positive", "journal_entries", type_="check")
    op.drop_constraint("uq_journals_reference", "journals", type_="unique")
    op.drop_constraint("uq_ledger_account_owner_type_currency", "ledger_accounts", type_="unique")
    op.drop_constraint("ck_transfer_attempt_status_valid", "transfer_attempts", type_="check")
    op.drop_constraint("ck_transfer_attempt_number_range", "transfer_attempts", type_="check")
    op.drop_constraint("uq_transfer_attempt_provider_ref", "transfer_attempts", type_="unique")
    op.drop_constraint("uq_transfer_attempt_order_number", "transfer_attempts", type_="unique")

    if is_postgresql:
        op.execute(
            "ALTER TABLE transfer_attempts "
            "ALTER COLUMN status TYPE payoutstat "
            "USING status::text::payoutstat"
        )
        sa.Enum(name="transferattemptstat").drop(bind, checkfirst=True)

    op.create_index("ix_journals_reference", "journals", ["reference"])

    op.drop_column("user", "bvn_hmac")
    op.drop_column("user", "bvn_verified_at")
    op.drop_column("user", "nin_hmac")
    op.drop_column("user", "nin_verified_at")
    op.drop_column("wallet_ledger", "balance_after_kobo")
    op.drop_column("wallet_ledger", "balance_before_kobo")
    op.drop_column("order", "delivered_at")
    if is_postgresql:
        op.alter_column(
            "idempotency_keys",
            "response_status",
            existing_type=sa.SmallInteger(),
            type_=sa.Integer(),
        )

"""Remove legacy payout details and use rep terminology in the schema.

Revision ID: e14f7c2a9b30
Revises: d991a65b2c40
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e14f7c2a9b30"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d991a65b2c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("user")}
    for column_name in (
        "vendor_bank_account",
        "vendor_bank_code",
        "vendor_bank_name",
    ):
        if column_name in user_columns:
            op.drop_column("user", column_name)

    idempotency_columns = {
        column["name"]
        for column in inspector.get_columns("idempotency_keys")
    }
    if "expires_at" in idempotency_columns:
        op.drop_column("idempotency_keys", "expires_at")

    _rename_column("user", "vendor_location", "rep_location")
    _rename_column("user", "vendor_is_open", "rep_is_open")
    _rename_column("user", "vendor_cover_image_url", "rep_cover_image_url")
    _rename_column("product", "vendor_id", "rep_id")
    _rename_index("product", "ix_product_vendor_id", "ix_product_rep_id")
    _rename_column("order", "vendor_id", "rep_id")
    _rename_index("order", "ix_order_vendor_id", "ix_order_rep_id")


def downgrade() -> None:
    _rename_column("order", "rep_id", "vendor_id")
    _rename_index("order", "ix_order_rep_id", "ix_order_vendor_id")
    _rename_column("product", "rep_id", "vendor_id")
    _rename_index("product", "ix_product_rep_id", "ix_product_vendor_id")
    _rename_column("user", "rep_location", "vendor_location")
    _rename_column("user", "rep_is_open", "vendor_is_open")
    _rename_column("user", "rep_cover_image_url", "vendor_cover_image_url")

    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("user")}
    for column_name in (
        "vendor_bank_account",
        "vendor_bank_code",
        "vendor_bank_name",
    ):
        if column_name not in columns:
            op.add_column("user", sa.Column(column_name, sa.String(), nullable=True))
    idempotency_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("idempotency_keys")
    }
    if "expires_at" not in idempotency_columns:
        op.add_column(
            "idempotency_keys",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def _rename_column(table_name: str, old_name: str, new_name: str) -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
    if old_name in columns and new_name not in columns:
        op.alter_column(table_name, old_name, new_column_name=new_name)


def _rename_index(table_name: str, old_name: str, new_name: str) -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if old_name in indexes:
        op.drop_index(old_name, table_name=table_name)
        indexes.remove(old_name)
    if new_name not in indexes:
        column_name = "rep_id" if new_name.endswith("_rep_id") else "vendor_id"
        op.create_index(new_name, table_name, [column_name], unique=False)

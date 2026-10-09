"""Compatibility imports for the original single-file model module.

New model definitions live in focused domain modules. Existing callers can keep
importing from ``app.models.models`` while they are migrated incrementally.
Importing each module here also registers every table on ``Base.metadata`` for
Alembic and ``create_all``.
"""

from app.core.database import Base
from app.models.catalog import products
from app.models.enums import (
    JSON_TYPE,
    accstatus,
    accounttype,
    approles,
    deliverystat,
    entrytype,
    hookstate,
    kycstat,
    paymentstat,
    transferattemptstat,
)
from app.models.identity import accounts, departments, rosters, users
from app.models.idempotency import IdempotencyKey
from app.models.ledger import Journal, JournalEntry, LedgerAccount
from app.models.orders import TransferAttempt, orders
from app.models.wallet import wallets
from app.models.webhooks import webhook_events

__all__ = [
    "Base",
    "JSON_TYPE",
    "accounts",
    "accstatus",
    "accounttype",
    "approles",
    "departments",
    "deliverystat",
    "entrytype",
    "hookstate",
    "IdempotencyKey",
    "Journal",
    "JournalEntry",
    "kycstat",
    "LedgerAccount",
    "orders",
    "paymentstat",
    "transferattemptstat",
    "products",
    "rosters",
    "TransferAttempt",
    "users",
    "wallets",
    "webhook_events",
]

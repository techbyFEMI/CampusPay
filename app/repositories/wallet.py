from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import accounts, users
from app.models.ledger import Journal, JournalEntry, LedgerAccount
from app.models.wallet import wallets


class WalletRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_wallet_snapshot(self, user_id: str):
        statement = (
            select(users, wallets, accounts)
            .join(wallets, wallets.user_id == users.user_id)
            .outerjoin(accounts, accounts.owner_user_id == users.user_id)
            .where(users.user_id == user_id)
        )
        result = await self.session.execute(statement)
        return result.first()

    async def list_transactions(self, user_id: str, limit: int, offset: int):
        account_ids = select(LedgerAccount.account_id).where(
            LedgerAccount.user_id == user_id
        )
        statement = (
            select(JournalEntry, Journal)
            .join(Journal, Journal.journal_id == JournalEntry.journal_id)
            .where(JournalEntry.account_id.in_(account_ids))
            .order_by(Journal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return result.all()

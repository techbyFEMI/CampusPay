from app.repositories.wallet import WalletRepository
from app.schemas.wallet import TransactionItem, WalletResponse
from app.services.errors import UserNotFoundError


class WalletService:
    def __init__(self, wallet_repository: WalletRepository):
        self.wallet_repository = wallet_repository

    async def get_wallet(self, user_id: str) -> WalletResponse:
        row = await self.wallet_repository.get_wallet_snapshot(user_id)
        if row is None:
            raise UserNotFoundError("User or wallet not found")

        user, wallet, dva = row
        return WalletResponse(
            user_id=user.user_id,
            role=user.role.value,
            full_name=user.full_name,
            balance_kobo=wallet.balance_kobo,
            bank_account_number=dva.bank_account_number if dva else None,
            bank_name=dva.bank_name if dva else None,
        )

    async def list_transactions(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> list[TransactionItem]:
        rows = await self.wallet_repository.list_transactions(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return [
            TransactionItem(
                type=entry.entry_type.value,
                description=journal.reason,
                amount_kobo=entry.amount_kobo,
                direction="+" if entry.entry_type.value == "credit" else "-",
                status="completed",
                created_at=journal.created_at.isoformat(),
            )
            for entry, journal in rows
        ]

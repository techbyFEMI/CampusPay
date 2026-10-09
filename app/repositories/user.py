from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import users
from app.models.wallet import wallets


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_id(self, user_id: str, *, for_update: bool = False):
        statement = select(users).where(users.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_user_by_matric_number(self, matric_number: str):
        result = await self.session.execute(
            select(users).where(users.matric_number == matric_number)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str):
        result = await self.session.execute(select(users).where(users.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_phone(self, phone: str):
        result = await self.session.execute(select(users).where(users.phone == phone))
        return result.scalar_one_or_none()

    def add_user(self, user: users) -> users:
        self.session.add(user)
        return user

    def add_wallet(self, user_id: str) -> wallets:
        wallet = wallets(user_id=user_id, balance_kobo=0, currency="NGN")
        self.session.add(wallet)
        return wallet

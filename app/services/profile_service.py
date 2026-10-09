import asyncio

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository
from app.schemas.profile import ProfileResponse, SetPinRequest
from app.services.errors import UserNotFoundError


class ProfileService:
    def __init__(self, session: AsyncSession, user_repository: UserRepository):
        self.session = session
        self.user_repository = user_repository

    async def get_profile(self, user_id: str) -> ProfileResponse:
        user = await self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User profile not found")
        return ProfileResponse(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email or "",
            phone=user.phone,
            role=user.role.value,
            has_transaction_pin=user.transaction_pin_hash is not None,
        )

    async def set_transaction_pin(self, user_id: str, body: SetPinRequest) -> dict[str, str]:
        user = await self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found")
        pin_hash = await asyncio.to_thread(
            bcrypt.hashpw, body.pin.encode(), bcrypt.gensalt()
        )
        user.transaction_pin_hash = pin_hash.decode()
        await self.session.commit()
        return {"message": "Transaction PIN set successfully"}

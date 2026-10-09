from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.user import UserRepository
from app.schemas.profile import ProfileResponse, SetPinRequest
from app.services.errors import UserNotFoundError
from app.services.profile_service import ProfileService


router = APIRouter(prefix="/api/profile", tags=["profile"])


def _profile_service(db: AsyncSession) -> ProfileService:
    return ProfileService(db, UserRepository(db))


@router.get("", response_model=ProfileResponse)
async def get_profile(
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _profile_service(db).get_profile(auth_user["user_id"])
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/set-pin", status_code=200)
async def set_transaction_pin(
    body: SetPinRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _profile_service(db).set_transaction_pin(
            auth_user["user_id"], body
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.wallet import WalletRepository
from app.schemas.wallet import TransactionItem, WalletResponse
from app.services.errors import UserNotFoundError
from app.services.wallet_service import WalletService


router = APIRouter()


def _wallet_service(db: AsyncSession) -> WalletService:
    return WalletService(WalletRepository(db))


@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _wallet_service(db).get_wallet(auth_user["user_id"])
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/wallet/transactions", response_model=list[TransactionItem])
async def get_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _wallet_service(db).list_transactions(
        user_id=auth_user["user_id"],
        limit=limit,
        offset=offset,
    )

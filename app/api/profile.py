import logging
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_firebase_user
from app.models.models import users, approles
from app.schemas.profile import (
    ProfileResponse,
    SetPinRequest,
    BankItem,
    AccountLookupRequest,
    VendorBankSetupRequest,
)
from app.services.nomba import fetch_banks, lookup_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        firebase_uid = firebase_user.get("uid")

        query = select(users).where(users.firebase_uid == firebase_uid)
        result = await db.execute(query)
        row = result.first()

        if not row:
            raise HTTPException(status_code=404, detail="User profile not found")

        user = row[0]

        return ProfileResponse(
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            phone=user.phone,
            role=user.role.value,
            has_transaction_pin=user.transaction_pin_hash is not None,
            vendor_bank_account=user.vendor_bank_account,
            vendor_bank_code=user.vendor_bank_code,
            vendor_bank_name=user.vendor_bank_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/set-pin", status_code=200)
async def set_transaction_pin(
    body: SetPinRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        firebase_uid = firebase_user.get("uid")

        result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        pin_hash = bcrypt.hashpw(body.pin.encode(), bcrypt.gensalt()).decode()
        user.transaction_pin_hash = pin_hash
        await db.commit()

        logger.info(f"Transaction PIN set for user {user.user_id}")
        return {"message": "Transaction PIN set successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")



@router.get("/banks", response_model=list[BankItem])
async def get_banks(
    firebase_user: dict = Depends(get_current_firebase_user),
):
    """Return all supported Nigerian banks (cached 24 h from Nomba)."""
    try:
        banks = await fetch_banks()
        return [
            BankItem(name=b.get("bankName", b.get("name", "")), code=b.get("bankCode", b.get("code", "")))
            for b in banks
            if b.get("bankCode") or b.get("code")
        ]
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=502, detail="Could not fetch bank list from Nomba")


@router.post("/banks/lookup")
async def resolve_account_name(
    body: AccountLookupRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
):
    """Resolve an account number + bank code to an account name via Nomba."""
    try:
        result = await lookup_account(body.account_number, body.bank_code)
        if result.get("code") != "00":
            raise HTTPException(
                status_code=422,
                detail=result.get("description", "Account lookup failed"),
            )
        data = result.get("data", {})
        account_name = data.get("accountName") or data.get("account_name")
        if not account_name:
            raise HTTPException(status_code=422, detail="Account name not found")
        return {"account_name": account_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=502, detail="Account lookup failed")


@router.patch("/vendor-bank", status_code=200)
async def save_vendor_bank(
    body: VendorBankSetupRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Save (or update) the authenticated vendor's payout bank account."""
    try:
        firebase_uid = firebase_user.get("uid")

        result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.role not in (approles.Rep, approles.Admin):
            raise HTTPException(status_code=403, detail="Only department representatives or admins can set a payout account")

        user.vendor_bank_account = body.account_number
        user.vendor_bank_code = body.bank_code
        user.vendor_bank_name = body.bank_name
        await db.commit()

        logger.info(
            f"Vendor bank account updated: user={user.user_id}, "
            f"bank={body.bank_name}, acct={body.account_number[-4:]}"
        )
        return {
            "message": "Bank account saved successfully",
            "account_name": body.account_name,
            "bank_name": body.bank_name,
            "account_number": body.account_number,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

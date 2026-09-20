from fastapi import Depends, HTTPException, APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_current_firebase_user
from sqlalchemy import select, case, literal_column, union_all
from app.core.database import get_db
from app.models.models import users, wallets, accounts, webhook_events, orders, orderstat, approles
from app.schemas.wallet import WalletResponse, TransactionItem
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


router = APIRouter()

@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        firebase_uid = firebase_user.get("uid")

        if not firebase_uid:
            raise HTTPException(
                status_code=401,
                detail="Invalid Firebase token",
            )

        query = (
            select(users, wallets, accounts)
            .join(wallets, wallets.user_id == users.user_id)
            .outerjoin(accounts, accounts.student_id == users.user_id)
            .where(users.firebase_uid == firebase_uid)
        )

        result = await db.execute(query)
        row = result.first()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="User or wallet not found",
            )

        user, wallet, account = row

        return WalletResponse(
            user_id=user.user_id,
            role=user.role.value,
            full_name=user.full_name,
            available_balance=str(wallet.available_balance),
            locked_balance=str(wallet.locked_balance),
            bank_account_number=account.bank_account_number if account else None,
            bank_name=account.bank_name if account else None,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


@router.get("/wallet/transactions", response_model=list[TransactionItem])
async def get_transactions(
    firebase_user: dict = Depends(get_current_firebase_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    transaction_type: str | None = Query(default=None, alias="type", pattern="^(credit|debit)$"),
    db: AsyncSession = Depends(get_db),
):

    try:
        firebase_uid = firebase_user.get("uid")
        if not firebase_uid:
            raise HTTPException(status_code=401, detail="Invalid Firebase token")

        # Fetch current user to determine role
        user_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        status_case = case(
            (orders.order_status == orderstat.confirmed, "completed"),
            (orders.order_status == orderstat.pending, "processing"),
            (orders.order_status == orderstat.expired, "expired"),
            (orders.order_status == orderstat.refunded, "refunded"),
            else_="unknown"
        )

        if user.role == approles.Student:
            # 1. Credits: Webhook events linked to student's DVAs
            credits_query = select(
                literal_column("'credit'").label("type"),
                literal_column("'Funds Deposit'").label("description"),
                webhook_events.amount.label("amount"),
                literal_column("'+'").label("direction"),
                literal_column("'completed'").label("status"),
                webhook_events.processed_at.label("created_at")
            ).join(
                accounts, accounts.account_reference == webhook_events.account_reference
            ).where(
                accounts.student_id == user.user_id
            )

            # 2. Debits: Orders placed by the student
            debits_query = select(
                literal_column("'debit'").label("type"),
                orders.item_description.label("description"),
                orders.item_amount.label("amount"),
                literal_column("'-'").label("direction"),
                status_case.label("status"),
                orders.created_at.label("created_at")
            ).where(
                orders.student_id == user.user_id
            )

            if transaction_type == "credit":
                main_query = credits_query
            elif transaction_type == "debit":
                main_query = debits_query
            else:
                main_query = union_all(credits_query, debits_query)

        elif user.role in (approles.Rep, approles.Admin):
            # Reps/Admins receive payments (credits) when orders placed with them are processed
            credits_query = select(
                literal_column("'credit'").label("type"),
                orders.item_description.label("description"),
                orders.item_amount.label("amount"),
                literal_column("'+'").label("direction"),
                status_case.label("status"),
                orders.created_at.label("created_at")
            ).where(
                orders.vendor_id == user.user_id
            )

            if transaction_type == "debit":
                return []
            
            main_query = credits_query

        else:
            # Admin or other roles - no transaction history defined here
            return []

        # Wrap in subquery to apply ordering and pagination
        subquery = main_query.subquery()
        stmt = select(
            subquery.c.type,
            subquery.c.description,
            subquery.c.amount,
            subquery.c.direction,
            subquery.c.status,
            subquery.c.created_at
        ).order_by(subquery.c.created_at.desc()).limit(limit).offset(offset)

        res = await db.execute(stmt)
        rows = res.all()

        def format_utc_iso(dt):
            if not dt:
                return ""
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        return [
            TransactionItem(
                type=row.type,
                description=row.description,
                amount=str(row.amount),
                direction=row.direction,
                status=row.status,
                created_at=format_utc_iso(row.created_at)
            )
            for row in rows
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching transactions for user_uid={firebase_user.get('uid')}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
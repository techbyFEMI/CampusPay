import logging
import bcrypt
import jwt
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.models import products as ProductsModel
from app.models.models import users, wallets, orders, orderstat, wallet_ledger, approles
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_firebase_user
from app.schemas.orders import (
    PlaceOrderRequest,
    PlaceOrderResponse,
    ScanQRRequest,
    PendingTransactionItem,
    RepOrderItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])

PLATFORM_FEE = Decimal("0.00")
QR_ALGORITHM = "HS256"


def _write_ledger(
    wallet: wallets,
    user_id: str,
    direction: str,
    amount: Decimal,
    balance_before: Decimal,
    reference: str,
    reason: str,
    order_id: str | None = None,
) -> wallet_ledger:
    """Create a double-entry ledger record for a wallet balance movement."""
    return wallet_ledger(
        wallet_id=wallet.wallet_id,
        user_id=user_id,
        direction=direction,
        amount=amount,
        balance_before=balance_before,
        balance_after=wallet.available_balance,
        reference=reference,
        order_id=order_id,
        reason=reason,
    )


@router.post("", response_model=PlaceOrderResponse, status_code=201)
async def place_order(
    body: PlaceOrderRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Student places an order for a Rep's item.
    - PIN is verified.
    - Funds are debited from student wallet and credited IMMEDIATELY to Rep wallet.
    - Double-entry ledger entries are recorded.
    - Order is created as confirmed with is_collected=False.
    - QR token is returned for physical collection/attendance scan.
    """
    try:
        firebase_uid = firebase_user.get("uid")

        user_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        student = user_result.scalar_one_or_none()

        if not student:
            raise HTTPException(status_code=404, detail="Student user not found")

        if not student.transaction_pin_hash:
            raise HTTPException(
                status_code=403,
                detail="Transaction PIN not set. Please set a 4-digit PIN in your profile before placing orders.",
            )

        pin_valid = bcrypt.checkpw(body.pin.encode(), student.transaction_pin_hash.encode())
        if not pin_valid:
            raise HTTPException(status_code=403, detail="Incorrect transaction PIN")

        student_wallet_res = await db.execute(
            select(wallets)
            .where(wallets.user_id == student.user_id)
            .with_for_update()
        )
        student_wallet = student_wallet_res.scalar_one_or_none()

        if not student_wallet:
            raise HTTPException(status_code=404, detail="Student wallet not found")

        target_rep_id = body.rep_id or body.vendor_id
        rep_result = await db.execute(
            select(users).where(users.user_id == target_rep_id)
        )
        rep = rep_result.scalar_one_or_none()

        if not rep:
            raise HTTPException(status_code=404, detail="Department Representative not found")

        total_charge = body.item_amount + PLATFORM_FEE
        if student_wallet.available_balance < total_charge:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient wallet balance. Required: ₦{total_charge}, "
                    f"Available: ₦{student_wallet.available_balance}"
                ),
            )

        # Get or create Rep's wallet
        rep_wallet_res = await db.execute(
            select(wallets)
            .where(wallets.user_id == rep.user_id)
            .with_for_update()
        )
        rep_wallet = rep_wallet_res.scalar_one_or_none()
        if not rep_wallet:
            rep_wallet = wallets(
                user_id=rep.user_id,
                available_balance=Decimal("0.00"),
                locked_balance=Decimal("0.00"),
                currency="NGN",
            )
            db.add(rep_wallet)
            await db.flush()

        # Execute immediate transfer to Rep wallet
        student_balance_before = student_wallet.available_balance
        rep_balance_before = rep_wallet.available_balance

        student_wallet.available_balance -= total_charge
        student_wallet.updated_at = datetime.now(timezone.utc)

        rep_wallet.available_balance += body.item_amount
        rep_wallet.updated_at = datetime.now(timezone.utc)

        new_order = orders(
            student_id=student.user_id,
            vendor_id=rep.user_id,
            item_description=body.item_description,
            item_amount=body.item_amount,
            escrow_hold=Decimal("0.00"),
            order_status=orderstat.confirmed,
            is_collected=False,
            qr_token="pending",
        )
        db.add(new_order)
        await db.flush()

        # Generate QR payload
        qr_payload = {
            "order_id": new_order.order_id,
            "rep_id": rep.user_id,
            "vendor_id": rep.user_id,
            "student_id": student.user_id,
        }
        signed_token = jwt.encode(qr_payload, settings.SECRET_KEY, algorithm=QR_ALGORITHM)
        new_order.qr_token = signed_token

        # Ledger record: Student Debit
        db.add(_write_ledger(
            wallet=student_wallet,
            user_id=student.user_id,
            direction="debit",
            amount=total_charge,
            balance_before=student_balance_before,
            reference=new_order.order_id,
            reason="student_order_payment",
            order_id=new_order.order_id,
        ))

        # Ledger record: Rep Credit
        db.add(_write_ledger(
            wallet=rep_wallet,
            user_id=rep.user_id,
            direction="credit",
            amount=body.item_amount,
            balance_before=rep_balance_before,
            reference=new_order.order_id,
            reason="rep_payment_received",
            order_id=new_order.order_id,
        ))

        await db.commit()

        logger.info(
            "order_placed_and_credited",
            extra={
                "order_id": new_order.order_id,
                "student_id": student.user_id,
                "rep_id": rep.user_id,
                "item_amount": str(body.item_amount),
            },
        )

        return PlaceOrderResponse(
            order_id=new_order.order_id,
            qr_token=signed_token,
            timer_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            total_charged=str(total_charge),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("place_order_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{order_id}/scan", status_code=200)
async def scan_order_qr(
    order_id: str,
    body: ScanQRRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Distribution Scan Endpoint:
    - Scanned by Course Rep upon physical item distribution to a student.
    - Validates QR token.
    - Marks order as collected (is_collected=True, collected_at=now).
    - Money is NOT moved during scan (funds were credited to Rep at checkout).
    """
    try:
        try:
            token_data = jwt.decode(body.qr_token, settings.SECRET_KEY, algorithms=[QR_ALGORITHM])
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid QR token")

        token_order_id = token_data.get("order_id")
        token_rep_id = token_data.get("rep_id") or token_data.get("vendor_id")

        if token_order_id != order_id:
            raise HTTPException(status_code=401, detail="QR token does not match this order")

        # Authenticate Rep
        firebase_uid = firebase_user.get("uid")
        rep_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        rep = rep_result.scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Course Representative user record not found")

        role = firebase_user.get("role") or firebase_user.get("claims", {}).get("role") or rep.role.value
        if role != approles.Rep.value and role != approles.Admin.value and rep.role != approles.Rep:
            raise HTTPException(status_code=403, detail="Only Department Representatives can perform distribution scans.")

        # Fetch Order
        order_result = await db.execute(
            select(orders).where(orders.order_id == order_id).with_for_update()
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.vendor_id != rep.user_id and token_rep_id != rep.user_id:
            raise HTTPException(status_code=403, detail="This order belongs to a different department representative")

        if order.is_collected:
            raise HTTPException(
                status_code=409,
                detail=f"Item has ALREADY been collected on {order.collected_at.isoformat() if order.collected_at else 'previous scan'}.",
            )

        # Fetch student details for attendance confirmation output
        student_res = await db.execute(
            select(users).where(users.user_id == order.student_id)
        )
        student = student_res.scalar_one_or_none()

        now_utc = datetime.now(timezone.utc)
        order.is_collected = True
        order.collected_at = now_utc

        await db.commit()

        return {
            "message": "Distribution attendance confirmed! Item marked as collected.",
            "order_id": order.order_id,
            "student_name": student.full_name if student else "Student",
            "student_matric": student.matric_number if student else None,
            "item_description": order.item_description,
            "is_collected": True,
            "collected_at": now_utc.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("scan_order_qr_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/rep", response_model=list[RepOrderItem])
async def get_rep_orders(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Rep Dashboard Endpoint:
    Returns the list of all student orders for the Rep's items, including collection status.
    """
    try:
        firebase_uid = firebase_user.get("uid")
        user_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        rep = user_result.scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="User not found")

        student_alias = aliased(users)
        stmt = (
            select(
                orders.order_id,
                orders.item_description,
                orders.item_amount,
                orders.order_status,
                orders.is_collected,
                orders.collected_at,
                orders.created_at,
                student_alias.full_name.label("student_name"),
                student_alias.matric_number.label("student_matric"),
            )
            .join(student_alias, student_alias.user_id == orders.student_id)
            .where(orders.vendor_id == rep.user_id)
            .order_by(orders.created_at.desc())
        )

        result = await db.execute(stmt)
        rows = result.fetchall()

        items = []
        for row in rows:
            created_at_str = row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else ""
            collected_at_str = row.collected_at.isoformat().replace("+00:00", "Z") if row.collected_at else None

            items.append(
                RepOrderItem(
                    order_id=row.order_id,
                    item_description=row.item_description,
                    item_amount=str(row.item_amount),
                    student_name=row.student_name,
                    student_matric=row.student_matric,
                    created_at=created_at_str,
                    order_status=row.order_status.value,
                    is_collected=row.is_collected,
                    collected_at=collected_at_str,
                )
            )
        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_rep_orders_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pending", response_model=list[PendingTransactionItem])
async def get_pending_transactions(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Student Orders Endpoint: Returns active confirmed orders with QR codes."""
    try:
        firebase_uid = firebase_user.get("uid")
        user_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        rep_alias = aliased(users)

        stmt = (
            select(
                orders.order_id,
                orders.item_description.label("name"),
                orders.item_amount.label("price"),
                orders.qr_token,
                orders.created_at,
                orders.is_collected,
                rep_alias.user_id.label("rep_id"),
                rep_alias.full_name.label("rep_name"),
            )
            .join(rep_alias, rep_alias.user_id == orders.vendor_id)
            .where(orders.student_id == user.user_id)
            .order_by(orders.created_at.desc())
        )

        result = await db.execute(stmt)
        rows = result.fetchall()

        items = []
        for row in rows:
            created_at_str = row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else ""

            items.append(
                PendingTransactionItem(
                    order_id=row.order_id,
                    name=row.name,
                    price=str(row.price),
                    status="confirmed",
                    qr_token=row.qr_token,
                    created_at=created_at_str,
                    rep_id=row.rep_id,
                    rep_name=row.rep_name,
                    total_charged=str(row.price),
                    timer_expire_at=created_at_str,
                    is_collected=row.is_collected,
                )
            )
        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_pending_transactions_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
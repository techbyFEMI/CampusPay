import asyncio
import logging
import bcrypt
import jwt
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.models.models import products as ProductsModel
from app.models.models import users, wallets, orders, orderstat, wallet_ledger, approles
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_firebase_user
from app.core.rate_limiter import order_rate_limiter, scan_rate_limiter
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

# QR_SECRET_KEY is used for signing QR tokens (falls back to SECRET_KEY if not explicitly set)
_qr_secret = getattr(settings, "QR_SECRET_KEY", None) or getattr(settings, "SECRET_KEY", "fallback-secret-key")
QR_SECRET: str = _qr_secret



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


@router.post("", response_model=PlaceOrderResponse, status_code=201, dependencies=[Depends(order_rate_limiter)])
async def place_order(

    body: PlaceOrderRequest,
    request: Request,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Student places an order for a Rep's item.
    - Idempotency key check prevents duplicate charges.
    - Product canonical price is looked up server-side if product_id is provided.
    - PIN lockout protection & async bcrypt verification.
    - Deterministic wallet locking (sort user_ids) prevents deadlocks.
    - Funds are debited from student wallet and credited IMMEDIATELY to Rep wallet.
    - Double-entry ledger entries are recorded.
    """
    try:
        idempotency_key = body.idempotency_key or request.headers.get("X-Idempotency-Key")

        firebase_uid = firebase_user.get("uid")

        # Lock the student row immediately — required for safe PIN counter increment
        # and ensures the PIN reset flush doesn't race with concurrent requests.
        user_result = await db.execute(
            select(users)
            .where(users.firebase_uid == firebase_uid)
            .with_for_update()
        )
        student = user_result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student user not found")

        # Idempotency check — must be scoped to student_id to prevent key reuse
        # by another user returning another user's order record.
        if idempotency_key:
            existing_order_res = await db.execute(
                select(orders).where(
                    orders.idempotency_key == idempotency_key,
                    orders.student_id == student.user_id,
                )
            )
            existing_order = existing_order_res.scalar_one_or_none()
            if existing_order:
                # Rollback to release the FOR UPDATE lock on the student row before
                # returning. Nothing was mutated, so rollback is correct here.
                # Relying on get_db teardown to do this would hold the lock open
                # for the duration of the response serialisation + network flush.
                await db.rollback()
                return PlaceOrderResponse(
                    order_id=existing_order.order_id,
                    qr_token=existing_order.qr_token,
                    timer_expires_at=existing_order.timer_expires_at,
                    total_charged=str(existing_order.item_amount + PLATFORM_FEE),
                )

        now_utc = datetime.now(timezone.utc)

        # 4. PIN Lockout check
        if student.pin_locked_until:
            if now_utc < student.pin_locked_until:
                remaining_seconds = int((student.pin_locked_until - now_utc).total_seconds())
                raise HTTPException(
                    status_code=423,
                    detail=f"PIN locked due to multiple incorrect attempts. Try again in {remaining_seconds // 60 + 1} minutes.",
                )
            # Lock expired — clear it under the row lock we already hold
            student.pin_locked_until = None
            student.failed_pin_attempts = 0

        if not student.transaction_pin_hash:
            raise HTTPException(
                status_code=403,
                detail="Transaction PIN not set. Please set a 4-digit PIN in your profile before placing orders.",
            )

        # 5. Non-blocking bcrypt — offload the slow call so the event loop stays free
        pin_valid = await asyncio.to_thread(
            bcrypt.checkpw, body.pin.encode(), student.transaction_pin_hash.encode()
        )
        if not pin_valid:
            # student row is already locked (with_for_update above) so increment is safe
            student.failed_pin_attempts = (student.failed_pin_attempts or 0) + 1
            if student.failed_pin_attempts >= 5:
                student.pin_locked_until = now_utc + timedelta(minutes=15)
                await db.commit()
                raise HTTPException(
                    status_code=423,
                    detail="Too many incorrect PIN attempts. Your PIN has been locked for 15 minutes.",
                )
            await db.commit()
            remaining = 5 - student.failed_pin_attempts
            raise HTTPException(
                status_code=403,
                detail=f"Incorrect transaction PIN. {remaining} attempt(s) remaining before lock.",
            )

        # PIN is correct — reset counter and flush immediately so a later HTTPException
        # in this same request can't leave a stale increment on the session.
        student.failed_pin_attempts = 0
        student.pin_locked_until = None
        await db.flush()

        # 3. Check rep_id belongs to a Rep or Admin
        rep_result = await db.execute(
            select(users).where(
                users.user_id == body.rep_id,
                users.role.in_([approles.Rep, approles.Admin]),
            )
        )
        rep = rep_result.scalar_one_or_none()
        if not rep:
            raise HTTPException(status_code=404, detail="Department Representative not found")

        # Prevent ordering from oneself
        if student.user_id == rep.user_id:
            raise HTTPException(status_code=400, detail="Cannot place an order against your own account")

        # Server-side price lookup from product catalog (catalog product is strictly required)
        product_res = await db.execute(
            select(ProductsModel).where(
                ProductsModel.product_id == body.product_id,
                ProductsModel.vendor_id == rep.user_id,
            )
        )
        product = product_res.scalar_one_or_none()
        if not product or not product.is_available:
            raise HTTPException(status_code=404, detail="Product not found or unavailable")
        item_amount = product.price
        item_description = product.name

        if item_amount <= 0:
            raise HTTPException(status_code=400, detail="item_amount must be greater than zero")

        total_charge = item_amount + PLATFORM_FEE

        # 8. Deterministic Wallet Locking Order (Sort by user_id to avoid deadlock)
        first_id, second_id = sorted([student.user_id, rep.user_id])

        first_w = (
            await db.execute(
                select(wallets).where(wallets.user_id == first_id).with_for_update()
            )
        ).scalar_one_or_none()

        second_w = (
            await db.execute(
                select(wallets).where(wallets.user_id == second_id).with_for_update()
            )
        ).scalar_one_or_none()

        wallet_map = {}
        if first_w:
            wallet_map[first_id] = first_w
        if second_w:
            wallet_map[second_id] = second_w

        student_wallet = wallet_map.get(student.user_id)
        if not student_wallet:
            raise HTTPException(status_code=404, detail="Student wallet not found")

        # 9. Rep wallet lazy-creation with savepoint to avoid rolling back
        # the entire transaction (which would release row locks already held
        # and leave student/rep ORM objects expired and unusable).
        rep_wallet = wallet_map.get(rep.user_id)
        if not rep_wallet:
            try:
                async with db.begin_nested():
                    rep_wallet = wallets(
                        user_id=rep.user_id,
                        available_balance=Decimal("0.00"),
                        locked_balance=Decimal("0.00"),
                        currency="NGN",
                    )
                    db.add(rep_wallet)
                    await db.flush()
            except IntegrityError:
                # Another concurrent first-order already created the wallet.
                # Savepoint rolls back just the insert; outer locks remain held.
                rep_w_res = await db.execute(
                    select(wallets)
                    .where(wallets.user_id == rep.user_id)
                    .with_for_update()
                )
                rep_wallet = rep_w_res.scalar_one()

        if student_wallet.available_balance < total_charge:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient wallet balance. Required: ₦{total_charge}, "
                    f"Available: ₦{student_wallet.available_balance}"
                ),
            )

        # Execute transfer
        student_balance_before = student_wallet.available_balance
        rep_balance_before = rep_wallet.available_balance

        student_wallet.available_balance -= total_charge
        student_wallet.updated_at = now_utc

        rep_wallet.available_balance += item_amount
        rep_wallet.updated_at = now_utc

        timer_expires = now_utc + timedelta(hours=24)

        new_order = orders(
            idempotency_key=idempotency_key,
            student_id=student.user_id,
            vendor_id=rep.user_id,
            item_description=item_description,
            item_amount=item_amount,
            order_status=orderstat.confirmed,
            is_collected=False,
            qr_token="pending",
            timer_expires_at=timer_expires,
        )

        db.add(new_order)
        await db.flush()

        # 6 & 7. QR Payload with exp claim & dedicated QR secret
        qr_payload = {
            "order_id": new_order.order_id,
            "rep_id": rep.user_id,
            "student_id": student.user_id,
            "exp": int(timer_expires.timestamp()),
        }
        signed_token = jwt.encode(qr_payload, QR_SECRET, algorithm=QR_ALGORITHM)
        new_order.qr_token = signed_token

        # Ledger records
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

        db.add(_write_ledger(
            wallet=rep_wallet,
            user_id=rep.user_id,
            direction="credit",
            amount=item_amount,
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
                "item_amount": str(item_amount),
            },
        )

        return PlaceOrderResponse(
            order_id=new_order.order_id,
            qr_token=signed_token,
            timer_expires_at=timer_expires,
            total_charged=str(total_charge),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("place_order_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{order_id}/scan", status_code=200, dependencies=[Depends(scan_rate_limiter)])
async def scan_order_qr(

    order_id: str,
    body: ScanQRRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Distribution Scan Endpoint:
    - Scanned by Course Rep upon physical item distribution to a student.
    - Validates QR token & exp claim.
    - Marks order as collected (is_collected=True, collected_at=now).
    """
    try:
        # 6 & 7. QR JWT decoding with exp validation & dedicated QR secret
        try:
            token_data = jwt.decode(body.qr_token, QR_SECRET, algorithms=[QR_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="QR token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid QR token")

        token_order_id = token_data.get("order_id")
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

        # 11. Role check simplified directly on DB rep.role
        if rep.role not in (approles.Rep, approles.Admin):
            raise HTTPException(status_code=403, detail="Only Department Representatives can perform distribution scans.")

        # Fetch Order
        order_result = await db.execute(
            select(orders).where(orders.order_id == order_id).with_for_update()
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # 10. Ownership check simplified directly on DB record
        if order.vendor_id != rep.user_id:
            raise HTTPException(status_code=403, detail="This order belongs to a different department representative")

        if order.is_collected:
            raise HTTPException(
                status_code=409,
                detail=f"Item has ALREADY been collected on {order.collected_at.isoformat() if order.collected_at else 'previous scan'}.",
            )

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

    except Exception as e:
        await db.rollback()
        logger.exception("scan_order_qr_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


rep_router = APIRouter(prefix="/api/rep", tags=["orders"])


@rep_router.get("/orders", response_model=list[RepOrderItem])
@router.get("/rep", response_model=list[RepOrderItem])
async def get_rep_orders(
    limit: int = Query(50, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Rep Dashboard Endpoint:
    Returns student orders for the Rep's items, with pagination.
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
            .limit(limit)
            .offset(offset)
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
    limit: int = Query(50, ge=1, le=100, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Student Orders Endpoint: Returns active confirmed orders (uncollected) with QR codes."""
    try:
        firebase_uid = firebase_user.get("uid")
        user_result = await db.execute(
            select(users).where(users.firebase_uid == firebase_uid)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        rep_alias = aliased(users)

        # 12. Filter by is_collected == False & order_status == confirmed
        stmt = (
            select(
                orders.order_id,
                orders.item_description.label("name"),
                orders.item_amount.label("price"),
                orders.qr_token,
                orders.created_at,
                orders.timer_expires_at,
                orders.is_collected,
                rep_alias.user_id.label("rep_id"),
                rep_alias.full_name.label("rep_name"),
            )
            .join(rep_alias, rep_alias.user_id == orders.vendor_id)
            .where(
                orders.student_id == user.user_id,
                orders.is_collected == False,
                orders.order_status == orderstat.confirmed,
            )
            .order_by(orders.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(stmt)
        rows = result.fetchall()

        items = []
        for row in rows:
            created_at_str = row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else ""
            expires_at_str = row.timer_expires_at.isoformat().replace("+00:00", "Z") if row.timer_expires_at else created_at_str

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
                    timer_expire_at=expires_at_str,
                    is_collected=row.is_collected,
                )
            )
        return items

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_pending_transactions_error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
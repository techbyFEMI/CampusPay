import asyncio
import bcrypt
import hashlib
import json
import logging
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import order_rate_limiter, scan_rate_limiter
from app.core.security import get_current_user
from app.models.models import (
    IdempotencyKey,
    approles,
    deliverystat,
    orders,
    paymentstat,
    products,
    users,
)
from app.schemas.orders import (
    PendingTransactionItem,
    PlaceOrderRequest,
    PlaceOrderResponse,
    RepOrderItem,
    ScanQRRequest,
)

from app.repositories.user import UserRepository
from app.repositories.orders import OrderRepository
from app.services.order_service import OrderService
from app.services.errors import (
    AccessDeniedError,
    InvalidQRTokenError,
    InvalidOrderStateError,
    OrderNotFoundError,
    UserNotFoundError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orders", tags=["orders"])
rep_router = APIRouter(prefix="/api/rep", tags=["orders"])
MAX_EXTRA_FEE_KOBO = 5_000
QR_ALGORITHM = "HS256"


def _make_qr_token(order_id: str, rep_id: str, student_id: str) -> str:
    # QR tokens have no expiry; delivery is controlled by payment and ownership state.
    return jwt.encode(
        {"order_id": order_id, "rep_id": rep_id, "student_id": student_id},
        settings.QR_SECRET_KEY,
        algorithm=QR_ALGORITHM,
    )


def _order_response(order: orders) -> PlaceOrderResponse:
    return PlaceOrderResponse(
        order_id=order.order_id,
        qr_token=order.qr_token,
        item_price_kobo=order.item_price_kobo,
        fee_kobo=order.fee_kobo,
        total_charge_kobo=order.item_price_kobo + order.fee_kobo,
        payment_status=order.payment_status.value,
    )


@router.post("", response_model=PlaceOrderResponse, status_code=201, dependencies=[Depends(order_rate_limiter)])
async def place_order(
    body: PlaceOrderRequest,
    request: Request,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    student_id = auth_user["user_id"]
    user_result = await db.execute(
        select(users).where(users.user_id == student_id).with_for_update()
    )
    student = user_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    if student.role != approles.Student:
        raise HTTPException(status_code=403, detail="Only students can place orders")
    if not student.transaction_pin_hash:
        raise HTTPException(status_code=403, detail="Set a transaction PIN before placing orders")
    pin_matches = await asyncio.to_thread(
        bcrypt.checkpw, body.pin.encode(), student.transaction_pin_hash.encode()
    )
    if not pin_matches:
        raise HTTPException(status_code=403, detail="Incorrect transaction PIN")

    product_result = await db.execute(
        select(products).where(
            products.product_id == body.product_id,
            products.rep_id == body.rep_id,
            products.is_available.is_(True),
        )
    )
    product = product_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Available product not found")
    rep_result = await db.execute(
        select(users).where(
            users.user_id == body.rep_id,
            users.role.in_([approles.Rep, approles.Admin]),
        )
    )
    rep = rep_result.scalar_one_or_none()
    if rep is None:
        raise HTTPException(status_code=404, detail="Department representative not found")
    if rep.user_id == student_id:
        raise HTTPException(status_code=400, detail="Cannot order from your own account")

    key = body.idempotency_key or request.headers.get("X-Idempotency-Key")
    payload_hash = hashlib.sha256(
        json.dumps({"rep_id": body.rep_id, "product_id": body.product_id}, sort_keys=True).encode()
    ).hexdigest()
    if key:
        cached_result = await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.caller_user_id == student_id,
                IdempotencyKey.idempotency_key == key,
            )
        )
        cached = cached_result.scalar_one_or_none()
        if cached:
            if cached.payload_hash != payload_hash:
                raise HTTPException(status_code=409, detail="Idempotency key was used for another request")
            return PlaceOrderResponse.model_validate(cached.response_body)

    fee_kobo = MAX_EXTRA_FEE_KOBO
    order = orders(
        student_id=student_id,
        rep_id=rep.user_id,
        product_id=product.product_id,
        item_description=product.name,
        item_price_kobo=product.price_kobo,
        fee_kobo=fee_kobo,
        # Shares are calculated from confirmed Paystack costs on transfer approval.
        rep_share_kobo=0,
        campuspay_share_kobo=0,
        provider_cost_kobo=0,
        payment_status=paymentstat.pending,
        delivery_status=deliverystat.awaiting_delivery,
        qr_token="pending",
    )
    db.add(order)
    await db.flush()
    order.qr_token = _make_qr_token(order.order_id, rep.user_id, student_id)
    response = _order_response(order)
    if key:
        db.add(
            IdempotencyKey(
                caller_user_id=student_id,
                idempotency_key=key,
                payload_hash=payload_hash,
                response_body=response.model_dump(),
                response_status=201,
            )
        )
    await db.commit()
    return response


@router.post("/{order_id}/scan", status_code=200, dependencies=[Depends(scan_rate_limiter)])
async def scan_order_qr(
    order_id: str,
    body: ScanQRRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrderService(db, OrderRepository(db), UserRepository(db))
    try:
        return await service.confirm_delivery(
            order_id=order_id,
            qr_token=body.qr_token,
            rep_id=auth_user["user_id"],
        )
    except InvalidQRTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Order not found") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidOrderStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@rep_router.get("/orders", response_model=list[RepOrderItem])
@router.get("/rep", response_model=list[RepOrderItem])
async def get_rep_orders(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrderService(db, OrderRepository(db), UserRepository(db))
    try:
        return await service.list_rep_orders(
            rep_id=auth_user["user_id"],
            limit=limit,
            offset=offset,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/pending", response_model=list[PendingTransactionItem])
async def get_pending_transactions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = OrderService(
        session=db,
        order_repository=OrderRepository(db),
        user_repository=UserRepository(db),
    )
    try:
        return await service.list_pending_delivery(
            student_id=auth_user["user_id"],
            offset=offset,
            limit=limit,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

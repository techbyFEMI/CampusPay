from datetime import datetime, timezone

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import approles, deliverystat, paymentstat
from app.repositories.orders import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.orders import PendingTransactionItem, RepOrderItem
from app.services.errors import (
    AccessDeniedError,
    InvalidOrderStateError,
    InvalidQRTokenError,
    OrderNotFoundError,
    UserNotFoundError,
)


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        order_repository: OrderRepository,
        user_repository: UserRepository,
    ):
        self.session = session
        self.order_repository = order_repository
        self.user_repository = user_repository

    async def list_pending_delivery(
        self,
        student_id: str,
        offset: int = 0,
        limit: int = 10,
    ) -> list[PendingTransactionItem]:
        student = await self.user_repository.get_user_by_id(student_id)
        if student is None:
            raise UserNotFoundError(f"User with ID {student_id} not found.")

        rows = await self.order_repository.list_pending_delivery(
            student_id=student_id,
            offset=offset,
            limit=limit,
        )
        return [
            PendingTransactionItem(
                order_id=order.order_id,
                name=order.item_description,
                item_price_kobo=order.item_price_kobo,
                fee_kobo=order.fee_kobo,
                qr_token=order.qr_token,
                payment_status=order.payment_status.value,
                delivery_status=order.delivery_status.value,
                rep_id=order.rep_id,
                rep_name=rep_name,
                created_at=order.created_at.isoformat(),
            )
            for order, rep_name in rows
        ]

    async def list_rep_orders(
        self,
        rep_id: str,
        offset: int = 0,
        limit: int = 10,
    ) -> list[RepOrderItem]:
        rep = await self.user_repository.get_user_by_id(rep_id)
        if rep is None:
            raise UserNotFoundError(f"User with ID {rep_id} not found.")
        if rep.role not in (approles.Rep, approles.Admin):
            raise AccessDeniedError("Representative access required")

        rows = await self.order_repository.list_rep_orders(
            rep_id=rep_id,
            offset=offset,
            limit=limit,
        )
        return [
            RepOrderItem(
                order_id=order.order_id,
                item_description=order.item_description,
                item_price_kobo=order.item_price_kobo,
                student_name=student_name,
                student_matric=student_matric,
                created_at=order.created_at.isoformat(),
                payment_status=order.payment_status.value,
                delivery_status=order.delivery_status.value,
                delivered_at=(
                    order.delivered_at.isoformat() if order.delivered_at else None
                ),
            )
            for order, student_name, student_matric in rows
        ]

    async def confirm_delivery(
        self, order_id: str, qr_token: str, rep_id: str
    ) -> dict:
        try:
            token_data = jwt.decode(
                qr_token,
                settings.QR_SECRET_KEY,
                algorithms=["HS256"],
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidQRTokenError("Invalid QR token") from exc

        if token_data.get("order_id") != order_id:
            raise InvalidQRTokenError("QR token does not match this order")
        if token_data.get("rep_id") != rep_id:
            raise AccessDeniedError("This QR code is only valid for its representative")

        order = await self.order_repository.get_order_for_update(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found.")
        if order.rep_id != rep_id:
            raise AccessDeniedError("This order belongs to another representative")
        if token_data.get("student_id") != order.student_id:
            raise InvalidQRTokenError("QR token does not match this order")
        if order.payment_status != paymentstat.approved:
            raise InvalidOrderStateError("Payment has not been approved")
        if order.delivery_status == deliverystat.delivered:
            raise InvalidOrderStateError("This order has already been delivered")

        order.delivery_status = deliverystat.delivered
        order.delivered_at = datetime.now(timezone.utc)
        await self.session.commit()

        student = await self.user_repository.get_user_by_id(order.student_id)
        return {
            "message": "Delivery confirmed",
            "order_id": order.order_id,
            "student_name": student.full_name if student else "Student",
            "student_matric": student.matric_number if student else None,
            "item_description": order.item_description,
            "delivery_status": order.delivery_status.value,
            "delivered_at": order.delivered_at.isoformat(),
        }
from datetime import datetime, timezone

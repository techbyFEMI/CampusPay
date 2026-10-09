from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.enums import deliverystat
from app.models.identity import users
from app.models.orders import orders


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_pending_delivery(
        self,
        student_id: str,
        offset: int = 0,
        limit: int = 10,
    ):
        rep = aliased(users)
        statement = (
            select(orders, rep.full_name)
            .join(rep, rep.user_id == orders.rep_id)
            .where(
                orders.student_id == student_id,
                orders.delivery_status == deliverystat.awaiting_delivery,
            )
            .order_by(orders.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return result.all()

    async def list_rep_orders(
        self,
        rep_id: str,
        offset: int = 0,
        limit: int = 10,
    ):
        student = aliased(users)
        statement = (
            select(orders, student.full_name, student.matric_number)
            .join(student, student.user_id == orders.student_id)
            .where(orders.rep_id == rep_id)
            .order_by(orders.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return result.all()

    async def get_order_for_update(self, order_id: str):
        result = await self.session.execute(
            select(orders)
            .where(orders.order_id == order_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

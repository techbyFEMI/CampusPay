from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import products
from app.models.enums import approles
from app.models.identity import users


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_reps(self, is_open: bool | None = None):
        statement = select(users).where(
            users.role.in_((approles.Rep, approles.Admin))
        )
        if is_open is not None:
            statement = statement.where(users.rep_is_open == is_open)
        statement = statement.order_by(
            users.rep_is_open.desc(), users.full_name.asc()
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_rep(self, rep_id: str):
        result = await self.session.execute(
            select(users).where(
                users.user_id == rep_id,
                users.role.in_((approles.Rep, approles.Admin)),
            )
        )
        return result.scalar_one_or_none()

    async def list_rep_products(
        self, rep_id: str, available_only: bool = False
    ):
        statement = select(products).where(products.rep_id == rep_id)
        if available_only:
            statement = statement.where(products.is_available.is_(True))
        statement = statement.order_by(
            products.is_available.desc(), products.created_at.desc()
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_product_by_id(self, product_id: str):
        result = await self.session.execute(
            select(products).where(products.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def add_product(self, product: products):
        self.session.add(product)
        await self.session.flush()
        return product

    async def delete_product(self, product: products) -> None:
        await self.session.delete(product)

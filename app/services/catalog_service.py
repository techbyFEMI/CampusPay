from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import products
from app.models.enums import approles
from app.repositories.catalog import CatalogRepository
from app.repositories.user import UserRepository
from app.schemas.catalog import (
    ProductCreateRequest,
    ProductItem,
    ProductResponse,
    ProductUpdateRequest,
    RepDetail,
    RepSummary,
)
from app.services.errors import (
    AccessDeniedError,
    ProductNotFoundError,
    ProductOwnershipError,
    UserNotFoundError,
)


class CatalogService:
    def __init__(
        self,
        session: AsyncSession,
        catalog_repository: CatalogRepository,
        user_repository: UserRepository,
    ):
        self.session = session
        self.catalog_repository = catalog_repository
        self.user_repository = user_repository

    async def list_reps(self, is_open: bool | None = None) -> list[RepSummary]:
        reps = await self.catalog_repository.list_reps(is_open=is_open)
        return [
            RepSummary(
                rep_id=rep.user_id,
                name=rep.full_name,
                location=rep.rep_location,
                phone=rep.phone,
                is_open=rep.rep_is_open,
                cover_image_url=rep.rep_cover_image_url,
            )
            for rep in reps
        ]

    async def get_rep(
        self, rep_id: str, available_only: bool = False
    ) -> RepDetail:
        rep = await self.catalog_repository.get_rep(rep_id)
        if rep is None:
            raise UserNotFoundError(f"Representative {rep_id} not found")

        rep_products = await self.catalog_repository.list_rep_products(
            rep_id, available_only=available_only
        )
        return RepDetail(
            rep_id=rep.user_id,
            name=rep.full_name,
            location=rep.rep_location,
            phone=rep.phone,
            is_open=rep.rep_is_open,
            cover_image_url=rep.rep_cover_image_url,
            products=[
                ProductItem(
                    product_id=product.product_id,
                    name=product.name,
                    description=product.description,
                    price_kobo=product.price_kobo,
                    is_available=product.is_available,
                    image_url=product.image_url,
                )
                for product in rep_products
            ],
        )

    async def create_product(
        self, user_id: str, body: ProductCreateRequest
    ) -> ProductResponse:
        rep = await self._get_rep_account(user_id)
        product = products(
            rep_id=rep.user_id,
            name=body.name,
            description=body.description,
            price_kobo=body.price_kobo,
            image_url=body.image_url,
            is_available=True,
        )
        await self.catalog_repository.add_product(product)
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def update_product(
        self, user_id: str, product_id: str, body: ProductUpdateRequest
    ) -> ProductResponse:
        rep = await self._get_rep_account(user_id)
        product = await self.catalog_repository.get_product_by_id(product_id)
        if product is None:
            raise ProductNotFoundError("Product not found")
        if product.rep_id != rep.user_id:
            raise ProductOwnershipError("You do not own this product")

        changes = body.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if value is not None:
                setattr(product, field, value)

        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def delete_product(self, user_id: str, product_id: str) -> None:
        rep = await self._get_rep_account(user_id)
        product = await self.catalog_repository.get_product_by_id(product_id)
        if product is None:
            raise ProductNotFoundError("Product not found")
        if product.rep_id != rep.user_id:
            raise ProductOwnershipError("You do not own this product")

        await self.catalog_repository.delete_product(product)
        await self.session.commit()

    async def _get_rep_account(self, user_id: str):
        user = await self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found")
        if user.role not in (approles.Rep, approles.Admin):
            raise AccessDeniedError("Representative or Admin access required")
        return user

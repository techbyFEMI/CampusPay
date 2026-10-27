from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.catalog import CatalogRepository
from app.repositories.user import UserRepository
from app.schemas.catalog import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
    RepDetail,
    RepSummary,
)
from app.services.catalog_service import CatalogService
from app.services.errors import (
    AccessDeniedError,
    ProductNotFoundError,
    ProductOwnershipError,
    UserNotFoundError,
)


router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _catalog_service(db: AsyncSession) -> CatalogService:
    return CatalogService(
        session=db,
        catalog_repository=CatalogRepository(db),
        user_repository=UserRepository(db),
    )


def _raise_catalog_error(error: Exception) -> None:
    if isinstance(error, (ProductNotFoundError, UserNotFoundError)):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, (AccessDeniedError, ProductOwnershipError)):
        raise HTTPException(status_code=403, detail=str(error)) from error
    raise error


@router.get("/reps", response_model=list[RepSummary])
async def list_reps(
    db: AsyncSession = Depends(get_db),
) -> list[RepSummary]:
    return await _catalog_service(db).list_reps()


@router.get("/reps/{rep_id}", response_model=RepDetail)
async def get_rep(
    rep_id: Annotated[
        str, Path(description="UUID of the representative (user_id from the user table)")
    ],
    available_only: Annotated[
        bool,
        Query(description="When true, only return currently available products."),
    ] = False,
    db: AsyncSession = Depends(get_db),
) -> RepDetail:
    try:
        return await _catalog_service(db).get_rep(
            rep_id=rep_id,
            available_only=available_only,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    body: ProductCreateRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    try:
        return await _catalog_service(db).create_product(auth_user["user_id"], body)
    except (UserNotFoundError, AccessDeniedError) as exc:
        _raise_catalog_error(exc)


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: Annotated[str, Path(description="UUID of the product")],
    body: ProductUpdateRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    try:
        return await _catalog_service(db).update_product(
            user_id=auth_user["user_id"],
            product_id=product_id,
            body=body,
        )
    except (UserNotFoundError, AccessDeniedError, ProductNotFoundError, ProductOwnershipError) as exc:
        _raise_catalog_error(exc)


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: Annotated[str, Path(description="UUID of the product")],
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        await _catalog_service(db).delete_product(
            user_id=auth_user["user_id"], product_id=product_id
        )
        return {"message": "Product deleted"}
    except (UserNotFoundError, AccessDeniedError, ProductNotFoundError, ProductOwnershipError) as exc:
        _raise_catalog_error(exc)

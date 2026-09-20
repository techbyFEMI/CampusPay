import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_firebase_user
from app.models.models import approles, products, users
from app.schemas.catalog import (
    ProductCreateRequest,
    ProductItem,
    ProductResponse,
    ProductUpdateRequest,
    VendorDetail,
    VendorSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get(
    "/vendors",
    response_model=list[VendorSummary],
    summary="List all vendors",
    description=(
        "Returns every user with role=vendor. "
        "Optionally filter by `is_open` to show only currently open stores. "
        "Results are ordered: open vendors first, then alphabetically by name."
    ),
)
async def list_vendors(
    is_open: Annotated[
        bool | None,
        Query(description="Filter by open/closed status. Omit for all vendors."),
    ] = None,
    db: AsyncSession = Depends(get_db),
) -> list[VendorSummary]:
   
    try:
        stmt = select(users).where(users.role.in_([approles.Rep, approles.Admin]))

        if is_open is not None:
            stmt = stmt.where(users.vendor_is_open == is_open)

        stmt = stmt.order_by(users.vendor_is_open.desc(), users.full_name.asc())

        result = await db.execute(stmt)
        vendor_rows = result.scalars().all()

        return [
            VendorSummary(
                vendor_id=v.user_id,
                name=v.full_name,
                location=v.vendor_location,
                phone=v.phone,
                is_open=v.vendor_is_open,
                cover_image_url=v.vendor_cover_image_url,
            )
            for v in vendor_rows
        ]

    except HTTPException:
        raise  
    except Exception:
        logger.exception("Unexpected error in list_vendors")
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch vendor list. Please try again later.",
        )



@router.get(
    "/vendors/{vendor_id}",
    response_model=VendorDetail,
    summary="Get vendor details + products",
    description=(
        "Returns the full profile of a single vendor along with their product "
        "catalogue. Pass `available_only=true` to restrict products to those "
        "currently in stock."
    ),
)
async def get_vendor(
    vendor_id: Annotated[
        str,
        Path(description="UUID of the vendor (user_id from the users table)"),
    ],
    available_only: Annotated[
        bool,
        Query(description="When true, only return products where is_available=true."),
    ] = False,
    db: AsyncSession = Depends(get_db),
) -> VendorDetail:
    
    try:
        
        vendor_result = await db.execute(
            select(users).where(
                users.user_id == vendor_id,
                users.role.in_([approles.Rep, approles.Admin]), 
            )
        )
        vendor = vendor_result.scalar_one_or_none()

        if vendor is None:
            raise HTTPException(
                status_code=404,
                detail=f"Vendor '{vendor_id}' not found.",
            )

        product_stmt = select(products).where(products.vendor_id == vendor_id)

        if available_only:
            product_stmt = product_stmt.where(products.is_available == True)  

        
        product_stmt = product_stmt.order_by(
            products.is_available.desc(),
            products.created_at.desc(),
        )

        product_result = await db.execute(product_stmt)
        product_rows = product_result.scalars().all()

        return VendorDetail(
            vendor_id=vendor.user_id,
            name=vendor.full_name,
            location=vendor.vendor_location,
            phone=vendor.phone,
            is_open=vendor.vendor_is_open,
            cover_image_url=vendor.vendor_cover_image_url,
            products=[
                ProductItem(
                    product_id=p.product_id,
                    name=p.name,
                    description=p.description,
                    price=p.price,
                    is_available=p.is_available,
                    image_url=p.image_url,
                )
                for p in product_rows
            ],
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in get_vendor vendor_id=%s", vendor_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch vendor details. Please try again later.",
        )


async def _resolve_vendor(firebase_user: dict, db: AsyncSession) -> users:
    """Resolve Firebase token → DB user, enforce Vendor role."""
    firebase_uid = firebase_user.get("uid")
    result = await db.execute(select(users).where(users.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role not in (approles.Rep, approles.Admin):
        raise HTTPException(status_code=403, detail="Representative or Admin access required")
    return user


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=201,
    summary="Create a new product",
)
async def create_product(
    body: ProductCreateRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    try:
        vendor = await _resolve_vendor(firebase_user, db)

        new_product = products(
            vendor_id=vendor.user_id,
            name=body.name,
            description=body.description,
            price=body.price,
            image_url=body.image_url,
            is_available=True,
        )
        db.add(new_product)
        await db.commit()
        await db.refresh(new_product)
        return ProductResponse.model_validate(new_product)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in create_product")
        raise HTTPException(status_code=500, detail="Unable to create product.")


@router.put(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Update a product (partial)",
)
async def update_product(
    product_id: Annotated[str, Path(description="UUID of the product")],
    body: ProductUpdateRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    try:
        vendor = await _resolve_vendor(firebase_user, db)

        result = await db.execute(
            select(products).where(products.product_id == product_id)
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product.vendor_id != vendor.user_id:
            raise HTTPException(
                status_code=403, detail="You do not own this product"
            )

        if body.name is not None:
            product.name = body.name
        if body.description is not None:
            product.description = body.description
        if body.price is not None:
            product.price = body.price
        if body.image_url is not None:
            product.image_url = body.image_url
        if body.is_available is not None:
            product.is_available = body.is_available

        await db.commit()
        await db.refresh(product)
        return ProductResponse.model_validate(product)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in update_product product_id=%s", product_id)
        raise HTTPException(status_code=500, detail="Unable to update product.")


@router.delete(
    "/products/{product_id}",
    summary="Delete a product",
)
async def delete_product(
    product_id: Annotated[str, Path(description="UUID of the product")],
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        vendor = await _resolve_vendor(firebase_user, db)

        result = await db.execute(
            select(products).where(products.product_id == product_id)
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product.vendor_id != vendor.user_id:
            raise HTTPException(
                status_code=403, detail="You do not own this product"
            )

        await db.delete(product)
        await db.commit()
        return {"message": "Product deleted"}

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in delete_product product_id=%s", product_id)
        raise HTTPException(status_code=500, detail="Unable to delete product.")

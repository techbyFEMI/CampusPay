

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from sqlalchemy import select, text

from app.api import auth, catalog, webhooks, wallet, profile, orders
from app.core.database import Base, engine, sessionLocal, get_db
from app.models.models import orders as Orders, wallets, orderstat
from app.models import models
from app.services.nomba import transfer_to_bank
from app.services.reconciliation import run_reconciliation

logger = logging.getLogger(__name__)


_started_at: datetime = datetime.now(timezone.utc)


_expiry_in_progress: set[str] = set()



async def expiry_job():
    while True:
        await asyncio.sleep(300)
        try:
            async with sessionLocal() as db:
                result = await db.execute(
                    select(Orders).where(
                        Orders.order_status == orderstat.pending,

                        Orders.timer_expires_at <= datetime.now(timezone.utc),
                    )
                )
                expired_orders = result.scalars().all()
                if not expired_orders:
                    continue

                logger.info("expiry_job_processing count=%d", len(expired_orders))

                for order in expired_orders:

                    if order.order_id in _expiry_in_progress:
                        logger.debug("expiry_job_skip_in_progress order_id=%s", order.order_id)
                        continue
                    _expiry_in_progress.add(order.order_id)

                    try:
                        await _expire_single_order(db, order)
                    finally:
                        _expiry_in_progress.discard(order.order_id)

        except Exception:
            logger.exception("expiry_job_unhandled_error")


async def _expire_single_order(db, order) -> None:
    
    wallet_result = await db.execute(
        select(wallets).where(wallets.user_id == order.student_id)
    )
    wallet = wallet_result.scalar_one_or_none()
    if wallet is None:
        logger.error(
            "expiry_wallet_missing student_id=%s order_id=%s",
            order.student_id, order.order_id,
        )
        return

    vendor_result = await db.execute(
        select(models.users).where(models.users.user_id == order.vendor_id)
    )
    vendor = vendor_result.scalar_one_or_none()

  
    wallet.locked_balance -= order.escrow_hold
    wallet.available_balance += order.item_amount
    wallet.updated_at = datetime.now(timezone.utc)
    order.order_status = orderstat.expired
    order.penalty_status = "pending"

    try:
        await db.commit()
        logger.info(
            "expiry_refund_committed order_id=%s student_id=%s amount=%s",
            order.order_id, order.student_id, order.item_amount,
        )
    except Exception:
        await db.rollback()
        logger.exception(
            "expiry_db_commit_failed order_id=%s — skipping penalty payout this cycle",
            order.order_id,
        )
        return

 
    if not vendor or not vendor.vendor_bank_account or not vendor.vendor_bank_code:
        logger.error(
            "[ACTION REQUIRED] expiry_no_vendor_bank vendor_id=%s order_id=%s — ₦20 penalty cannot be paid",
            order.vendor_id, order.order_id,
        )
        return

    penalty_ref = None
    try:
        nomba_result = await transfer_to_bank(
            amount=Decimal("20.00"),
            account_name=vendor.full_name,
            account_number=vendor.vendor_bank_account,
            bank_code=str(vendor.vendor_bank_code),
            sender_name="CampusPay",
            narration=f"No-show penalty — order {order.order_id[:8]}",
            merchantTxRef=f"penalty-{order.order_id}",
        )
        if nomba_result.get("code") == "00":
            penalty_ref = nomba_result.get("data", {}).get("transferRef") or f"penalty-{order.order_id}"
            logger.info(
                "expiry_penalty_paid order_id=%s ref=%s", order.order_id, penalty_ref,
            )
        else:
            logger.error(
                "[ACTION REQUIRED] expiry_penalty_failed order_id=%s response=%s",
                order.order_id, nomba_result,
            )
    except Exception as e:
        logger.error(
            "[ACTION REQUIRED] expiry_penalty_exception order_id=%s error=%s",
            order.order_id, e,
        )

    if penalty_ref:
        try:
            order.penalty_status = "paid"
            order.penalty_transfer_ref = penalty_ref
            await db.commit()
        except Exception as e:
            logger.error(
                "expiry_save_penalty_ref_failed order_id=%s error=%s", order.order_id, e,
            )



@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    task = asyncio.create_task(expiry_job())

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass



app = FastAPI(
    title="CampusPay DVA Infrastructure",
    version="1.3.0",
    lifespan=lifespan,
)

origins = [
    "https://campuspay-web.vercel.app",
    "https://campuspay-3f39.onrender.com",
    "https://campuspay-eta.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(wallet.router, prefix="/api", tags=["wallet"])
app.include_router(profile.router)
app.include_router(orders.router)
app.include_router(catalog.router)




@app.get("/health")
async def health(db=Depends(get_db)):

    db_status = "unknown"
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = "error"
        db_error = str(e)
        logger.error("health_check_db_error: %s", e)

    uptime_seconds = int((datetime.now(timezone.utc) - _started_at).total_seconds())

    return {
        "status": "live" if db_status == "ok" else "degraded",
        "service": "CampusPay Backend",
        "version": "1.3.0",
        "environment": "production",
        "uptime_seconds": uptime_seconds,
        "database": db_status,
        **({"database_error": db_error} if db_error else {}),
    }


@app.get("/api/admin/reconciliation")
async def reconciliation_report(
    lookback_hours: int = 48,
    db=Depends(get_db),
):
   
    from app.core.security import get_current_firebase_user
    try:
        report = await run_reconciliation(db, lookback_hours=lookback_hours)
        return {
            "run_at": report.run_at,
            "orders_checked": report.orders_checked,
            "critical_count": report.critical_count,
            "warning_count": report.warning_count,
            "issues": [
                {
                    "order_id": i.order_id,
                    "issue": i.issue,
                    "severity": i.severity,
                    "amount": i.amount,
                    "vendor_id": i.vendor_id,
                    "nomba_transfer_ref": i.nomba_transfer_ref,
                }
                for i in report.issues
            ],
        }
    except Exception as e:
        logger.exception("reconciliation_endpoint_error: %s", e)
        
        raise HTTPException(status_code=500, detail="Reconciliation failed")
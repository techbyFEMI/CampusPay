import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, catalog, webhooks, wallet, profile, orders
from app.core.database import Base, engine, get_db
from app.services.reconciliation import run_reconciliation

logger = logging.getLogger(__name__)

_started_at: datetime = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="CampusPay Course-Rep Pilot Infrastructure",
    version="2.0.0",
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
app.include_router(orders.rep_router)
app.include_router(catalog.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


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
        "version": "2.0.0",
        "environment": "production",
        "uptime_seconds": uptime_seconds,
        "database": db_status,
        **({"database_error": "Database connection error"} if db_error else {}),
    }



@app.get("/api/admin/reconciliation")
async def reconciliation_report(
    lookback_hours: int = 48,
    db=Depends(get_db),
):
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
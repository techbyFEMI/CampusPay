import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, catalog, webhooks, wallet, profile, orders
from app.core.database import get_db

logger = logging.getLogger(__name__)

_started_at: datetime = datetime.now(timezone.utc)


app = FastAPI(
    title="CampusPay Course-Rep Pilot Infrastructure",
    version="2.0.0",
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

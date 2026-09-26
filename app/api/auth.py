from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_firebase_user
from app.core.rate_limiter import login_rate_limiter, claim_rate_limiter, lookup_rate_limiter
from app.models.models import users, approles
from app.services.user_service import get_or_create_user
from app.services import roster_auth_service
from app.schemas.auth import (
    AuthSyncRequest,
    RepBootstrapRequest,
    LookupMatricRequest,
    ClaimAccountRequest,
    LoginMatricRequest,
    RosterUploadRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _verify_bootstrap_secret(x_admin_secret: str | None = Header(default=None)) -> None:
    """Dependency: verify ADMIN_BOOTSTRAP_SECRET header for privileged bootstrap endpoints."""
    configured = settings.ADMIN_BOOTSTRAP_SECRET
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap endpoint is disabled: ADMIN_BOOTSTRAP_SECRET is not configured.",
        )
    if not x_admin_secret or not secrets.compare_digest(x_admin_secret, configured):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing X-Admin-Secret header.",
        )


@router.get("/departments")
async def list_departments(
    request: Request,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    try:
        dept_data, etag = await roster_auth_service.get_all_departments_with_etag(db)
        quoted_etag = f'"{etag}"'

        # Check client's cached ETag (If-None-Match header)
        if if_none_match and if_none_match.strip() in (etag, quoted_etag):
            response.status_code = 304
            return Response(status_code=304)

        response.headers["ETag"] = quoted_etag
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        return dept_data
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_departments_failed")
        raise HTTPException(status_code=500, detail="Failed to fetch departments")


@router.post("/bootstrap-rep", dependencies=[Depends(_verify_bootstrap_secret)])
async def bootstrap_rep_account(
    payload: RepBootstrapRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a Rep account. Requires a valid X-Admin-Secret header. Server-only operation."""
    try:
        result = await roster_auth_service.bootstrap_rep(
            db=db,
            matric_number=payload.matric_number,
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            department_name=payload.department_name,
            department_code=payload.department_code,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("bootstrap_rep_failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/upload-roster")
async def upload_roster(
    payload: RosterUploadRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a department roster. Requires the authenticated user to be a Rep or Admin IN THE DATABASE.
    Role is always verified against the database row — never trusted from the JWT claim.
    """
    firebase_uid = firebase_user.get("uid")
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

    # Always resolve role from DB — never trust the JWT payload's role claim
    user_result = await db.execute(
        select(users).where(users.firebase_uid == firebase_uid)
    )
    db_user = user_result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")
    if db_user.role not in (approles.Rep, approles.Admin):
        raise HTTPException(
            status_code=403,
            detail="Only department representatives or admins can upload rosters.",
        )

    try:
        roster_list = [row.model_dump() for row in payload.roster]
        result = await roster_auth_service.upload_department_roster(
            db=db,
            department_code=payload.department_code,
            roster_data=roster_list,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("upload_roster_failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/lookup-matric", dependencies=[Depends(lookup_rate_limiter)])
async def lookup_matric(
    payload: LookupMatricRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await roster_auth_service.lookup_matric_number(
            db=db,
            matric_number=payload.matric_number,
            department_code=payload.department_code,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("lookup_matric_failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/claim", dependencies=[Depends(claim_rate_limiter)])
async def claim_account(
    payload: ClaimAccountRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await roster_auth_service.claim_student_account(
            db=db,
            matric_number=payload.matric_number,
            department_code=payload.department_code,
            email=payload.email,
            password=payload.password,
            phone=payload.phone,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("claim_account_failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/login-matric", dependencies=[Depends(login_rate_limiter)])
async def login_matric(
    payload: LoginMatricRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await roster_auth_service.login_user(
            db=db,
            matric_number=payload.matric_number,
            password=payload.password,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("login_matric_failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sync")
async def sync_user(
    payload: AuthSyncRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync a user after authentication.
    - For NEW users: role defaults to 'Student' unconditionally — client cannot self-assign Rep/Admin.
    - For EXISTING users: role is never changed via this endpoint; the DB value is authoritative.
    """
    try:
        result = await get_or_create_user(
            db=db,
            firebase_uid=firebase_user["uid"],
            email=firebase_user.get("email") or f"{firebase_user['uid']}@campuspay.internal",
            full_name=payload.full_name or firebase_user.get("name") or "New User",
            # Hard-code "Student" for new registrations; existing users keep their DB role
            role_str="Student",
            phone=payload.phone,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("sync_user_failed")
        raise HTTPException(status_code=500, detail="Internal server error")

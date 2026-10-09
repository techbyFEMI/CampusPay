import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import claim_rate_limiter, login_rate_limiter, lookup_rate_limiter
from app.core.security import get_current_user
from app.repositories.auth import AuthRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AuthSyncRequest,
    ClaimAccountRequest,
    LookupMatricRequest,
    LoginMatricRequest,
    LoginRequest,
    RefreshSessionRequest,
    RegisterRequest,
    RepBootstrapRequest,
    RosterUploadRequest,
)
from app.services.auth_service import AuthService, SupabaseSessionService
from app.services.errors import AccessDeniedError, UserNotFoundError
from app.services.supabase_auth import SupabaseAuthError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer()


def _auth_service(db: AsyncSession) -> AuthService:
    return AuthService(
        session=db,
        auth_repository=AuthRepository(db),
        user_repository=UserRepository(db),
    )


def _verify_bootstrap_secret(x_admin_secret: str | None = Header(default=None)) -> None:
    configured = settings.ADMIN_BOOTSTRAP_SECRET
    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap endpoint is disabled: ADMIN_BOOTSTRAP_SECRET is not configured.",
        )
    if not x_admin_secret or not secrets.compare_digest(x_admin_secret, configured):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Admin-Secret header.")


@router.get("/departments")
async def list_departments(
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    try:
        department_data, etag = await _auth_service(db).list_departments()
    except Exception as exc:
        logger.exception("list_departments_failed")
        raise HTTPException(status_code=500, detail="Failed to fetch departments") from exc

    quoted_etag = f'"{etag}"'
    if if_none_match and if_none_match.strip() in (etag, quoted_etag):
        return Response(status_code=304)
    response.headers["ETag"] = quoted_etag
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
    return department_data


@router.post("/bootstrap-rep", dependencies=[Depends(_verify_bootstrap_secret)])
async def bootstrap_rep_account(
    payload: RepBootstrapRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _auth_service(db).bootstrap_rep(
            matric_number=payload.matric_number,
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            department_name=payload.department_name,
            department_code=payload.department_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=502, detail="Could not provision Supabase account") from exc
    except Exception as exc:
        logger.exception("bootstrap_rep_failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/upload-roster")
async def upload_roster(
    payload: RosterUploadRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _auth_service(db).upload_department_roster(
            user_id=auth_user["user_id"],
            department_code=payload.department_code,
            roster_data=[row.model_dump() for row in payload.roster],
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lookup-matric", dependencies=[Depends(lookup_rate_limiter)])
async def lookup_matric(
    payload: LookupMatricRequest,
    db: AsyncSession = Depends(get_db),
):
    # Kept separate from login input below; this endpoint accepts matric + department.
    try:
        return await _auth_service(db).lookup_matric_number(
            matric_number=payload.matric_number,
            department_code=payload.department_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claim", dependencies=[Depends(claim_rate_limiter)])
async def claim_account(
    payload: ClaimAccountRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _auth_service(db).claim_student_account(
            matric_number=payload.matric_number,
            department_code=payload.department_code,
            email=payload.email,
            password=payload.password,
            phone=payload.phone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=502, detail="Could not provision Supabase account") from exc


@router.post("/login-matric", dependencies=[Depends(login_rate_limiter)])
async def login_matric(
    payload: LoginMatricRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _auth_service(db).login_matric(
            matric_number=payload.matric_number,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid matriculation number or password") from exc


@router.post("/sync")
async def sync_user(
    payload: AuthSyncRequest,
    auth_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_metadata = auth_user.get("user_metadata", {})
    try:
        return await _auth_service(db).sync_user(
            auth_user_id=auth_user["user_id"],
            email=auth_user.get("email") or f"{auth_user['user_id']}@campuspay.internal",
            full_name=payload.full_name or user_metadata.get("full_name") or "New User",
            phone=payload.phone,
        )
    except Exception as exc:
        logger.exception("sync_user_failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/login")
async def login(payload: LoginRequest):
    try:
        return await SupabaseSessionService().login(
            email=payload.email, password=payload.password
        )
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc


@router.post("/register", status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await _auth_service(db).register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("register_user_failed")
        raise HTTPException(status_code=500, detail="Could not create account") from exc


@router.post("/refresh")
async def refresh(payload: RefreshSessionRequest):
    try:
        return await SupabaseSessionService().refresh(payload.refresh_token)
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout", status_code=204)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        await SupabaseSessionService().logout(credentials.credentials)
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

"""Small GoTrue client for server-side Supabase Auth provisioning and sessions."""

import httpx

from app.core.config import settings


class SupabaseAuthError(RuntimeError):
    pass


def _url(path: str) -> str:
    if not settings.SUPABASE_URL:
        raise SupabaseAuthError("SUPABASE_URL is not configured")
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/{path.lstrip('/')}"


def _admin_headers() -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not key:
        raise SupabaseAuthError("SUPABASE_SERVICE_ROLE_KEY is not configured")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _public_headers() -> dict[str, str]:
    key = settings.SUPABASE_ANON_KEY
    if not key:
        raise SupabaseAuthError("SUPABASE_ANON_KEY is not configured")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


async def create_auth_user(
    *, email: str, password: str, metadata: dict | None = None
) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            _url("admin/users"),
            headers={**_admin_headers(), "Content-Type": "application/json"},
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": metadata or {},
            },
        )
    if response.is_error:
        detail = response.json().get("msg") or response.json().get("message") or "Auth user creation failed"
        raise SupabaseAuthError(detail)
    return response.json()["id"]


async def delete_auth_user(user_id: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.delete(
            _url(f"admin/users/{user_id}"), headers=_admin_headers()
        )
    if response.is_error:
        raise SupabaseAuthError("Could not roll back Supabase Auth user creation")


async def sign_in(*, email: str, password: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            _url("token?grant_type=password"),
            headers={**_public_headers(), "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
    if response.is_error:
        raise SupabaseAuthError("Invalid email or password")
    return response.json()


async def refresh_session(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            _url("token?grant_type=refresh_token"),
            headers={**_public_headers(), "Content-Type": "application/json"},
            json={"refresh_token": refresh_token},
        )
    if response.is_error:
        raise SupabaseAuthError("Session has expired; please sign in again")
    return response.json()


async def sign_out(access_token: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            _url("logout"),
            headers={**_public_headers(), "Authorization": f"Bearer {access_token}"},
        )
    if response.is_error:
        raise SupabaseAuthError("Could not revoke Supabase session")

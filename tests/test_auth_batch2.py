"""
Batch 2 — Authentication & Authorization Security tests.

Tests:
  1. /bootstrap-rep: rejects requests without X-Admin-Secret header
  2. /bootstrap-rep: rejects requests with wrong X-Admin-Secret
  3. /bootstrap-rep: disabled entirely when ADMIN_BOOTSTRAP_SECRET not configured
  4. /upload-roster: role resolved from DB, not JWT claim (JWT-role bypass blocked)
  5. /sync: client cannot self-promote to Rep via payload.role
  6. /sync: existing users keep their DB role even if payload.role differs
"""

import pytest
import jwt
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────
# Helper: build a signed Supabase-style JWT
# ─────────────────────────────────────────────────────────────
def _make_token(uid: str, role: str | None = None, secret: str = "test-secret") -> str:
    claims: dict = {
        "sub": uid,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    if role:
        claims["app_metadata"] = {"role": role}
    return jwt.encode(claims, secret, algorithm="HS256")


# ─────────────────────────────────────────────────────────────
# 1-3: /bootstrap-rep endpoint guard
# ─────────────────────────────────────────────────────────────

class TestBootstrapRepGuard:
    """All checks on the bootstrap-rep secret-header dependency."""

    def test_verify_bootstrap_secret_rejects_missing_header(self):
        """No header → 403."""
        from app.api.auth import _verify_bootstrap_secret

        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_BOOTSTRAP_SECRET = "real-secret"  # pragma: allowlist secret
            with pytest.raises(HTTPException) as exc_info:
                _verify_bootstrap_secret(x_admin_secret=None)
        assert exc_info.value.status_code == 403

    def test_verify_bootstrap_secret_rejects_wrong_header(self):
        """Wrong value → 403 (constant-time compare)."""
        from app.api.auth import _verify_bootstrap_secret

        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_BOOTSTRAP_SECRET = "real-secret"  # pragma: allowlist secret
            with pytest.raises(HTTPException) as exc_info:
                _verify_bootstrap_secret(x_admin_secret="wrong-secret")  # pragma: allowlist secret
        assert exc_info.value.status_code == 403

    def test_verify_bootstrap_secret_accepts_correct_header(self):
        """Correct header → no exception."""
        from app.api.auth import _verify_bootstrap_secret

        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_BOOTSTRAP_SECRET = "real-secret"  # pragma: allowlist secret
            # Should not raise
            _verify_bootstrap_secret(x_admin_secret="real-secret")  # pragma: allowlist secret

    def test_verify_bootstrap_secret_disabled_when_not_configured(self):
        """If env var not set → 503 (disabled)."""
        from app.api.auth import _verify_bootstrap_secret

        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_BOOTSTRAP_SECRET = None
            with pytest.raises(HTTPException) as exc_info:
                _verify_bootstrap_secret(x_admin_secret="anything")  # pragma: allowlist secret
        assert exc_info.value.status_code == 503


# ─────────────────────────────────────────────────────────────
# 4: /upload-roster — role resolved from DB, not JWT
# ─────────────────────────────────────────────────────────────

class TestUploadRosterRoleResolution:
    """Verify that upload-roster checks the DB role, not the JWT claim."""

    @pytest.mark.asyncio
    async def test_upload_roster_blocks_student_with_crafted_jwt_claim(self):
        """
        A Student who crafts a JWT with role='Rep' in the claim must be rejected
        because we read role from the DB, not the token.
        """
        from app.api.auth import upload_roster
        from app.models.models import approles

        # Mock firebase_user: token claims role = Rep (attacker's crafted JWT)
        firebase_user = {
            "uid": "attacker-uid",
            "role": "Rep",  # claimed — should be ignored
            "claims": {"role": "Rep"},
        }

        # Mock DB returns a Student
        mock_db_user = MagicMock()
        mock_db_user.role = approles.Student

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_payload = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await upload_roster(
                payload=mock_payload,
                firebase_user=firebase_user,
                db=mock_db,
            )

        assert exc_info.value.status_code == 403
        assert "representatives" in exc_info.value.detail.lower() or "admin" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_upload_roster_allows_db_rep(self):
        """A user whose DB role is Rep should pass the role check."""
        from app.api.auth import upload_roster
        from app.models.models import approles

        firebase_user = {"uid": "rep-uid"}

        mock_db_user = MagicMock()
        mock_db_user.role = approles.Rep

        mock_db = AsyncMock()

        # First execute call → user lookup; second → roster_auth_service.upload (patched separately)
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_db_user
        mock_db.execute = AsyncMock(return_value=mock_user_result)

        mock_payload = MagicMock()
        mock_payload.roster = []
        mock_payload.department_code = "CSC"

        with patch(
            "app.api.auth.roster_auth_service.upload_department_roster",
            new=AsyncMock(return_value={"uploaded": 0}),
        ):
            result = await upload_roster(
                payload=mock_payload,
                firebase_user=firebase_user,
                db=mock_db,
            )
        assert result == {"uploaded": 0}


# ─────────────────────────────────────────────────────────────
# 5-6: /sync — client cannot self-promote role
# ─────────────────────────────────────────────────────────────

class TestSyncRoleProtection:
    """Verify that /sync never honours client-supplied role for privilege escalation."""

    @pytest.mark.asyncio
    async def test_sync_new_user_ignores_rep_role_in_payload(self):
        """
        A new user that passes role='Rep' in the payload must be created as 'Student'.
        """
        from app.api.auth import sync_user
        from app.schemas.auth import AuthSyncRequest

        firebase_user = {
            "uid": "new-uid-123",
            "email": "newstudent@test.com",
        }

        # Simulate payload with attacker's role escalation attempt
        payload = MagicMock(spec=AuthSyncRequest)
        payload.full_name = "Test Student"
        payload.role = "Rep"   # attacker-controlled — must be ignored
        payload.phone = None

        captured_role = {}

        async def mock_get_or_create(db, firebase_uid, email, full_name, role_str, phone=None):
            captured_role["role_str"] = role_str
            return {"user_id": "u1", "role": "Student", "full_name": full_name}

        mock_db = AsyncMock()

        with patch("app.api.auth.get_or_create_user", side_effect=mock_get_or_create):
            result = await sync_user(
                payload=payload,
                firebase_user=firebase_user,
                db=mock_db,
            )

        # Confirm that "Student" was passed regardless of payload.role = "Rep"
        assert captured_role["role_str"] == "Student", (
            f"Expected role_str='Student' but got '{captured_role['role_str']}'. "
            "Client-supplied role must never be honoured on /sync."
        )

    @pytest.mark.asyncio
    async def test_sync_existing_user_role_not_overwritten(self):
        """
        An existing Rep user who calls /sync must keep their Rep role even if
        the payload carries role='Student'.
        """
        from app.api.auth import sync_user
        from app.schemas.auth import AuthSyncRequest

        firebase_user = {"uid": "existing-rep-uid", "email": "rep@test.com"}
        payload = MagicMock(spec=AuthSyncRequest)
        payload.full_name = "Rep Person"
        payload.role = "Student"  # irrelevant — existing user; role from DB
        payload.phone = None

        # Existing user: get_or_create_user returns DB role 'Rep' unchanged
        async def mock_get_or_create(db, firebase_uid, email, full_name, role_str, phone=None):
            # Simulate: user already exists, DB returns existing role
            return {"user_id": "rep-user", "role": "Rep", "full_name": full_name}

        mock_db = AsyncMock()

        with patch("app.api.auth.get_or_create_user", side_effect=mock_get_or_create):
            result = await sync_user(
                payload=payload,
                firebase_user=firebase_user,
                db=mock_db,
            )

        assert result["role"] == "Rep", (
            "Existing Rep user's DB role must not be downgraded by /sync payload."
        )

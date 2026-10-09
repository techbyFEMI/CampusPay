from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import approles
from app.services.auth_service import AuthService
from app.services.errors import AccessDeniedError


@pytest.mark.asyncio
async def test_roster_upload_uses_database_role():
    session = AsyncMock()
    auth_repository = MagicMock()
    user_repository = MagicMock()
    student = MagicMock(role=approles.Student)
    user_repository.get_user_by_id = AsyncMock(return_value=student)
    service = AuthService(session, auth_repository, user_repository)

    with pytest.raises(AccessDeniedError):
        await service.upload_department_roster(
            user_id="student-id",
            department_code="DS",
            roster_data=[],
        )


@pytest.mark.asyncio
async def test_rep_can_upload_roster_for_existing_department():
    session = AsyncMock()
    auth_repository = MagicMock()
    user_repository = MagicMock()
    rep = MagicMock(role=approles.Rep)
    department = MagicMock()
    department.name = "Data Science"
    user_repository.get_user_by_id = AsyncMock(return_value=rep)
    auth_repository.get_department_by_code = AsyncMock(return_value=department)
    service = AuthService(session, auth_repository, user_repository)

    result = await service.upload_department_roster(
        user_id="rep-id",
        department_code=" ds ",
        roster_data=[],
    )

    assert result == {
        "department_code": "DS",
        "department_name": "Data Science",
        "added": 0,
        "updated": 0,
        "total_records": 0,
    }
    session.commit.assert_awaited_once()

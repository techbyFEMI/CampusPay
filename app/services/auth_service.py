import hashlib
import json
import random
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import approles
from app.models.identity import departments, rosters, users
from app.repositories.auth import AuthRepository
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest
from app.services.supabase_auth import (
    SupabaseAuthError,
    create_auth_user,
    delete_auth_user,
    refresh_session,
    sign_in,
    sign_out,
)
from app.services.errors import AccessDeniedError, UserNotFoundError


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        auth_repository: AuthRepository,
        user_repository: UserRepository,
    ):
        self.session = session
        self.auth_repository = auth_repository
        self.user_repository = user_repository

    async def list_departments(self) -> tuple[list[dict], str]:
        departments_in_db = await self.auth_repository.list_departments()
        data = [
            {
                "department_id": department.department_id,
                "name": department.name,
                "code": department.code,
            }
            for department in departments_in_db
        ]
        etag = hashlib.md5(
            json.dumps(data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return data, etag

    async def bootstrap_rep(
        self,
        *,
        matric_number: str,
        full_name: str,
        email: str,
        password: str,
        department_name: str,
        department_code: str | None = None,
    ) -> dict:
        matric = matric_number.strip().upper()
        name = full_name.strip()
        clean_email = email.strip().lower()
        clean_department_name = department_name.strip()

        if await self.user_repository.get_user_by_matric_number(matric):
            raise ValueError(f"Rep with matric number {matric} already exists.")
        if await self.user_repository.get_user_by_email(clean_email):
            raise ValueError("A user with that email already exists.")

        code = department_code.strip().upper() if department_code else None
        department = await self.auth_repository.get_department_by_code(code) if code else None
        if code is None:
            code = await self._generate_department_code(clean_department_name)
        if department is None:
            department = departments(name=clean_department_name, code=code)
            await self.auth_repository.add_department(department)

        auth_user_id = await create_auth_user(
            email=clean_email,
            password=password,
            metadata={"matric_number": matric, "role": approles.Rep.value},
        )
        try:
            rep = users(
                user_id=auth_user_id,
                matric_number=matric,
                department_id=department.department_id,
                role=approles.Rep,
                full_name=name,
                email=clean_email,
            )
            self.user_repository.add_user(rep)
            self.user_repository.add_wallet(auth_user_id)
            await self.auth_repository.add_roster_entry(
                rosters(
                    department_id=department.department_id,
                    matric_number=matric,
                    full_name=name,
                    is_claimed=True,
                )
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await delete_auth_user(auth_user_id)
            raise

        auth_session = await sign_in(email=clean_email, password=password)
        return {
            **auth_session,
            "user_id": rep.user_id,
            "role": approles.Rep.value,
            "full_name": rep.full_name,
            "department_name": department.name,
            "department_code": department.code,
        }

    async def upload_department_roster(
        self, user_id: str, department_code: str, roster_data: list[dict]
    ) -> dict:
        user = await self.user_repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found")
        if user.role not in (approles.Rep, approles.Admin):
            raise AccessDeniedError(
                "Only department representatives or admins can upload rosters."
            )

        code = department_code.strip().upper()
        department = await self.auth_repository.get_department_by_code(code)
        if department is None:
            raise ValueError(f"Department code '{code}' not found.")

        added = 0
        updated = 0
        for row in roster_data:
            matric = row["matric_number"].strip().upper()
            name = row["full_name"].strip()
            entry = await self.auth_repository.get_roster_entry(
                department.department_id, matric
            )
            if entry:
                entry.full_name = name
                updated += 1
            else:
                await self.auth_repository.add_roster_entry(
                    rosters(
                        department_id=department.department_id,
                        matric_number=matric,
                        full_name=name,
                        is_claimed=False,
                    )
                )
                added += 1

        await self.session.commit()
        return {
            "department_code": code,
            "department_name": department.name,
            "added": added,
            "updated": updated,
            "total_records": added + updated,
        }

    async def lookup_matric_number(
        self, matric_number: str, department_code: str
    ) -> dict:
        code = department_code.strip().upper()
        matric = matric_number.strip().upper()
        department = await self.auth_repository.get_department_by_code(code)
        if department is None:
            raise ValueError(f"Department code '{code}' does not exist.")

        entry = await self.auth_repository.get_roster_entry(
            department.department_id, matric
        )
        if entry is None:
            return {
                "found": False,
                "message": "Matriculation number not found in class roster for this department.",
            }
        return {
            "found": True,
            "matric_number": matric,
            "full_name": entry.full_name,
            "is_claimed": entry.is_claimed,
            "department_name": department.name,
            "department_code": department.code,
        }

    async def claim_student_account(
        self,
        *,
        matric_number: str,
        department_code: str,
        email: str,
        password: str,
        phone: str | None = None,
    ) -> dict:
        code = department_code.strip().upper()
        matric = matric_number.strip().upper()
        clean_email = email.strip().lower()
        department = await self.auth_repository.get_department_by_code(code)
        if department is None:
            raise ValueError(f"Department code '{code}' does not exist.")

        roster_entry = await self.auth_repository.get_roster_entry(
            department.department_id, matric
        )
        if roster_entry is None:
            raise ValueError(
                "Matriculation number not found in official department roster. Access denied."
            )
        if roster_entry.is_claimed:
            raise ValueError(
                "This matriculation number has already been claimed. Please log in instead."
            )
        if await self.user_repository.get_user_by_matric_number(matric):
            raise ValueError("Account already exists for this matriculation number. Please log in.")
        if await self.user_repository.get_user_by_email(clean_email):
            raise ValueError("A user with that email already exists.")

        clean_phone = phone.strip() if phone else None
        if clean_phone and await self.user_repository.get_user_by_phone(clean_phone):
            raise ValueError("A user with that phone number already exists.")

        auth_user_id = await create_auth_user(
            email=clean_email,
            password=password,
            metadata={"matric_number": matric, "role": approles.Student.value},
        )
        try:
            student = users(
                user_id=auth_user_id,
                matric_number=matric,
                department_id=department.department_id,
                role=approles.Student,
                full_name=roster_entry.full_name,
                email=clean_email,
                phone=clean_phone,
            )
            self.user_repository.add_user(student)
            self.user_repository.add_wallet(auth_user_id)
            roster_entry.is_claimed = True
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await delete_auth_user(auth_user_id)
            raise

        auth_session = await sign_in(email=clean_email, password=password)
        return {
            **auth_session,
            "user_id": student.user_id,
            "role": approles.Student.value,
            "full_name": student.full_name,
            "matric_number": matric,
            "balance_kobo": 0,
        }

    async def login_matric(self, matric_number: str, password: str) -> dict:
        matric = matric_number.strip().upper()
        user = await self.user_repository.get_user_by_matric_number(matric)
        if user is None or not user.email:
            raise ValueError("Invalid matriculation number or password.")
        try:
            auth_session = await sign_in(email=user.email, password=password)
        except SupabaseAuthError as exc:
            raise ValueError("Invalid matriculation number or password.") from exc
        return {
            **auth_session,
            "user_id": user.user_id,
            "role": user.role.value,
            "full_name": user.full_name,
            "matric_number": user.matric_number,
        }

    async def register(self, payload: RegisterRequest) -> dict:
        email = payload.email.strip().lower()
        if await self.user_repository.get_user_by_email(email):
            raise ValueError("A user with that email already exists.")

        auth_user_id = await create_auth_user(
            email=email,
            password=payload.password,
            metadata={"full_name": payload.full_name},
        )
        try:
            user = users(
                user_id=auth_user_id,
                role=approles.Student,
                full_name=payload.full_name,
                email=email,
                phone=payload.phone,
            )
            self.user_repository.add_user(user)
            self.user_repository.add_wallet(auth_user_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await delete_auth_user(auth_user_id)
            raise

        auth_session = await sign_in(email=email, password=payload.password)
        return {**auth_session, "profile": self._profile_payload(user)}

    async def sync_user(
        self,
        *,
        auth_user_id: str,
        email: str,
        full_name: str,
        phone: str | None,
    ) -> dict:
        user = await self.user_repository.get_user_by_id(auth_user_id)
        if user is None:
            user = users(
                user_id=auth_user_id,
                role=approles.Student,
                full_name=full_name or "CampusPay User",
                email=email,
                phone=phone,
            )
            self.user_repository.add_user(user)
            self.user_repository.add_wallet(auth_user_id)
        else:
            if full_name and user.full_name in {"CampusPay User", "New User", ""}:
                user.full_name = full_name
            if phone and not user.phone:
                user.phone = phone
        await self.session.commit()
        return self._profile_payload(user)

    def _profile_payload(self, user: users) -> dict:
        return {
            "user_id": user.user_id,
            "role": user.role.value,
            "full_name": user.full_name,
            "balance_kobo": 0,
        }

    async def _generate_department_code(self, department_name: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", department_name)
        if not words:
            prefix = "DEPT"
        elif len(words) == 1:
            prefix = words[0][:4].upper()
        else:
            prefix = "".join(word[0].upper() for word in words[:4])

        while True:
            code = f"{prefix}-{random.randint(100, 999)}"
            if await self.auth_repository.get_department_by_code(code) is None:
                return code


class SupabaseSessionService:
    """Thin application service for auth actions that need no database session."""

    async def login(self, email: str, password: str) -> dict:
        return await sign_in(email=email, password=password)

    async def refresh(self, refresh_token: str) -> dict:
        return await refresh_session(refresh_token)

    async def logout(self, access_token: str) -> None:
        await sign_out(access_token)

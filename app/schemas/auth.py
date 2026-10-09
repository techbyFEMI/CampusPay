from pydantic import BaseModel
from pydantic import field_validator
import re

class AuthSyncRequest(BaseModel):
    full_name: str | None = None
    role: str | None = None   # None on login (existing user) — required on signup
    phone: str | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        name = v.strip()
        if not name:
            return None
    
        if not re.fullmatch(r"[A-Za-z\u00C0-\u024F\s'\-]+", name):
            raise ValueError(
                "Name must contain only letters, spaces, hyphens, or apostrophes. "
                "Special characters like @, #, &, numbers etc. are not allowed."
            )
        return name

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        phone = v.strip()
        if not re.fullmatch(r"^\+?[1-9]\d{7,14}$", phone):
            raise ValueError(
                "Phone number must be a valid international number (e.g. +2348012345678)"
            )
        return phone


class RepBootstrapRequest(BaseModel):
    matric_number: str
    full_name: str
    email: str
    password: str
    department_name: str
    department_code: str | None = None


class LookupMatricRequest(BaseModel):
    matric_number: str
    department_code: str


class ClaimAccountRequest(BaseModel):
    matric_number: str
    department_code: str
    email: str
    password: str
    phone: str | None = None


class LoginMatricRequest(BaseModel):
    matric_number: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str | None = None


class RefreshSessionRequest(BaseModel):
    refresh_token: str


class RosterRow(BaseModel):
    matric_number: str
    full_name: str


class RosterUploadRequest(BaseModel):
    department_code: str
    roster: list[RosterRow]

import logging
import re
import random
import bcrypt
import hashlib
import json
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from firebase_admin import auth as firebase_auth

from app.models.models import users, wallets, accounts, departments, rosters, approles, accstatus
from app.services.nomba import create_virtual_account

logger = logging.getLogger(__name__)


def generate_dept_code(dept_name: str) -> str:
    words = re.findall(r'[A-Za-z0-9]+', dept_name)
    if not words:
        prefix = "DEPT"
    elif len(words) == 1:
        prefix = words[0][:4].upper()
    else:
        prefix = "".join([w[0].upper() for w in words[:4]])
    
    random_num = random.randint(100, 999)
    return f"{prefix}-{random_num}"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def mint_custom_token(matric_number: str, role: str, department_id: str) -> str:
    claims = {
        "role": role,
        "department_id": department_id,
    }
    token_bytes = firebase_auth.create_custom_token(uid=matric_number, developer_claims=claims)
    if isinstance(token_bytes, bytes):
        return token_bytes.decode("utf-8")
    return str(token_bytes)


async def get_all_departments_with_etag(db: AsyncSession) -> tuple[list[dict], str]:
    """Always queries DB. ETag is computed from the result content.
    TODO: Replace DB query with Redis cache lookup when Redis is added to the stack.
    """
    result = await db.execute(select(departments).order_by(departments.name))
    dept_list = result.scalars().all()
    data = [
        {
            "department_id": dept.department_id,
            "name": dept.name,
            "code": dept.code,
        }
        for dept in dept_list
    ]
    # Compute ETag from content — same data always produces the same hash
    etag = hashlib.md5(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
    return data, etag


async def bootstrap_rep(
    db: AsyncSession,
    matric_number: str,
    full_name: str,
    email: str,
    password: str,
    department_name: str,
    department_code: str | None = None,
) -> dict:
    formatted_matric = matric_number.strip().upper()
    clean_dept_name = department_name.strip()

    if not department_code:
        code_candidate = generate_dept_code(clean_dept_name)
        while True:
            existing_dept = await db.execute(
                select(departments).where(departments.code == code_candidate)
            )
            if not existing_dept.scalar_one_or_none():
                break
            code_candidate = generate_dept_code(clean_dept_name)
        formatted_code = code_candidate
    else:
        formatted_code = department_code.strip().upper()

    dept_res = await db.execute(
        select(departments).where(departments.code == formatted_code)
    )
    dept = dept_res.scalar_one_or_none()
    if not dept:
        dept = departments(
            name=clean_dept_name,
            code=formatted_code,
        )
        db.add(dept)
        await db.flush()

    user_res = await db.execute(
        select(users).where(users.matric_number == formatted_matric)
    )
    existing_user = user_res.scalar_one_or_none()
    if existing_user:
        raise ValueError(f"Rep with matric number {formatted_matric} already exists.")

    clean_email = email.strip()
    email_res = await db.execute(
        select(users).where(users.email == clean_email)
    )
    if email_res.scalar_one_or_none():
        raise ValueError(f"User with email '{clean_email}' already exists. Please use a different email or log in.")

    pwd_hash = hash_password(password)

    new_rep = users(
        firebase_uid=formatted_matric,
        matric_number=formatted_matric,
        department_id=dept.department_id,
        role=approles.Rep,
        full_name=full_name.strip(),
        email=clean_email,
        password_hash=pwd_hash,
    )
    db.add(new_rep)
    await db.flush()

    rep_wallet = wallets(
        user_id=new_rep.user_id,
        available_balance=Decimal("0.00"),
        locked_balance=Decimal("0.00"),
        currency="NGN",
    )
    db.add(rep_wallet)

    roster_item = rosters(
        department_id=dept.department_id,
        matric_number=formatted_matric,
        full_name=full_name.strip(),
        is_claimed=True,
    )
    db.add(roster_item)

    await db.commit()

    custom_token = mint_custom_token(
        matric_number=formatted_matric,
        role=approles.Rep.value,
        department_id=dept.department_id,
    )

    return {
        "custom_token": custom_token,
        "user_id": new_rep.user_id,
        "role": approles.Rep.value,
        "full_name": new_rep.full_name,
        "department_name": dept.name,
        "department_code": dept.code,
    }


async def upload_department_roster(
    db: AsyncSession,
    department_code: str,
    roster_data: list[dict],
) -> dict:
    formatted_code = department_code.strip().upper()
    dept_res = await db.execute(
        select(departments).where(departments.code == formatted_code)
    )
    dept = dept_res.scalar_one_or_none()
    if not dept:
        raise ValueError(f"Department code '{formatted_code}' not found.")

    added_count = 0
    updated_count = 0

    for row in roster_data:
        matric = row["matric_number"].strip().upper()
        name = row["full_name"].strip()

        roster_res = await db.execute(
            select(rosters).where(
                rosters.department_id == dept.department_id,
                rosters.matric_number == matric,
            )
        )
        existing = roster_res.scalar_one_or_none()
        if existing:
            existing.full_name = name
            updated_count += 1
        else:
            new_entry = rosters(
                department_id=dept.department_id,
                matric_number=matric,
                full_name=name,
                is_claimed=False,
            )
            db.add(new_entry)
            added_count += 1

    await db.commit()
    return {
        "department_code": formatted_code,
        "department_name": dept.name,
        "added": added_count,
        "updated": updated_count,
        "total_records": added_count + updated_count,
    }


async def lookup_matric_number(
    db: AsyncSession,
    matric_number: str,
    department_code: str,
) -> dict:
    formatted_code = department_code.strip().upper()
    formatted_matric = matric_number.strip().upper()

    dept_res = await db.execute(
        select(departments).where(departments.code == formatted_code)
    )
    dept = dept_res.scalar_one_or_none()
    if not dept:
        raise ValueError(f"Department code '{formatted_code}' does not exist.")

    roster_res = await db.execute(
        select(rosters).where(
            rosters.department_id == dept.department_id,
            rosters.matric_number == formatted_matric,
        )
    )
    roster_entry = roster_res.scalar_one_or_none()
    if not roster_entry:
        return {
            "found": False,
            "message": "Matriculation number not found in class roster for this department.",
        }

    return {
        "found": True,
        "matric_number": formatted_matric,
        "full_name": roster_entry.full_name,
        "is_claimed": roster_entry.is_claimed,
        "department_name": dept.name,
        "department_code": dept.code,
    }


async def claim_student_account(
    db: AsyncSession,
    matric_number: str,
    department_code: str,
    email: str,
    password: str,
    phone: str | None = None,
) -> dict:
    formatted_code = department_code.strip().upper()
    formatted_matric = matric_number.strip().upper()

    dept_res = await db.execute(
        select(departments).where(departments.code == formatted_code)
    )
    dept = dept_res.scalar_one_or_none()
    if not dept:
        raise ValueError(f"Department code '{formatted_code}' does not exist.")

    roster_res = await db.execute(
        select(rosters).where(
            rosters.department_id == dept.department_id,
            rosters.matric_number == formatted_matric,
        )
    )
    roster_entry = roster_res.scalar_one_or_none()
    if not roster_entry:
        raise ValueError("Matriculation number not found in official department roster. Access denied.")

    if roster_entry.is_claimed:
        raise ValueError("This matriculation number has already been claimed. Please log in instead.")

    user_res = await db.execute(
        select(users).where(users.matric_number == formatted_matric)
    )
    db_user = user_res.scalar_one_or_none()
    if db_user:
        raise ValueError("Account already exists for this matriculation number. Please log in.")

    clean_email = email.strip()
    email_res = await db.execute(
        select(users).where(users.email == clean_email)
    )
    if email_res.scalar_one_or_none():
        raise ValueError(f"User with email '{clean_email}' already exists. Please use a different email or log in.")

    if phone:
        clean_phone = phone.strip()
        phone_res = await db.execute(
            select(users).where(users.phone == clean_phone)
        )
        if phone_res.scalar_one_or_none():
            raise ValueError(f"User with phone number '{clean_phone}' already exists.")

    pwd_hash = hash_password(password)

    new_user = users(
        firebase_uid=formatted_matric,
        matric_number=formatted_matric,
        department_id=dept.department_id,
        role=approles.Student,
        full_name=roster_entry.full_name,
        email=clean_email,
        phone=phone.strip() if phone else None,
        password_hash=pwd_hash,
    )
    db.add(new_user)
    await db.flush()

    new_wallet = wallets(
        user_id=new_user.user_id,
        available_balance=Decimal("0.00"),
        locked_balance=Decimal("0.00"),
        currency="NGN",
    )
    db.add(new_wallet)

    roster_entry.is_claimed = True

    account_ref = new_user.user_id
    va_data = {}
    try:
        va_response = await create_virtual_account(
            student_name=roster_entry.full_name,
            account_ref=account_ref,
        )
        if va_response.get("code") == "00":
            va_info = va_response.get("data", {})
            new_account = accounts(
                student_id=new_user.user_id,
                account_reference=account_ref,
                bank_account_number=va_info.get("bankAccountNumber"),
                bank_name=va_info.get("bankName"),
                status=accstatus.active,
            )
            db.add(new_account)
            va_data = {
                "bank_account_number": va_info.get("bankAccountNumber"),
                "bank_name": va_info.get("bankName"),
            }
    except Exception as e:
        logger.warning(f"Virtual account creation skipped or failed for {new_user.user_id}: {e}")

    await db.commit()

    custom_token = mint_custom_token(
        matric_number=formatted_matric,
        role=approles.Student.value,
        department_id=dept.department_id,
    )

    return {
        "custom_token": custom_token,
        "user_id": new_user.user_id,
        "role": approles.Student.value,
        "full_name": new_user.full_name,
        "matric_number": formatted_matric,
        "available_balance": "0.00",
        **va_data,
    }


async def login_user(
    db: AsyncSession,
    matric_number: str,
    password: str,
) -> dict:
    formatted_matric = matric_number.strip().upper()

    user_res = await db.execute(
        select(users).where(users.matric_number == formatted_matric)
    )
    db_user = user_res.scalar_one_or_none()
    if not db_user:
        raise ValueError("Invalid matriculation number or password.")

    if not verify_password(password, db_user.password_hash):
        raise ValueError("Invalid matriculation number or password.")

    wallet_res = await db.execute(
        select(wallets).where(wallets.user_id == db_user.user_id)
    )
    wallet = wallet_res.scalar_one_or_none()

    custom_token = mint_custom_token(
        matric_number=formatted_matric,
        role=db_user.role.value,
        department_id=db_user.department_id or "",
    )

    return {
        "custom_token": custom_token,
        "user_id": db_user.user_id,
        "role": db_user.role.value,
        "full_name": db_user.full_name,
        "matric_number": db_user.matric_number,
        "available_balance": str(wallet.available_balance) if wallet else "0.00",
    }

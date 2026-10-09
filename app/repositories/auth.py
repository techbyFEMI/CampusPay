from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import departments, rosters


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_departments(self):
        result = await self.session.execute(
            select(departments).order_by(departments.name)
        )
        return result.scalars().all()

    async def get_department_by_code(self, code: str):
        result = await self.session.execute(
            select(departments).where(departments.code == code)
        )
        return result.scalar_one_or_none()

    async def add_department(self, department: departments):
        self.session.add(department)
        await self.session.flush()
        return department

    async def get_roster_entry(self, department_id: str, matric_number: str):
        result = await self.session.execute(
            select(rosters).where(
                rosters.department_id == department_id,
                rosters.matric_number == matric_number,
            )
        )
        return result.scalar_one_or_none()

    async def add_roster_entry(self, roster_entry: rosters):
        self.session.add(roster_entry)
        return roster_entry

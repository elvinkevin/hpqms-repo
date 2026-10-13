"""Bootstrap the first administrator account.

This is the ONLY seeding that runs at startup. Unlike seed.py (development
demo data), it creates no staff or service points — those are created
through the admin dashboard. It ensures the four starter service departments
and a dedicated Administration department exist so the first admin can log in
without being attached to a clinical area.

Safe to run on every start:
- If admins already exist, it ensures they are attached to Administration and
  does not change their credentials.
- If no admin exists, it creates one using INITIAL_ADMIN_EMPLOYEE_ID /
  INITIAL_ADMIN_PASSWORD. In development, sensible defaults are used so a
  fresh developer environment can log in immediately.
"""

import asyncio

from sqlalchemy.future import select

from app.core.security import hash_password
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.domain.models.models import Department, DeptType, Staff, StaffRole

STARTER_DEPARTMENTS = [
    {"name": "Reception Desk", "department_code": "REC", "type": DeptType.OPD, "max_capacity": 50},
    {"name": "Emergency Department", "department_code": "EMERGENCY", "type": DeptType.EMERGENCY, "max_capacity": 30},
    {"name": "Triage & Vitals Station", "department_code": "TRIAGE", "type": DeptType.OPD, "max_capacity": 15},
    {"name": "General Consultation", "department_code": "CONSULT", "type": DeptType.OPD, "max_capacity": 25},
]
ADMIN_DEPARTMENT = {
    "name": "Administration",
    "department_code": "ADMIN",
    # DeptType has no administrative value; OPD is its general-purpose type.
    "type": DeptType.OPD,
    "max_capacity": 1,
}


def initial_admin_credentials():
    """Return explicitly configured bootstrap credentials."""
    employee_id = settings.INITIAL_ADMIN_EMPLOYEE_ID
    password = settings.INITIAL_ADMIN_PASSWORD
    if not employee_id or not password:
        return None
    if len(password) < 12:
        raise ValueError("INITIAL_ADMIN_PASSWORD must be at least 12 characters.")
    return employee_id, password


async def bootstrap_admin():
    async with AsyncSessionLocal() as db:
        admin_department = (
            await db.execute(
                select(Department).where(
                    Department.department_code == ADMIN_DEPARTMENT["department_code"]
                )
            )
        ).scalar_one_or_none()
        existing_admins = (
            await db.execute(select(Staff).where(Staff.role == StaffRole.ADMIN))
        ).scalars().all()

        # Existing deployments may have the first admin attached to a clinical
        # department. Give admins a dedicated department and correct that link.
        if existing_admins:
            created_admin_department = admin_department is None
            if admin_department is None:
                admin_department = Department(**ADMIN_DEPARTMENT)
                db.add(admin_department)
                await db.flush()
            changed = False
            for admin in existing_admins:
                if admin.dept_id != admin_department.dept_id:
                    admin.dept_id = admin_department.dept_id
                    changed = True
            if created_admin_department or changed:
                await db.commit()
            print(
                f"Administrator department verified ({len(existing_admins)} admin account(s)); "
                "admin account creation skipped."
            )
            return

        credentials = initial_admin_credentials()
        if credentials is None:
            raise RuntimeError(
                "No administrator exists. Set INITIAL_ADMIN_EMPLOYEE_ID and "
                "INITIAL_ADMIN_PASSWORD before starting the application."
            )
        admin_employee_id, admin_password = credentials

        collision_result = await db.execute(
            select(Staff).where(Staff.employee_id == admin_employee_id)
        )
        if collision_result.scalar_one_or_none():
            raise RuntimeError(
                f"Employee ID {admin_employee_id!r} is already used by a non-admin; "
                "choose a different INITIAL_ADMIN_EMPLOYEE_ID."
            )

        created_names = []
        for spec in STARTER_DEPARTMENTS:
            existing = (
                await db.execute(
                    select(Department).where(
                        (Department.department_code == spec["department_code"])
                        | (Department.name == spec["name"])
                    )
                )
            ).scalars().first()
            if existing is None:
                db.add(Department(**spec))
                created_names.append(spec["name"])

        created_admin_department = admin_department is None
        if created_admin_department:
            admin_department = Department(**ADMIN_DEPARTMENT)
            db.add(admin_department)
        await db.flush()
        await db.refresh(admin_department)
        await db.commit()
        if created_names:
            print(f"Created starter departments: {', '.join(created_names)}")
        if created_admin_department:
            print(f"Created administrator department: {admin_department.name}")

        admin = Staff(
            employee_id=admin_employee_id,
            dept_id=admin_department.dept_id,
            first_name="Hospital",
            last_name="Administrator",
            role=StaffRole.ADMIN,
            specialization="System Administration",
            hashed_password=hash_password(admin_password),
            admin_setup_complete=False,
        )
        db.add(admin)
        await db.commit()
        print(
            f"Bootstrapped initial administrator: {admin_employee_id} "
            f"({admin_department.name})"
        )


if __name__ == "__main__":
    asyncio.run(bootstrap_admin())

"""
Seed script — run once after migrations:
    python scripts/seed.py

Creates:
  - 3 departments (OPD, Emergency, Cardiology)
  - 5 staff accounts (1 receptionist, 2 nurses, 2 doctors)
  - 1 test patient
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.security import hash_password
from app.domain.models.models import (
    Department, Staff, Patient, DeptType, StaffRole
)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with Session() as db:
        # ── Departments ──────────────────────────────────────────────────
        opd = Department(name="General OPD", code="OPD", type=DeptType.OPD, max_capacity=80)
        eme = Department(name="Emergency", code="EME", type=DeptType.EMERGENCY, max_capacity=30)
        card= Department(name="Cardiology", code="CARD", type=DeptType.SPECIALIST, max_capacity=40)
        db.add_all([opd, eme, card])
        await db.flush()

        print(f"  Departments: OPD={opd.dept_id}, EME={eme.dept_id}, CARD={card.dept_id}")

        # ── Staff ────────────────────────────────────────────────────────
        staff_data = [
            {
                "employee_id": "REC-001", "dept_id": opd.dept_id,
                "first_name": "Aisha", "last_name": "Wanjiku",
                "role": StaffRole.RECEPTIONIST, "password": "reception123",
            },
            {
                "employee_id": "NRS-001", "dept_id": opd.dept_id,
                "first_name": "Amina", "last_name": "Kamau",
                "role": StaffRole.TRIAGE_NURSE, "password": "nurse123",
            },
            {
                "employee_id": "NRS-002", "dept_id": eme.dept_id,
                "first_name": "Faith", "last_name": "Otieno",
                "role": StaffRole.CHARGE_NURSE, "password": "nurse123",
            },
            {
                "employee_id": "DOC-001", "dept_id": opd.dept_id,
                "first_name": "Kipchoge", "last_name": "Maina",
                "role": StaffRole.DOCTOR, "password": "doctor123",
                "specialization": "General Practice",
            },
            {
                "employee_id": "DOC-002", "dept_id": card.dept_id,
                "first_name": "Wanjiru", "last_name": "Odhiambo",
                "role": StaffRole.DOCTOR, "password": "doctor123",
                "specialization": "Cardiology",
            },
        ]

        for s in staff_data:
            pw = s.pop("password")
            staff = Staff(**s, hashed_password=hash_password(pw), is_on_duty=True)
            db.add(staff)
            print(f"  Staff: {s['employee_id']} / {pw}")

        # ── Test patient ─────────────────────────────────────────────────
        patient = Patient(
            national_id="12345678",
            first_name="James",
            last_name="Odhiambo",
            phone="+254712000001",
            blood_type="O+",
        )
        db.add(patient)

        await db.commit()
        print(f"\n  Test patient: James Odhiambo / national_id=12345678")
        print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())

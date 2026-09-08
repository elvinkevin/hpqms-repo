import asyncio
from sqlalchemy.future import select

# Native password hashing utility
from app.core.security import hash_password 

# Database session & models
from app.db.session import AsyncSessionLocal 
from app.domain.models.models import Department, Staff, DeptType, StaffRole 


async def seed_hospital_data():
    print("🚀 Starting logic-aligned hospital database seeding pipeline...")
    
    async with AsyncSessionLocal() as db:  
        try:
            # -----------------------------------------------------------
            # 1. SEED DEPARTMENTS WITH STRICT SYSTEM CODES (Max 10 chars)
            # -----------------------------------------------------------
            departments_to_create = [
                {
                    "name": "Reception Desk",
                    "department_code": "REC",
                    "type": DeptType.OPD,
                    "max_capacity": 50,
                },
                {
                    "name": "Emergency Department",
                    "department_code": "EMERGENCY",
                    "type": DeptType.EMERGENCY,
                    "max_capacity": 30,
                },
                {
                    "name": "Triage & Vitals Station",
                    "department_code": "TRIAGE",
                    "type": DeptType.OPD,
                    "max_capacity": 15,
                },
                {
                    "name": "General Consultation",
                    "department_code": "CONSULT",  # Shortened to fit VARCHAR(10)
                    "type": DeptType.OPD,
                    "max_capacity": 25,
                },
            ]

            seeded_departments = {}
            for dept_data in departments_to_create:
                query = await db.execute(
                    select(Department).where(
                        Department.department_code == dept_data["department_code"]
                    )
                )
                existing_dept = query.scalar_one_or_none()

                if not existing_dept:
                    dept = Department(**dept_data)
                    db.add(dept)
                    await db.flush() 
                    seeded_departments[dept.department_code] = dept
                    print(f"🏥 Seeded Department: {dept.name} [{dept.department_code}]")
                else:
                    seeded_departments[existing_dept.department_code] = existing_dept

            # -----------------------------------------------------------
            # 2. SEED STAFF MEMBERS USING NATIVE HASHER
            # -----------------------------------------------------------
            secure_hash = hash_password("SecurePassword123")

            staff_to_create = [
                {
                    "employee_id": "EMP-RECEP01",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Jane",
                    "last_name": "Moraa",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Front Desk Operations",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-TRIAGE01",
                    "dept_id": seeded_departments["TRIAGE"].dept_id,
                    "first_name": "John",
                    "last_name": "Ondieki",
                    "role": StaffRole.TRIAGE_NURSE,
                    "specialization": "Trauma & Acute Triage",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-DOC01",
                    "dept_id": seeded_departments["CONSULT"].dept_id,  # Mapped to CONSULT
                    "first_name": "Alice",
                    "last_name": "Wanjiku",
                    "role": StaffRole.DOCTOR,
                    "specialization": "General Medicine & Outpatient Care",
                    "hashed_password": secure_hash,
                },
            ]

            for staff_data in staff_to_create:
                query = await db.execute(
                    select(Staff).where(Staff.employee_id == staff_data["employee_id"])
                )
                existing_staff = query.scalar_one_or_none()

                if not existing_staff:
                    staff_member = Staff(**staff_data)
                    db.add(staff_member)
                    print(
                        f"👤 Seeded Staff: {staff_member.first_name} {staff_member.last_name} ({staff_member.role.value})"
                    )
                else:
                    existing_staff.hashed_password = secure_hash
                    print(
                        f"🔄 Updated password hash for existing staff: {existing_staff.employee_id}"
                    )

            await db.commit()
            print("🎉 Database seeding finalized successfully. System codes and credentials synchronized.")

        except Exception as error:
            await db.rollback()
            print("❌ Seeding execution failure occurred:", error)
            raise error


if __name__ == "__main__":
    asyncio.run(seed_hospital_data())
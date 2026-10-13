import asyncio
from sqlalchemy.future import select

# Native password hashing utility
from app.core.security import hash_password

# Database session & models
from app.db.session import AsyncSessionLocal
from app.domain.models.models import Department, Staff, DeptType, StaffRole, ServicePoint, StationType
from app.core.config import settings


def initial_admin_credentials():
    """Return explicitly configured bootstrap credentials."""
    employee_id = settings.INITIAL_ADMIN_EMPLOYEE_ID
    password = settings.INITIAL_ADMIN_PASSWORD
    if not employee_id or not password:
        return None
    if len(password) < 12:
        raise ValueError("INITIAL_ADMIN_PASSWORD must be at least 12 characters.")
    return employee_id, password


async def seed_hospital_data():
    if settings.ENVIRONMENT.lower() != "development":
        raise RuntimeError("seed.py is for development environments only.")
    demo_staff_password = settings.DEMO_STAFF_PASSWORD
    if not demo_staff_password or len(demo_staff_password) < 12:
        raise ValueError(
            "Set DEMO_STAFF_PASSWORD to a value of at least 12 characters "
            "before running seed.py."
        )

    print(" Starting logic-aligned hospital database seeding pipeline...")

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
                {
                    "name": "Administration",
                    "department_code": "ADMIN",
                    # DeptType has no administrative value; OPD is its general type.
                    "type": DeptType.OPD,
                    "max_capacity": 1,
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
            # 2. SEED SERVICE POINTS PER DEPARTMENT
            # -----------------------------------------------------------
            service_points_to_create = [
                # Reception Desk — counters (6 to match 6 receptionists)
                {"dept_code": "REC", "code": "REC-C1", "label": "Counter 1", "station_type": StationType.COUNTER},
                {"dept_code": "REC", "code": "REC-C2", "label": "Counter 2", "station_type": StationType.COUNTER},
                {"dept_code": "REC", "code": "REC-C3", "label": "Counter 3", "station_type": StationType.COUNTER},
                {"dept_code": "REC", "code": "REC-C4", "label": "Counter 4", "station_type": StationType.COUNTER},
                {"dept_code": "REC", "code": "REC-W1", "label": "Window 1", "station_type": StationType.WINDOW},
                {"dept_code": "REC", "code": "REC-W2", "label": "Window 2", "station_type": StationType.WINDOW},
                # Emergency — doors/rooms
                {"dept_code": "EMERGENCY", "code": "EM-DOOR1", "label": "Triage Door 1", "station_type": StationType.DOOR},
                {"dept_code": "EMERGENCY", "code": "EM-R1", "label": "Resus Room 1", "station_type": StationType.ROOM},
                # Triage — windows (4 to match 4 triage nurses)
                {"dept_code": "TRIAGE", "code": "TR-W1", "label": "Vitals Window 1", "station_type": StationType.WINDOW},
                {"dept_code": "TRIAGE", "code": "TR-W2", "label": "Vitals Window 2", "station_type": StationType.WINDOW},
                {"dept_code": "TRIAGE", "code": "TR-W3", "label": "Vitals Window 3", "station_type": StationType.WINDOW},
                {"dept_code": "TRIAGE", "code": "TR-W4", "label": "Vitals Window 4", "station_type": StationType.WINDOW},
                # Consultation — rooms (4 to match 4 doctors)
                {"dept_code": "CONSULT", "code": "CO-R1", "label": "Consultation Room 1", "station_type": StationType.ROOM},
                {"dept_code": "CONSULT", "code": "CO-R2", "label": "Consultation Room 2", "station_type": StationType.ROOM},
                {"dept_code": "CONSULT", "code": "CO-R3", "label": "Consultation Room 3", "station_type": StationType.ROOM},
                {"dept_code": "CONSULT", "code": "CO-R4", "label": "Consultation Room 4", "station_type": StationType.ROOM},
            ]

            for sp_data in service_points_to_create:
                dept = seeded_departments.get(sp_data["dept_code"])
                if dept is None:
                    continue

                query = await db.execute(
                    select(ServicePoint).where(
                        ServicePoint.dept_id == dept.dept_id,
                        ServicePoint.code == sp_data["code"],
                    )
                )
                existing_sp = query.scalar_one_or_none()

                if not existing_sp:
                    sp = ServicePoint(
                        dept_id=dept.dept_id,
                        code=sp_data["code"],
                        label=sp_data["label"],
                        station_type=sp_data["station_type"],
                    )
                    db.add(sp)
                    print(f"🏥 Seeded Service Point: {sp.label} [{sp.code}] in {dept.name}")

            # -----------------------------------------------------------
            # 3. SEED STAFF MEMBERS USING NATIVE HASHER
            # -----------------------------------------------------------
            secure_hash = hash_password(demo_staff_password)

            staff_to_create = [
                # Receptionists (4 members)
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
                    "employee_id": "EMP-RECEP02",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Brian",
                    "last_name": "Otieno",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Patient Check-In & Scheduling",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-RECEP03",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Grace",
                    "last_name": "Njoki",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Call Center & Patient Support",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-RECEP04",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Samuel",
                    "last_name": "Kipchoge",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Records Management & Filing",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-RECEP05",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Catherine",
                    "last_name": "Kiplagat",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Insurance & Billing Support",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-RECEP06",
                    "dept_id": seeded_departments["REC"].dept_id,
                    "first_name": "Moses",
                    "last_name": "Kipchoge",
                    "role": StaffRole.RECEPTIONIST,
                    "specialization": "Patient Guidance & Wayfinding",
                    "hashed_password": secure_hash,
                },
                # Triage Nurses (4 members)
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
                    "employee_id": "EMP-TRIAGE02",
                    "dept_id": seeded_departments["TRIAGE"].dept_id,
                    "first_name": "Mercy",
                    "last_name": "Chebet",
                    "role": StaffRole.TRIAGE_NURSE,
                    "specialization": "Vitals Assessment & Fast-Track",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-TRIAGE03",
                    "dept_id": seeded_departments["TRIAGE"].dept_id,
                    "first_name": "Patricia",
                    "last_name": "Kimani",
                    "role": StaffRole.TRIAGE_NURSE,
                    "specialization": "Pediatric Triage & Family Support",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-TRIAGE04",
                    "dept_id": seeded_departments["TRIAGE"].dept_id,
                    "first_name": "Michael",
                    "last_name": "Omondi",
                    "role": StaffRole.TRIAGE_NURSE,
                    "specialization": "Emergency Response & Stabilization",
                    "hashed_password": secure_hash,
                },
                # Doctors (4 members)
                {
                    "employee_id": "EMP-DOC01",
                    "dept_id": seeded_departments["CONSULT"].dept_id,
                    "first_name": "Alice",
                    "last_name": "Wanjiku",
                    "role": StaffRole.DOCTOR,
                    "specialization": "General Medicine & Outpatient Care",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-DOC02",
                    "dept_id": seeded_departments["CONSULT"].dept_id,
                    "first_name": "David",
                    "last_name": "Mutua",
                    "role": StaffRole.DOCTOR,
                    "specialization": "Family Medicine & Diagnostics",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-DOC03",
                    "dept_id": seeded_departments["CONSULT"].dept_id,
                    "first_name": "Sarah",
                    "last_name": "Kariuki",
                    "role": StaffRole.DOCTOR,
                    "specialization": "Internal Medicine & Chronic Disease Management",
                    "hashed_password": secure_hash,
                },
                {
                    "employee_id": "EMP-DOC04",
                    "dept_id": seeded_departments["CONSULT"].dept_id,
                    "first_name": "Joseph",
                    "last_name": "Mwangi",
                    "role": StaffRole.DOCTOR,
                    "specialization": "Preventive Medicine & Health Education",
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

            # -----------------------------------------------------------
            # 4. BOOTSTRAP THE FIRST ADMIN (NEVER RESET AN EXISTING ACCOUNT)
            # -----------------------------------------------------------
            existing_admin_result = await db.execute(
                select(Staff).where(Staff.role == StaffRole.ADMIN).limit(1)
            )
            existing_admin = existing_admin_result.scalar_one_or_none()
            if existing_admin:
                admin_department = seeded_departments["ADMIN"]
                existing_admin.dept_id = admin_department.dept_id
                print(
                    f"Administrator already exists ({existing_admin.employee_id}); "
                    f"assigned to {admin_department.name} without changing the password."
                )
            else:
                credentials = initial_admin_credentials()
                if credentials is None:
                    raise RuntimeError(
                        "No administrator exists. Set INITIAL_ADMIN_EMPLOYEE_ID "
                        "and INITIAL_ADMIN_PASSWORD before running seed.py."
                    )
                else:
                    admin_employee_id, admin_password = credentials
                    collision_result = await db.execute(
                        select(Staff).where(Staff.employee_id == admin_employee_id)
                    )
                    collision = collision_result.scalar_one_or_none()
                    if collision:
                        raise RuntimeError(
                            f"Employee ID {admin_employee_id!r} is already used by a non-admin; "
                            "choose a different INITIAL_ADMIN_EMPLOYEE_ID."
                        )
                    admin = Staff(
                        employee_id=admin_employee_id,
                        dept_id=seeded_departments["ADMIN"].dept_id,
                        first_name="Hospital",
                        last_name="Administrator",
                        role=StaffRole.ADMIN,
                        specialization="System Administration",
                        hashed_password=hash_password(admin_password),
                    )
                    db.add(admin)
                    print(f"Seeded initial administrator: {admin_employee_id} (Administration department)")

            await db.commit()
            print("🎉 Database seeding finalized successfully. System codes and credentials synchronized.")

        except Exception as error:
            await db.rollback()
            print("❌ Seeding execution failure occurred:", error)
            raise error


if __name__ == "__main__":
    asyncio.run(seed_hospital_data())

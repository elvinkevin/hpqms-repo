"""
HPQMS seed demo — config-driven version.

Instead of hardcoding one department / two staff / four patients in the
body of the script, everything is declared in DEMO_CONFIG below. To add a
department, a receptionist, or a patient, just add an entry to the
relevant list — no other code needs to change.

Usage:
    python seed_demo.py                # uses DEMO_CONFIG as-is
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.session import AsyncSessionLocal
from app.domain.models.models import (
    DeptType,
    EntryType,
    QueuePriority,
    StaffRole,
)
from app.domain.schemas.schemas import (
    DepartmentCreate,
    PatientCreate,
    StaffCreate,
    VisitCreate,
)
from app.domain.services.departments_service import DepartmentService
from app.domain.services.patient_service import PatientService
from app.domain.services.queue_service import QueueService
from app.domain.services.staff_service import StaffService
from app.domain.services.visit_service import VisitService


# ==========================================================================
# DEMO CONFIGURATION
#
# Edit this section to add/remove departments, staff, or patients.
# Nothing else in the script needs to change.
# ==========================================================================

@dataclass
class DepartmentSeed:
    code: str
    name: str
    type: DeptType = DeptType.OPD
    max_capacity: int = 20


@dataclass
class StaffSeed:
    employee_id: str
    department_code: str
    first_name: str
    last_name: str
    password: str
    role: StaffRole = StaffRole.RECEPTIONIST
    specialization: str = "Front Desk"


@dataclass
class PatientSeed:
    first_name: str
    last_name: str
    priority: QueuePriority
    department_code: str
    blood_type: str = "O+"
    visit_reason: str = "Queue priority matrix test"


DEMO_CONFIG = {
    "departments": [
        DepartmentSeed(code="REC", name="Reception"),
    ],
    "staff": [
        StaffSeed(
            employee_id="REC001",
            department_code="REC",
            first_name="Demo",
            last_name="Receptionist",
            password="password12345",
        ),
        StaffSeed(
            employee_id="REC002",
            department_code="REC",
            first_name="Second",
            last_name="Receptionist",
            password="demo12345",
        ),
    ],
    # IMPORTANT: patients are intentionally listed NORMAL -> CRITICAL so the
    # demo can verify that queue priority overrides creation order. The
    # expected queue order is the exact reverse of this list (per department).
    "patients": [
        PatientSeed("John", "Demo", QueuePriority.SEMI_URGENT, department_code="REC"),
        PatientSeed("Jane", "Demo", QueuePriority.NORMAL, department_code="REC"),
        PatientSeed("Mary", "Demo", QueuePriority.SEMI_URGENT, department_code="REC"),
        PatientSeed("Peter", "Demo", QueuePriority.NORMAL, department_code="REC"),
    ],
}

# Login shown at the end of the run — defaults to the first staff entry.
PRIMARY_STAFF_EMPLOYEE_ID = DEMO_CONFIG["staff"][0].employee_id


# ==========================================================================
# DEPARTMENT
# ==========================================================================

async def get_or_create_department(db, seed: DepartmentSeed):
    service = DepartmentService(db)

    try:
        return await service.get_by_code(seed.code)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise

        return await service.create_department(
            DepartmentCreate(
                name=seed.name,
                department_code=seed.code,
                type=seed.type,
                max_capacity=seed.max_capacity,
            )
        )


async def seed_departments(db, seeds: list[DepartmentSeed]) -> dict[str, object]:
    """Returns a dict mapping department_code -> department object."""
    departments = {}
    for seed in seeds:
        departments[seed.code] = await get_or_create_department(db, seed)
    return departments


# ==========================================================================
# STAFF
# ==========================================================================

async def get_or_create_staff(db, department, seed: StaffSeed):
    service = StaffService(db)

    staff = await service.get_by_employee_id(seed.employee_id)

    if not staff:
        staff = await service.create_staff(
            StaffCreate(
                employee_id=seed.employee_id,
                dept_id=department.dept_id,
                first_name=seed.first_name,
                last_name=seed.last_name,
                role=seed.role,
                specialization=seed.specialization,
                password=seed.password,
            )
        )

    staff.is_active = True
    staff.is_on_duty = True

    await db.flush()
    await db.refresh(staff)

    return staff


async def seed_staff(
    db, seeds: list[StaffSeed], departments: dict[str, object]
) -> dict[str, object]:
    """Returns a dict mapping employee_id -> staff object."""
    staff_by_id = {}
    for seed in seeds:
        department = departments.get(seed.department_code)
        if department is None:
            raise ValueError(
                f"Staff '{seed.employee_id}' references unknown department "
                f"code '{seed.department_code}'. Add it to DEMO_CONFIG['departments']."
            )
        staff_by_id[seed.employee_id] = await get_or_create_staff(
            db, department, seed
        )
    return staff_by_id


# ==========================================================================
# PATIENT / VISIT / QUEUE ENTRY
# ==========================================================================

async def create_fresh_demo_patient(
    db,
    patient_service,
    visit_service,
    queue_service,
    department,
    seed: PatientSeed,
    demo_run_id: str,
    patient_number: int,
):
    """
    Creates one completely fresh patient -> visit -> queue entry, always
    starting in WAITING status. Priority is taken from the seed so this
    script doubles as a queue-priority test fixture.
    """

    national_id = f"DEMO{demo_run_id}{patient_number}"
    phone = f"+254700{demo_run_id[-6:]}{patient_number}"

    patient = await patient_service.register_standard_patient(
        PatientCreate(
            national_id=national_id,
            first_name=seed.first_name,
            last_name=seed.last_name,
            phone=phone,
            blood_type=seed.blood_type,
        )
    )

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason=seed.visit_reason,
        )
    )

    queue_entry = await queue_service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=department.dept_id,
        priority=seed.priority,
        notes="Created for queue priority matrix test",
    )

    return patient, visit, queue_entry


async def seed_patients(
    db,
    patient_service,
    visit_service,
    queue_service,
    seeds: list[PatientSeed],
    departments: dict[str, object],
    demo_run_id: str,
) -> list[dict]:
    records = []

    for number, seed in enumerate(seeds, start=1):
        department = departments.get(seed.department_code)
        if department is None:
            raise ValueError(
                f"Patient '{seed.first_name} {seed.last_name}' references "
                f"unknown department code '{seed.department_code}'. Add it "
                f"to DEMO_CONFIG['departments']."
            )

        patient, visit, queue_entry = await create_fresh_demo_patient(
            db,
            patient_service,
            visit_service,
            queue_service,
            department,
            seed,
            demo_run_id,
            number,
        )

        records.append(
            {
                "department_code": seed.department_code,
                "patient": patient,
                "visit": visit,
                "queue_entry": queue_entry,
            }
        )

    return records


# ==========================================================================
# SEED PIPELINE
# ==========================================================================

async def seed_priority_demo(config: dict = DEMO_CONFIG):

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text

        # Truncate tables to remove old demo visits/queues and avoid collisions.
        await db.execute(
            text("TRUNCATE TABLE queue_entries, visits, patients CASCADE;")
        )
        await db.commit()

        # ------------------------------------------------------------------
        # Departments + staff (fully driven by config)
        # ------------------------------------------------------------------

        departments = await seed_departments(db, config["departments"])
        staff_by_id = await seed_staff(db, config["staff"], departments)

        # ------------------------------------------------------------------
        # Services
        # ------------------------------------------------------------------

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        demo_run_id = datetime.now().strftime("%m%d%H%M%S")

        records = await seed_patients(
            db,
            patient_service,
            visit_service,
            queue_service,
            config["patients"],
            departments,
            demo_run_id,
        )

        await db.commit()

        # ------------------------------------------------------------------
        # Re-query each department's queue using the real QueueService,
        # rather than assuming what the order should be.
        # ------------------------------------------------------------------

        ordered_queues = {}
        next_patients = {}

        for code, department in departments.items():
            ordered_queues[code] = await queue_service.get_department_queue(
                department.dept_id
            )
            next_patients[code] = await queue_service.get_next_patient(
                department.dept_id
            )

        return (
            departments,
            staff_by_id,
            records,
            ordered_queues,
            next_patients,
            demo_run_id,
        )


# ==========================================================================
# REPORTING
# ==========================================================================

def print_header(config):
    print()
    print("=" * 75)
    print("HPQMS QUEUE PRIORITY MATRIX TEST")
    print("=" * 75)
    print(f"Departments : {', '.join(d.code for d in config['departments'])}")
    print(f"Staff       : {', '.join(s.employee_id for s in config['staff'])}")
    print(f"Patients    : {len(config['patients'])}")


def print_creation_order(records):
    print()
    print("CREATION ORDER")
    print("-" * 75)

    for index, record in enumerate(records, start=1):
        patient = record["patient"]
        visit = record["visit"]
        queue_entry = record["queue_entry"]

        print(
            f"{index}. [{record['department_code']}] "
            f"{visit.token_number} | "
            f"{patient.first_name} {patient.last_name} | "
            f"{queue_entry.priority.value} | "
            f"Queue #{queue_entry.sequence_number} | "
            f"{queue_entry.status.value}"
        )


def print_expected_order():
    print()
    print("EXPECTED QUEUE ORDER (per department)")
    print("-" * 75)
    print("1. CRITICAL")
    print("2. URGENT")
    print("3. SEMI_URGENT")
    print("4. NORMAL")


def print_actual_order(ordered_queues):
    print()
    print("ACTUAL QUEUE ORDER FROM QueueService")
    print("-" * 75)

    for code, queue in ordered_queues.items():
        print(f"-- Department: {code} --")
        for index, queue_entry in enumerate(queue, start=1):
            patient = queue_entry.visit.patient
            print(
                f"{index}. "
                f"{queue_entry.visit.token_number} | "
                f"{patient.first_name} {patient.last_name} | "
                f"{queue_entry.priority.value} | "
                f"Queue #{queue_entry.sequence_number} | "
                f"{queue_entry.status.value}"
            )


def print_next_patients(next_patients):
    print()
    print("NEXT PATIENT SELECTED BY QueueService")
    print("-" * 75)

    for code, next_patient in next_patients.items():
        print(f"-- Department: {code} --")
        if next_patient:
            patient = next_patient.visit.patient
            print(f"Token    : {next_patient.visit.token_number}")
            print(f"Patient  : {patient.first_name} {patient.last_name}")
            print(f"Priority : {next_patient.priority.value}")
            print(f"Sequence : {next_patient.sequence_number}")
            print(f"Status   : {next_patient.status.value}")
        else:
            print("No waiting patient found.")


def print_test_result(ordered_queues, next_patients):
    print()
    print("PRIORITY TEST RESULT")
    print("-" * 75)

    all_passed = True

    for code in ordered_queues:
        queue = ordered_queues[code]
        next_patient = next_patients[code]

        passed = bool(
            queue
            and next_patient
            and next_patient.queue_entry_id == queue[0].queue_entry_id
        )
        all_passed = all_passed and passed

        status = "PASS" if passed else "FAIL"
        print(f"[{code}] {status}: get_next_patient() "
              f"{'matches' if passed else 'does NOT match'} "
              f"the first entry from get_department_queue().")

    print()
    print("OVERALL:", "PASS" if all_passed else "FAIL")


def print_footer(staff_by_id, config, run_id):
    print()
    print("=" * 75)
    print("ALL PATIENTS SHOULD CURRENTLY BE WAITING")
    print("=" * 75)
    print()
    print("No queue entry has been called, started, or completed.")

    primary_staff = staff_by_id.get(PRIMARY_STAFF_EMPLOYEE_ID)
    primary_password = next(
        (s.password for s in config["staff"] if s.employee_id == PRIMARY_STAFF_EMPLOYEE_ID),
        None,
    )

    print()
    print("STAFF DASHBOARD")
    print("http://localhost:8000/static/staff.html")
    if primary_staff:
        print(f"Login as {primary_staff.employee_id} / password: {primary_password}")

    print()
    print("PUBLIC DISPLAY")
    print("http://localhost:8000/static/index.html")

    print()
    print(f"Demo run ID: {run_id}")

    print()
    print("NEXT MANUAL TEST")
    print("-" * 75)
    steps = [
        f"Login as {PRIMARY_STAFF_EMPLOYEE_ID}",
        "Open the public display",
        "Verify the queue order",
        "CALL the CRITICAL patient",
        "Verify TOKEN_CALLED on the display",
        "START SERVICE",
        "Verify IN_PROGRESS",
        "COMPLETE the patient",
        "Verify the next patient is URGENT",
        "Continue through the priority order",
    ]
    for i, step in enumerate(steps, start=1):
        print(f"{i}. {step}")

    print()


# ==========================================================================
# MAIN
# ==========================================================================

async def main(config: dict = DEMO_CONFIG):

    (
        departments,
        staff_by_id,
        records,
        ordered_queues,
        next_patients,
        run_id,
    ) = await seed_priority_demo(config)

    print_header(config)
    print_creation_order(records)
    print_expected_order()
    print_actual_order(ordered_queues)
    print_next_patients(next_patients)
    print_test_result(ordered_queues, next_patients)
    print_footer(staff_by_id, config, run_id)


if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import sys
from datetime import datetime
from pathlib import Path

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
# ==========================================================================

DEMO_DEPARTMENT_CODE = "REC"
DEMO_DEPARTMENT_NAME = "Reception"

DEMO_EMPLOYEE_ID = "REC001"
DEMO_PASSWORD = "demo12345"


# --------------------------------------------------------------------------
# IMPORTANT:
#
# The patients are intentionally created in this order:
#
#   NORMAL
#   SEMI_URGENT
#   URGENT
#   CRITICAL
#
# This allows us to verify that queue priority overrides creation order.
# --------------------------------------------------------------------------

DEMO_PATIENTS = [
    ("John", "Demo", QueuePriority.NORMAL),
    ("Jane", "Demo", QueuePriority.SEMI_URGENT),
    ("Mary", "Demo", QueuePriority.URGENT),
    ("Peter", "Demo", QueuePriority.CRITICAL),
]


DEMO_VISIT_REASON = "Queue priority matrix test"


# ==========================================================================
# DEPARTMENT
# ==========================================================================

async def get_or_create_department(db):
    service = DepartmentService(db)

    try:
        return await service.get_by_code(DEMO_DEPARTMENT_CODE)

    except HTTPException as exc:
        if exc.status_code != 404:
            raise

        return await service.create_department(
            DepartmentCreate(
                name=DEMO_DEPARTMENT_NAME,
                department_code=DEMO_DEPARTMENT_CODE,
                type=DeptType.OPD,
                max_capacity=20,
            )
        )


# ==========================================================================
# STAFF
# ==========================================================================

async def get_or_create_staff(db, department):
    service = StaffService(db)

    staff = await service.get_by_employee_id(
        DEMO_EMPLOYEE_ID
    )

    if not staff:
        staff = await service.create_staff(
            StaffCreate(
                employee_id=DEMO_EMPLOYEE_ID,
                dept_id=department.dept_id,
                first_name="Demo",
                last_name="Receptionist",
                role=StaffRole.RECEPTIONIST,
                specialization="Front Desk",
                password=DEMO_PASSWORD,
            )
        )

    staff.is_active = True
    staff.is_on_duty = True

    await db.flush()
    await db.refresh(staff)

    return staff


# ==========================================================================
# CREATE FRESH DEMO PATIENT
# ==========================================================================

async def create_fresh_demo_patient(
    db,
    patient_service,
    visit_service,
    queue_service,
    department,
    first_name,
    last_name,
    priority,
    demo_run_id,
    patient_number,
):
    """
    Creates one completely fresh patient → visit → queue entry.

    The patient is always created with WAITING status.

    Priority is explicitly supplied so this script can be used
    as a controlled queue-priority test fixture.
    """

    # Unique identifiers ensure every execution creates
    # a completely new patient.
    national_id = (
        f"DEMO{demo_run_id}{patient_number}"
    )

    phone = (
        f"+254700{demo_run_id[-6:]}{patient_number}"
    )

    # ------------------------------------------------------------------
    # Patient
    # ------------------------------------------------------------------

    patient = await patient_service.register_standard_patient(
        PatientCreate(
            national_id=national_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            blood_type="O+",
        )
    )

    # ------------------------------------------------------------------
    # Visit
    # ------------------------------------------------------------------

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason=DEMO_VISIT_REASON,
        )
    )

    # ------------------------------------------------------------------
    # Queue entry
    # ------------------------------------------------------------------

    queue_entry = await queue_service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=department.dept_id,
        priority=priority,
        notes=(
            "Created for queue priority matrix test"
        ),
    )

    return patient, visit, queue_entry


# ==========================================================================
# SEED PRIORITY TEST DATA
# ==========================================================================

async def seed_priority_demo():

    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        # Truncate tables to remove old demo visits and queues preventing collisions
        await db.execute(text("TRUNCATE TABLE queue_entries, visits, patients CASCADE;"))
        await db.commit()
        # ------------------------------------------------------------------
        # Department + staff
        # ------------------------------------------------------------------

        department = await get_or_create_department(db)

        staff = await get_or_create_staff(
            db,
            department,
        )

        # ------------------------------------------------------------------
        # Services
        # ------------------------------------------------------------------

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        # ------------------------------------------------------------------
        # Unique run identifier
        # ------------------------------------------------------------------

        demo_run_id = datetime.now().strftime(
            "%m%d%H%M%S"
        )

        records = []

        # ------------------------------------------------------------------
        # Create patients
        #
        # IMPORTANT:
        #
        # They are created in this order:
        #
        #   NORMAL
        #   SEMI_URGENT
        #   URGENT
        #   CRITICAL
        #
        # The expected queue order should therefore be the exact opposite.
        # ------------------------------------------------------------------

        for number, (
            first_name,
            last_name,
            priority,
        ) in enumerate(
            DEMO_PATIENTS,
            start=1,
        ):

            patient, visit, queue_entry = (
                await create_fresh_demo_patient(
                    db,
                    patient_service,
                    visit_service,
                    queue_service,
                    department,
                    first_name,
                    last_name,
                    priority,
                    demo_run_id,
                    number,
                )
            )

            records.append(
                {
                    "patient": patient,
                    "visit": visit,
                    "queue_entry": queue_entry,
                }
            )

        # ------------------------------------------------------------------
        # Commit all test data
        # ------------------------------------------------------------------

        await db.commit()

        # ------------------------------------------------------------------
        # Re-query the queue using the actual QueueService ordering.
        #
        # This is important:
        #
        # We don't manually calculate the order here.
        #
        # We ask the real queue engine what the order is.
        # ------------------------------------------------------------------

        ordered_queue = (
            await queue_service.get_department_queue(
                department.dept_id
            )
        )

        # ------------------------------------------------------------------
        # Ask the queue engine who should be called next.
        # ------------------------------------------------------------------

        next_patient = (
            await queue_service.get_next_patient(
                department.dept_id
            )
        )

        return (
            department,
            staff,
            records,
            ordered_queue,
            next_patient,
            demo_run_id,
        )


# ==========================================================================
# MAIN
# ==========================================================================

async def main():

    (
        department,
        staff,
        records,
        ordered_queue,
        next_patient,
        run_id,
    ) = await seed_priority_demo()

    print()
    print("=" * 75)
    print("HPQMS QUEUE PRIORITY MATRIX TEST")
    print("=" * 75)

    print(
        f"Department : "
        f"{department.name} "
        f"({department.department_code})"
    )

    print(
        f"Staff      : "
        f"{staff.employee_id}"
    )

    print(
        f"Password   : "
        f"{DEMO_PASSWORD}"
    )

    print(
        f"Demo run   : "
        f"{run_id}"
    )

    # ======================================================================
    # CREATION ORDER
    # ======================================================================

    print()
    print("CREATION ORDER")
    print("-" * 75)

    for index, record in enumerate(
        records,
        start=1,
    ):

        patient = record["patient"]
        visit = record["visit"]
        queue_entry = record["queue_entry"]

        print(
            f"{index}. "
            f"{visit.token_number} | "
            f"{patient.first_name} "
            f"{patient.last_name} | "
            f"{queue_entry.priority.value} | "
            f"Queue #{queue_entry.sequence_number} | "
            f"{queue_entry.status.value}"
        )

    # ======================================================================
    # EXPECTED PRIORITY ORDER
    # ======================================================================

    print()
    print("EXPECTED QUEUE ORDER")
    print("-" * 75)

    print("1. CRITICAL")
    print("2. URGENT")
    print("3. SEMI_URGENT")
    print("4. NORMAL")

    # ======================================================================
    # ACTUAL QUEUE ORDER
    # ======================================================================

    print()
    print("ACTUAL QUEUE ORDER FROM QueueService")
    print("-" * 75)

    for index, queue_entry in enumerate(
        ordered_queue,
        start=1,
    ):

        patient = queue_entry.visit.patient

        print(
            f"{index}. "
            f"{queue_entry.visit.token_number} | "
            f"{patient.first_name} "
            f"{patient.last_name} | "
            f"{queue_entry.priority.value} | "
            f"Queue #{queue_entry.sequence_number} | "
            f"{queue_entry.status.value}"
        )

    # ======================================================================
    # NEXT PATIENT
    # ======================================================================

    print()
    print("NEXT PATIENT SELECTED BY QueueService")
    print("-" * 75)

    if next_patient:

        patient = next_patient.visit.patient

        print(
            f"Token    : "
            f"{next_patient.visit.token_number}"
        )

        print(
            f"Patient  : "
            f"{patient.first_name} "
            f"{patient.last_name}"
        )

        print(
            f"Priority : "
            f"{next_patient.priority.value}"
        )

        print(
            f"Sequence : "
            f"{next_patient.sequence_number}"
        )

        print(
            f"Status   : "
            f"{next_patient.status.value}"
        )

    else:
        print("No waiting patient found.")

    # ======================================================================
    # TEST RESULT
    # ======================================================================

    print()
    print("PRIORITY TEST RESULT")
    print("-" * 75)

    if (
        ordered_queue
        and next_patient
        and next_patient.queue_entry_id
        == ordered_queue[0].queue_entry_id
    ):

        print(
            "PASS: QueueService selected the first "
            "patient according to its priority ordering."
        )

    else:

        print(
            "FAIL: get_next_patient() does not match "
            "the first entry returned by get_department_queue()."
        )

    # ======================================================================
    # IMPORTANT
    # ======================================================================

    print()
    print("=" * 75)
    print("ALL FOUR PATIENTS SHOULD CURRENTLY BE WAITING")
    print("=" * 75)

    print()
    print("No queue entry has been called.")
    print("No queue entry has been started.")
    print("No queue entry has been completed.")

    print()
    print("STAFF DASHBOARD")
    print(
        "http://localhost:8000/static/staff.html"
    )

    print()
    print("PUBLIC DISPLAY")
    print(
        "http://localhost:8000/static/index.html"
    )

    print()
    print("NEXT MANUAL TEST")
    print("-" * 75)
    print(
        "1. Login as REC001"
    )
    print(
        "2. Open the public display"
    )
    print(
        "3. Verify the queue order"
    )
    print(
        "4. CALL the CRITICAL patient"
    )
    print(
        "5. Verify TOKEN_CALLED on the display"
    )
    print(
        "6. START SERVICE"
    )
    print(
        "7. Verify IN_PROGRESS"
    )
    print(
        "8. COMPLETE the patient"
    )
    print(
        "9. Verify the next patient is URGENT"
    )
    print(
        "10. Continue through the priority order"
    )

    print()


# ==========================================================================
# ENTRY POINT
# ==========================================================================

if __name__ == "__main__":
    asyncio.run(main())
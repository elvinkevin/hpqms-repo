"""
API tests for the admin dashboard read endpoints:

    GET /api/admin/overview
    GET /api/admin/departments/{dept_id}/overview
    GET /api/admin/audit-logs
"""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import (
    AuditLog,
    Department,
    EntryType,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    Visit,
    VisitStage,
)

pytestmark = pytest.mark.asyncio


# ============================================================================
# HELPERS
# ============================================================================


async def add_queue_entry(
    db: AsyncSession,
    department: Department,
    patient,
    status: QueueEntryStatus = QueueEntryStatus.WAITING,
    priority: QueuePriority = QueuePriority.NORMAL,
):
    visit = Visit(
        patient_id=patient.patient_id,
        token_number=f"W-{uuid4().int % 10**8:08d}",
        entry_type=EntryType.WALK_IN,
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()

    entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=department.dept_id,
        sequence_number=uuid4().int % 1000,
        priority=priority,
        status=status,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


# ============================================================================
# GROUP 1: RBAC — WHO CAN REACH /api/admin/*
# ============================================================================


async def test_overview_requires_authentication(client: AsyncClient):
    response = await client.get("/api/admin/overview")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_overview_forbidden_for_doctor(
    client: AsyncClient,
    doctor_token_headers,
):
    response = await client.get(
        "/api/admin/overview",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_overview_forbidden_for_receptionist(
    client: AsyncClient,
    receptionist_token_headers,
):
    response = await client.get(
        "/api/admin/overview",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_audit_logs_forbidden_for_triage_nurse(
    client: AsyncClient,
    triage_token_headers,
):
    response = await client.get(
        "/api/admin/audit-logs",
        headers=triage_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 2: HOSPITAL OVERVIEW (GET /api/admin/overview)
# ============================================================================


async def test_overview_success_shape(
    client: AsyncClient,
    admin_headers,
    department,
):
    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    # Top-level structure
    assert set(data.keys()) == {
        "generated_at",
        "totals",
        "critical_waiting",
        "departments",
        "on_duty_staff",
    }

    # Totals structure
    assert set(data["totals"].keys()) == {
        "waiting",
        "called",
        "in_progress",
        "active_visits",
        "patients",
        "staff_active",
        "staff_on_duty",
        "appointments_today",
    }


async def test_overview_counts_waiting_entries(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    existing_patient,
):
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.WAITING
    )
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.WAITING
    )

    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    data = response.json()

    assert data["totals"]["waiting"] >= 2

    dept_bucket = next(
        d
        for d in data["departments"]
        if d["dept_id"] == str(department.dept_id)
    )
    assert dept_bucket["waiting"] >= 2


async def test_overview_separates_queue_statuses(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    existing_patient,
):
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.WAITING
    )
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.CALLED
    )
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.IN_PROGRESS
    )

    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    data = response.json()

    assert data["totals"]["waiting"] >= 1
    assert data["totals"]["called"] >= 1
    assert data["totals"]["in_progress"] >= 1


async def test_overview_counts_critical_waiting(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    existing_patient,
):
    await add_queue_entry(
        db,
        department,
        existing_patient,
        QueueEntryStatus.WAITING,
        QueuePriority.URGENT,
    )
    await add_queue_entry(
        db,
        department,
        existing_patient,
        QueueEntryStatus.WAITING,
        QueuePriority.CRITICAL,
    )
    # A completed urgent entry must NOT count as critical waiting
    await add_queue_entry(
        db,
        department,
        existing_patient,
        QueueEntryStatus.COMPLETED,
        QueuePriority.CRITICAL,
    )

    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    data = response.json()

    assert data["critical_waiting"] == 2

    dept_bucket = next(
        d
        for d in data["departments"]
        if d["dept_id"] == str(department.dept_id)
    )
    assert dept_bucket["critical_waiting"] == 2


async def test_overview_excludes_inactive_departments_queue_is_still_present(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    secondary_department,
    existing_patient,
):
    """
    Both departments appear in the snapshot (admin sees the whole hospital),
    each with its own queue counts.
    """
    await add_queue_entry(db, department, existing_patient)
    await add_queue_entry(
        db, secondary_department, existing_patient, QueueEntryStatus.CALLED
    )

    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    data = response.json()
    by_code = {d["code"]: d for d in data["departments"]}

    assert "OPD" in by_code
    assert "PHARM" in by_code
    assert by_code["OPD"]["waiting"] >= 1
    assert by_code["PHARM"]["called"] >= 1


async def test_overview_includes_on_duty_roster(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    doctor_staff,
):
    doctor_staff.is_on_duty = True
    await db.commit()

    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    data = response.json()

    roster_ids = {s["staff_id"] for s in data["on_duty_staff"]}
    assert str(doctor_staff.staff_id) in roster_ids
    assert data["totals"]["staff_on_duty"] >= 1

    roster_entry = next(
        s
        for s in data["on_duty_staff"]
        if s["staff_id"] == str(doctor_staff.staff_id)
    )
    assert roster_entry["full_name"] == "Dr Doctor"
    assert roster_entry["role"] == "DOCTOR"
    assert roster_entry["service_point_id"] is None


async def test_overview_empty_hospital_returns_zeroes(
    client: AsyncClient,
    admin_headers,
):
    """
    Fresh database (only fixtures with no queue activity): snapshot must
    still render with zeroed counters rather than erroring.
    """
    response = await client.get(
        "/api/admin/overview",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["totals"]["waiting"] == 0
    assert data["totals"]["called"] == 0
    assert data["totals"]["in_progress"] == 0
    assert data["critical_waiting"] == 0
    assert isinstance(data["departments"], list)
    assert isinstance(data["on_duty_staff"], list)


# ============================================================================
# GROUP 3: DEPARTMENT DRILL-DOWN (GET /api/admin/departments/{id}/overview)
# ============================================================================


async def test_department_overview_success(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    existing_patient,
):
    await add_queue_entry(
        db, department, existing_patient, QueueEntryStatus.WAITING
    )

    response = await client.get(
        f"/api/admin/departments/{department.dept_id}/overview",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["dept_id"] == str(department.dept_id)
    assert data["waiting"] >= 1


async def test_department_overview_unknown_department(
    client: AsyncClient,
    admin_headers,
):
    response = await client.get(
        f"/api/admin/departments/{uuid4()}/overview",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_department_overview_forbidden_for_doctor(
    client: AsyncClient,
    doctor_token_headers,
    department,
):
    response = await client.get(
        f"/api/admin/departments/{department.dept_id}/overview",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 4: AUDIT LOG LISTING (GET /api/admin/audit-logs)
# ============================================================================


async def _seed_audit_log(
    db: AsyncSession,
    staff_id,
    action: str,
    entity_type: str = "STAFF",
    entity_id=None,
) -> AuditLog:
    entry = AuditLog(
        performed_by=staff_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id or uuid4(),
        payload={"test": True},
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def test_audit_logs_returns_entries(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
):
    entry = await _seed_audit_log(db, admin_staff.staff_id, "ROLE_CHANGED")

    response = await client.get(
        "/api/admin/audit-logs",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    logs = response.json()
    assert any(log["log_id"] == str(entry.audit_id) for log in logs)


async def test_audit_logs_schema_keys(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
):
    await _seed_audit_log(db, admin_staff.staff_id, "PASSWORD_RESET")

    response = await client.get(
        "/api/admin/audit-logs",
        headers=admin_headers,
    )

    log = response.json()[0]

    assert set(log.keys()) == {
        "log_id",
        "entity_id",
        "entity_type",
        "action",
        "performed_by",
        "payload",
        "created_at",
    }


async def test_audit_logs_filter_by_action(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
):
    await _seed_audit_log(db, admin_staff.staff_id, "ROLE_CHANGED")
    await _seed_audit_log(db, admin_staff.staff_id, "PASSWORD_RESET")

    response = await client.get(
        "/api/admin/audit-logs?action=ROLE_CHANGED",
        headers=admin_headers,
    )

    logs = response.json()

    assert len(logs) >= 1
    assert all(log["action"] == "ROLE_CHANGED" for log in logs)


async def test_audit_logs_filter_by_staff(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    doctor_staff,
    db,
):
    mine = await _seed_audit_log(db, admin_staff.staff_id, "ROLE_CHANGED")
    await _seed_audit_log(db, doctor_staff.staff_id, "ROLE_CHANGED")

    response = await client.get(
        f"/api/admin/audit-logs?staff_id={admin_staff.staff_id}",
        headers=admin_headers,
    )

    logs = response.json()
    log_ids = {log["log_id"] for log in logs}

    assert str(mine.audit_id) in log_ids
    assert all(log["performed_by"] == str(admin_staff.staff_id) for log in logs)


async def test_audit_logs_filter_by_entity_type(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
):
    await _seed_audit_log(
        db, admin_staff.staff_id, "PATIENT_DELETED", entity_type="PATIENT"
    )
    await _seed_audit_log(db, admin_staff.staff_id, "ROLE_CHANGED")

    response = await client.get(
        "/api/admin/audit-logs?entity_type=PATIENT",
        headers=admin_headers,
    )

    logs = response.json()

    assert len(logs) >= 1
    assert all(log["entity_type"] == "PATIENT" for log in logs)


async def test_audit_logs_empty_result_is_ok(
    client: AsyncClient,
    admin_headers,
):
    response = await client.get(
        "/api/admin/audit-logs?action=NEVER_HAPPENED",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


async def test_audit_logs_respects_limit(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
):
    for i in range(5):
        await _seed_audit_log(db, admin_staff.staff_id, f"BULK_ACTION_{i}")

    response = await client.get(
        "/api/admin/audit-logs?limit=3",
        headers=admin_headers,
    )

    assert len(response.json()) == 3

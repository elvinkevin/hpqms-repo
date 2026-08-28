# backend/tests/integration/test_staff_flow.py

import pytest
from uuid import uuid4

from fastapi import HTTPException, status

from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import StaffCreate, StaffUpdate
from app.domain.services.staff_service import StaffService


# ============================================================
# STAFF CREATION
# ============================================================

class TestStaffCreation:

    @pytest.mark.asyncio
    async def test_create_staff_success(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP001",
                first_name="John",
                last_name="Kamau",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        assert staff.staff_id is not None
        assert staff.employee_id == "EMP001"
        assert staff.first_name == "John"
        assert staff.last_name == "Kamau"
        assert staff.dept_id == routing_departments["reception"].dept_id
        assert staff.role == StaffRole.RECEPTIONIST

        # Password must never be stored as plaintext.
        assert staff.hashed_password != "SecurePassword123!"
        assert staff.hashed_password is not None


    @pytest.mark.asyncio
    async def test_duplicate_employee_id_rejected(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        payload = StaffCreate(
            employee_id="EMP002",
            first_name="Jane",
            last_name="Doe",
            dept_id=routing_departments["reception"].dept_id,
            role=StaffRole.RECEPTIONIST,
            specialization=None,
            password="SecurePassword123!",
        )

        await service.create_staff(payload)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_staff(payload)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail == "Employee ID already exists."


# ============================================================
# STAFF RETRIEVAL
# ============================================================

class TestStaffRetrieval:

    @pytest.mark.asyncio
    async def test_get_staff_by_id(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        created = await service.create_staff(
            StaffCreate(
                employee_id="EMP003",
                first_name="Mary",
                last_name="Wanjiku",
                dept_id=routing_departments["triage"].dept_id,
                role=StaffRole.NURSE,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        staff = await service.get_by_id(created.staff_id)

        assert staff.staff_id == created.staff_id
        assert staff.employee_id == "EMP003"


    @pytest.mark.asyncio
    async def test_get_staff_by_id_not_found(self, db):
        service = StaffService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_by_id(uuid4())

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Staff member not found."


    @pytest.mark.asyncio
    async def test_get_by_employee_id(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        created = await service.create_staff(
            StaffCreate(
                employee_id="EMP004",
                first_name="Peter",
                last_name="Otieno",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        staff = await service.get_by_employee_id("EMP004")

        assert staff is not None
        assert staff.staff_id == created.staff_id


    @pytest.mark.asyncio
    async def test_get_by_employee_id_returns_none_when_missing(
        self,
        db,
    ):
        service = StaffService(db)

        staff = await service.get_by_employee_id("DOES-NOT-EXIST")

        assert staff is None


# ============================================================
# DEPARTMENT / ROLE FILTERING
# ============================================================

class TestStaffFiltering:

    @pytest.mark.asyncio
    async def test_get_staff_by_department(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        reception_id = routing_departments["reception"].dept_id
        triage_id = routing_departments["triage"].dept_id

        reception_staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP005",
                first_name="Alice",
                last_name="Reception",
                dept_id=reception_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.create_staff(
            StaffCreate(
                employee_id="EMP006",
                first_name="Brian",
                last_name="Triage",
                dept_id=triage_id,
                role=StaffRole.NURSE,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        results = await service.get_by_department(reception_id)

        assert len(results) == 1
        assert results[0].staff_id == reception_staff.staff_id
        assert results[0].dept_id == reception_id


    @pytest.mark.asyncio
    async def test_get_staff_by_role(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        nurse = await service.create_staff(
            StaffCreate(
                employee_id="EMP007",
                first_name="Sarah",
                last_name="Nurse",
                dept_id=routing_departments["triage"].dept_id,
                role=StaffRole.NURSE,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.create_staff(
            StaffCreate(
                employee_id="EMP008",
                first_name="David",
                last_name="Doctor",
                dept_id=routing_departments["triage"].dept_id,
                role=StaffRole.DOCTOR,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        results = await service.get_by_role(StaffRole.NURSE)

        assert any(
            staff.staff_id == nurse.staff_id
            for staff in results
        )

        assert all(
            staff.role == StaffRole.NURSE
            for staff in results
        )


    @pytest.mark.asyncio
    async def test_get_by_department_excludes_inactive_staff(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP009",
                first_name="Inactive",
                last_name="Staff",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.deactivate_staff(staff.staff_id)

        results = await service.get_by_department(
            routing_departments["reception"].dept_id
        )

        assert all(
            member.staff_id != staff.staff_id
            for member in results
        )


# ============================================================
# SEARCH
# ============================================================

class TestStaffSearch:

    @pytest.mark.asyncio
    async def test_search_staff_by_name(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP010",
                first_name="Elizabeth",
                last_name="Mwangi",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        results = await service.search_staff("Elizabeth")

        assert any(
            result.staff_id == staff.staff_id
            for result in results
        )


    @pytest.mark.asyncio
    async def test_search_staff_by_employee_id(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP011",
                first_name="Kevin",
                last_name="Otieno",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        results = await service.search_staff("EMP011")

        assert any(
            result.staff_id == staff.staff_id
            for result in results
        )


# ============================================================
# DUTY STATUS
# ============================================================

class TestStaffDutyStatus:

    @pytest.mark.asyncio
    async def test_staff_can_check_in(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP012",
                first_name="Check",
                last_name="In",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        assert staff.is_on_duty is False

        checked_in = await service.check_in(staff.staff_id)

        assert checked_in.is_on_duty is True


    @pytest.mark.asyncio
    async def test_staff_cannot_check_in_twice(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP013",
                first_name="Double",
                last_name="CheckIn",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.check_in(staff.staff_id)

        with pytest.raises(HTTPException) as exc_info:
            await service.check_in(staff.staff_id)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail == "Staff member is already checked in."


    @pytest.mark.asyncio
    async def test_staff_can_check_out(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP014",
                first_name="Check",
                last_name="Out",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.check_in(staff.staff_id)

        checked_out = await service.check_out(staff.staff_id)

        assert checked_out.is_on_duty is False


    @pytest.mark.asyncio
    async def test_staff_cannot_check_out_twice(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP015",
                first_name="Double",
                last_name="CheckOut",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.check_out(staff.staff_id)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.detail == "Staff member is already checked out."


    @pytest.mark.asyncio
    async def test_inactive_staff_cannot_check_in(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP016",
                first_name="Inactive",
                last_name="Worker",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.deactivate_staff(staff.staff_id)

        with pytest.raises(HTTPException) as exc_info:
            await service.check_in(staff.staff_id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Inactive staff account."


# ============================================================
# ACCOUNT STATUS
# ============================================================

class TestStaffAccountStatus:

    @pytest.mark.asyncio
    async def test_deactivate_staff(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP017",
                first_name="Deactivate",
                last_name="Staff",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.check_in(staff.staff_id)

        deactivated = await service.deactivate_staff(
            staff.staff_id
        )

        assert deactivated.is_active is False
        assert deactivated.is_on_duty is False


    @pytest.mark.asyncio
    async def test_activate_staff(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP018",
                first_name="Activate",
                last_name="Staff",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        await service.deactivate_staff(staff.staff_id)

        activated = await service.activate_staff(
            staff.staff_id
        )

        assert activated.is_active is True


# ============================================================
# STAFF UPDATE
# ============================================================

class TestStaffUpdate:

    @pytest.mark.asyncio
    async def test_update_staff(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP019",
                first_name="Original",
                last_name="Name",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        updated = await service.update_staff(
            staff.staff_id,
            StaffUpdate(
                first_name="Updated",
                last_name="Staff",
            ),
        )

        assert updated.first_name == "Updated"
        assert updated.last_name == "Staff"


# ============================================================
# STAFF STATUS / ME
# ============================================================

class TestStaffStatus:

    @pytest.mark.asyncio
    async def test_get_my_status(
        self,
        db,
        routing_departments,
    ):
        service = StaffService(db)

        staff = await service.create_staff(
            StaffCreate(
                employee_id="EMP020",
                first_name="Status",
                last_name="Staff",
                dept_id=routing_departments["reception"].dept_id,
                role=StaffRole.RECEPTIONIST,
                specialization=None,
                password="SecurePassword123!",
            )
        )

        status_data = await service.get_my_status(
            staff.staff_id
        )

        assert status_data.staff_id == staff.staff_id
        assert status_data.employee_id == "EMP020"
        assert status_data.full_name == "Status Staff"
        assert status_data.role == StaffRole.RECEPTIONIST
        assert status_data.dept_id == routing_departments["reception"].dept_id
        assert status_data.is_on_duty is False
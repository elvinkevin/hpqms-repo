import uuid

import pytest
from fastapi import HTTPException


from app.core.security import verify_password
from app.domain.models.models import (
    Department,
    DeptType,
    Staff,
    StaffRole,
)
from app.domain.schemas.schemas import (
    StaffCreate,
    StaffUpdate,
)
from app.domain.services.staff_service import StaffService


#--------------------------------
# Department Fixture
#---------------------------------
@pytest.fixture
async def department(db):

    department = Department(
        name="Reception",
        department_code="REC",
        type=DeptType.OPD,
    )

    db.add(department)

    await db.commit()
    await db.refresh(department)

    return department


#---------------------------------------------
# test 1 register patient
#-----------------------------------------------
async def test_register_staff(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    assert staff.employee_id == "EMP001"
    assert staff.first_name == "Kevin"
    assert staff.role == StaffRole.RECEPTIONIST

    # default states
    assert staff.is_active is True
    assert staff.is_on_duty is False

    # password should be hashed
    assert staff.hashed_password != "Password123!"
    assert verify_password(
        "Password123!",
        staff.hashed_password,
    )



#----------------------------------------------
# test 2 test duplicate employee ids
#----------------------------------------------
async def test_duplicate_employee_id(db, department):

    service = StaffService(db)

    payload = StaffCreate(
        employee_id="EMP001",
        dept_id=department.dept_id,
        first_name="Kevin",
        last_name="Axel",
        role=StaffRole.RECEPTIONIST,
        password="Password123!",
    )

    await service.create_staff(payload)

    with pytest.raises(HTTPException):

        await service.create_staff(payload)

#----------------------------------------------------------
# test 3 test unknown departments
#----------------------------------------------------------
async def test_unknown_department_returns_404(db):

    service = StaffService(db)

    with pytest.raises(HTTPException):

        await service.create_staff(

            StaffCreate(
                employee_id="EMP001",
                dept_id=uuid.uuid4(),
                first_name="Kevin",
                last_name="Axel",
                role=StaffRole.RECEPTIONIST,
                password="Password123!",
            )

        )


#-------------------------------------------
# test 4 get staff by id
#--------------------------------------------

async def test_get_staff_by_id(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    result = await service.get_by_id(staff.staff_id)

    assert result.staff_id == staff.staff_id
    assert result.employee_id == "EMP001"


#--------------------------------------
# test 5 test unknown staff
#-------------------------------------

async def test_unknown_staff_returns_404(db):

    service = StaffService(db)

    with pytest.raises(HTTPException):

        await service.get_by_id(uuid.uuid4())



#----------------------------------------------
# test 6 get staff by employee id
#----------------------------------------------

async def test_get_staff_by_employee_id(db, department):

    service = StaffService(db)

    await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    staff = await service.get_by_employee_id("EMP001")

    assert staff is not None
    assert staff.employee_id == "EMP001"

#----------------------------------------------
# test 7 get all staff
#---------------------------------------------

async def test_get_all_staff(db, department):

    service = StaffService(db)

    await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    await service.create_staff(
        StaffCreate(
            employee_id="EMP002",
            dept_id=department.dept_id,
            first_name="John",
            last_name="Doe",
            role=StaffRole.NURSE,
            password="Password123!",
        )
    )

    staff = await service.get_all_staff()

    assert len(staff) == 2


#----------------------------------------------------
# test 8 get department staff
#--------------------------------------------------

async def test_get_department_staff(db, department):

    service = StaffService(db)

    await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    result = await service.get_by_department(
        department.dept_id
    )

    assert len(result) == 1
    assert result[0].employee_id == "EMP001"

#------------------------------------------
# test 9 update staff details 
#------------------------------------------

async def test_update_staff(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    updated = await service.update_staff(
        staff.staff_id,
        StaffUpdate(
            first_name="John",
            last_name="Doe",
        ),
    )

    assert updated.first_name == "John"
    assert updated.last_name == "Doe"


#-------------------------------------
# test 10 activate staff
#-------------------------------------

async def test_activate_staff(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    await service.deactivate_staff(staff.staff_id)

    activated = await service.activate_staff(staff.staff_id)

    assert activated.is_active is True

#-----------------------------------------------
# test 11 deactivate staff
#------------------------------------------------


async def test_deactivate_staff(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    result = await service.deactivate_staff(staff.staff_id)

    assert result.is_active is False

#-------------------------------
# test 12 clock in
#----------------------------------

async def test_clock_in(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    result = await service.check_in(staff.staff_id)

    assert result.is_on_duty is True

#--------------------------------
# test 13 clock out
#---------------------------------

async def test_clock_out(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    await service.check_in(staff.staff_id)

    result = await service.check_out(staff.staff_id)

    assert result.is_on_duty is False

#----------------------------------------
# test 14 staff exists 
#-----------------------------------------
# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------


async def test_staff_exists(db, department):

    service = StaffService(db)

    staff = await service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.RECEPTIONIST,
            password="Password123!",
        )
    )

    exists = await service.staff_exists(staff.staff_id)

    assert exists is True



#-----------------------------------------
# test 15 staff does not exist
#-----------------------------------------


async def test_staff_does_not_exist(db):

    service = StaffService(db)

    exists = await service.staff_exists(uuid.uuid4())

    assert exists is False
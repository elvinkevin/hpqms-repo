import uuid

import pytest

from fastapi import HTTPException

from app.domain.models.models import (
    Department,
    DeptType,
)

from app.domain.services.departments_service import DepartmentService

#------------------------------------
# Test 1 get departments by id
#-------------------------------------
async def test_get_department_by_id(db):
    department = Department(
        name="Reception",
        department_code="REC",
        type=DeptType.OPD,
    )

    db.add(department)

    await db.commit()

    service = DepartmentService(db)

    result = await service.get_by_id(
        department.dept_id
    )

    assert result.name == "Reception"

#-----------------------------------------
# Test 2 test non-existent deartments
#----------------------------------------
async def test_unknown_department_returns_404(db):

    service = DepartmentService(db)

    with pytest.raises(HTTPException):

        await service.get_by_id(
            uuid.uuid4()
        )


#------------------------------------------------
# test 3 get department by code
#----------------------------------------------
async def test_get_department_by_code(db):

    department = Department(
        name="Laboratory",
        department_code="LAB",
        type=DeptType.OPD,
    )

    db.add(department)

    await db.commit()

    service = DepartmentService(db)

    result = await service.get_by_code("LAB")

    assert result.department_code == "LAB"


#------------------------------------------------
# Test 4 get all active departments
#---------------------------------------------
async def test_get_active_departments(db):

    db.add_all([
        Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            is_active=True,
        ),
        Department(
            name="Archive",
            department_code="ARC",
            type=DeptType.OPD,
            is_active=False,
        ),
    ])

    await db.commit()

    service = DepartmentService(db)

    departments = await service.get_active_departments()

    assert len(departments) == 1
    assert departments[0].department_code == "REC"


#-----------------------------------------------
# Test 5 get all departments
#-------------------------------------------------
async def test_get_all_departments(db):

    db.add_all([
        Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
        ),
        Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
        ),
    ])

    await db.commit()

    service = DepartmentService(db)

    departments = await service.get_all()

    assert len(departments) == 2


#-------------------------------------------
# Test 6 check if departments exists
#-------------------------------------------
async def test_department_exists(db):

    department = Department(
        name="Radiology",
        department_code="RAD",
        type=DeptType.OPD,
    )

    db.add(department)

    await db.commit()

    service = DepartmentService(db)

    assert await service.department_exists(
        department.dept_id
    )


#-------------------------------------------
#Test 7 Test if department does not exits
#------------------------------------------
async def test_department_does_not_exist(db):

    service = DepartmentService(db)

    assert not await service.department_exists(
        uuid.uuid4()
    )
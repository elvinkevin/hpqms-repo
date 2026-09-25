import pytest

from fastapi import HTTPException

from app.domain.models.models import Department, DeptType, StaffRole
from app.domain.schemas.schemas import (
    LoginRequest,
    ChangePasswordRequest,
    StaffCreate,
)
from app.domain.services.auth_service import AuthService
from app.domain.services.staff_service import StaffService

@pytest.fixture
async def staff(db, department):

    staff_service = StaffService(db)

    staff = await staff_service.create_staff(
        StaffCreate(
            employee_id="EMP001",
            dept_id=department.dept_id,
            first_name="Kevin",
            last_name="Axel",
            role=StaffRole.ADMIN,
            password="Password123!",
        )
    )
    # create_staff flags new accounts for a first-login password change;
    # these tests exercise the normal login/change-password paths.
    staff.requires_password_change = False
    await db.commit()
    return staff

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
#--------------------------------------
# Test 1 — Successful Login
#--------------------------------------

async def test_login_success(db, staff):

    auth = AuthService(db)

    response = await auth.login(
        LoginRequest(
            employee_id="EMP001",
            password="Password123!",
        )
    )

    assert response.access_token is not None
    assert response.refresh_token is not None
    assert response.staff.employee_id == "EMP001"


#-----------------------------------------
# Test 2 — Wrong Password
#------------------------------------------

async def test_login_wrong_password(db, staff):

    auth = AuthService(db)

    with pytest.raises(HTTPException) as exc:

        await auth.login(
            LoginRequest(
                employee_id="EMP001",
                password="WrongPassword",
            )
        )

    assert exc.value.status_code == 401

#---------------------------------------
# Test 3 — Unknown Employee
#---------------------------------------

async def test_login_unknown_employee(db):

    auth = AuthService(db)

    with pytest.raises(HTTPException) as exc:

        await auth.login(
            LoginRequest(
                employee_id="EMP999",
                password="Password123!",
            )
        )

    assert exc.value.status_code == 401

#----------------------------------------
# Test 4 — Inactive Staff Cannot Login
#-----------------------------------------

async def test_login_inactive_staff(db, staff):

    staff.is_active = False

    await db.commit()

    auth = AuthService(db)

    with pytest.raises(HTTPException) as exc:

        await auth.login(
            LoginRequest(
                employee_id="EMP001",
                password="Password123!",
            )
        )

    assert exc.value.status_code == 401


#--------------------------------------------
#Test 5 — Refresh Access Token
#--------------------------------------------

async def test_refresh_access_token(db, staff):

    auth = AuthService(db)

    login = await auth.login(
        LoginRequest(
            employee_id="EMP001",
            password="Password123!",
        )
    )

    response = await auth.refresh_access_token(
        login.refresh_token
    )

    assert response.access_token is not None

#----------------------------------------
# Test 6 — Invalid Refresh Token
#----------------------------------------

async def test_invalid_refresh_token(db):

    auth = AuthService(db)

    with pytest.raises(HTTPException) as exc:

        await auth.refresh_access_token(
            "this-is-not-a-valid-token"
        )

    assert exc.value.status_code == 401


#-----------------------------------------
# Test 7 — Change Password
#------------------------------------------

async def test_change_password(db, staff):

    auth = AuthService(db)

    await auth.change_password(
        staff.staff_id,
        ChangePasswordRequest(
            current_password="Password123!",
            new_password="NewPassword123!",
        )
    )

    login = await auth.login(
        LoginRequest(
            employee_id="EMP001",
            password="NewPassword123!",
        )
    )

    assert login.access_token is not None


#--------------------------------------------
# Test 8 — Wrong Current Password
#--------------------------------------------

async def test_change_password_wrong_current(db, staff):

    auth = AuthService(db)

    with pytest.raises(HTTPException) as exc:

        await auth.change_password(
            staff.staff_id,
            ChangePasswordRequest(
                current_password="WrongPassword",
                new_password="NewPassword123!",
            )
        )

    assert exc.value.status_code == 400


#-------------------------------------------------------
# Test 9 — Old Password No Longer Works
#--------------------------------------------------------

async def test_old_password_fails_after_change(db, staff):

    auth = AuthService(db)

    await auth.change_password(
        staff.staff_id,
        ChangePasswordRequest(
            current_password="Password123!",
            new_password="NewPassword123!",
        )
    )

    with pytest.raises(HTTPException):

        await auth.login(
            LoginRequest(
                employee_id="EMP001",
                password="Password123!",
            )
        )


#--------------------------------------------------
# Test 10 — New Password Works
#---------------------------------------------

async def test_new_password_succeeds(db, staff):

    auth = AuthService(db)

    await auth.change_password(
        staff.staff_id,
        ChangePasswordRequest(
            current_password="Password123!",
            new_password="NewPassword123!",
        )
    )

    login = await auth.login(
        LoginRequest(
            employee_id="EMP001",
            password="NewPassword123!",
        )
    )

    assert login.access_token is not None

#-----------------------------------------------
# Test 11 — Role Guard Allows Admin
#---------------------------------------------------

async def test_require_role_allows_admin(staff):

    from app.domain.services.auth_service import require_role

    current_user = type(
        "MockUser",
        (),
        {"role": StaffRole.ADMIN},
    )()

    guard = require_role(StaffRole.ADMIN)

    result = await guard(current_user)

    assert result.role == StaffRole.ADMIN


#---------------------------------------
# Test 12 — Role Guard Rejects User
#----------------------------------------


async def test_require_role_rejects_receptionist():

    from app.domain.services.auth_service import require_role

    current_user = type(
        "MockUser",
        (),
        {"role": StaffRole.RECEPTIONIST},
    )()

    guard = require_role(StaffRole.ADMIN)

    with pytest.raises(HTTPException):

        await guard(current_user)
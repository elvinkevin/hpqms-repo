
# import pytest
# from uuid import uuid4

# from fastapi import HTTPException, status

# from app.domain.schemas.schemas import (
#     DepartmentCreate,
#     DepartmentUpdate,
# )
# from app.domain.services.departments_service import DepartmentService


# # ============================================================
# # DEPARTMENT CREATION
# # ============================================================

# class TestDepartmentCreation:

#     @pytest.mark.asyncio
#     async def test_create_department_success(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="CARDIOLOGY",
#                 name="Cardiology",
#             )
#         )

#         assert department.dept_id is not None
#         assert department.department_code == "CARDIOLOGY"
#         assert department.name == "Cardiology"
#         assert department.is_active is True


#     @pytest.mark.asyncio
#     async def test_create_department_normalizes_code_and_name(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="  cardio  ",
#                 name="  Cardiology  ",
#             )
#         )

#         assert department.department_code == "CARDIO"
#         assert department.name == "Cardiology"


#     @pytest.mark.asyncio
#     async def test_create_department_duplicate_code_rejected(self, db):
#         service = DepartmentService(db)

#         await service.create_department(
#             DepartmentCreate(
#                 department_code="CARDIOLOGY",
#                 name="Cardiology",
#             )
#         )

#         with pytest.raises(HTTPException) as exc_info:
#             await service.create_department(
#                 DepartmentCreate(
#                     department_code="CARDIOLOGY",
#                     name="Another Cardiology",
#                 )
#             )

#         assert exc_info.value.status_code == status.HTTP_409_CONFLICT
#         assert exc_info.value.detail == "Department code already exists."


# # ============================================================
# # DEPARTMENT LOOKUPS
# # ============================================================

# class TestDepartmentLookup:

#     @pytest.mark.asyncio
#     async def test_get_department_by_id(self, db):
#         service = DepartmentService(db)

#         created = await service.create_department(
#             DepartmentCreate(
#                 department_code="RADIOLOGY",
#                 name="Radiology",
#             )
#         )

#         found = await service.get_by_id(created.dept_id)

#         assert found.dept_id == created.dept_id
#         assert found.department_code == "RADIOLOGY"


#     @pytest.mark.asyncio
#     async def test_get_department_by_id_not_found(self, db):
#         service = DepartmentService(db)

#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_by_id(uuid4())

#         assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
#         assert exc_info.value.detail == "Department not found."


#     @pytest.mark.asyncio
#     async def test_get_department_by_code_is_case_insensitive(self, db):
#         service = DepartmentService(db)

#         created = await service.create_department(
#             DepartmentCreate(
#                 department_code="EMERGENCY",
#                 name="Emergency Department",
#             )
#         )

#         found = await service.get_by_code("emergency")

#         assert found.dept_id == created.dept_id
#         assert found.department_code == "EMERGENCY"


#     @pytest.mark.asyncio
#     async def test_get_department_by_code_not_found(self, db):
#         service = DepartmentService(db)

#         with pytest.raises(HTTPException) as exc_info:
#             await service.get_by_code("DOES_NOT_EXIST")

#         assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
#         assert "Department 'DOES_NOT_EXIST' not found." in exc_info.value.detail


# # ============================================================
# # DEPARTMENT LISTING
# # ============================================================

# class TestDepartmentListing:

#     @pytest.mark.asyncio
#     async def test_get_all_departments(self, db):
#         service = DepartmentService(db)

#         await service.create_department(
#             DepartmentCreate(
#                 department_code="CARDIO",
#                 name="Z Cardiology",
#             )
#         )

#         await service.create_department(
#             DepartmentCreate(
#                 department_code="RADIO",
#                 name="A Radiology",
#             )
#         )

#         departments = await service.get_all()

#         assert len(departments) == 2
#         assert departments[0].name == "A Radiology"
#         assert departments[1].name == "Z Cardiology"


#     @pytest.mark.asyncio
#     async def test_get_active_departments_excludes_inactive(
#         self,
#         db,
#     ):
#         service = DepartmentService(db)

#         active = await service.create_department(
#             DepartmentCreate(
#                 department_code="ACTIVE",
#                 name="Active Department",
#             )
#         )

#         inactive = await service.create_department(
#             DepartmentCreate(
#                 department_code="INACTIVE",
#                 name="Inactive Department",
#             )
#         )

#         await service.deactivate_department(inactive.dept_id)

#         departments = await service.get_active_departments()

#         dept_ids = {
#             department.dept_id
#             for department in departments
#         }

#         assert active.dept_id in dept_ids
#         assert inactive.dept_id not in dept_ids


# # ============================================================
# # EXISTENCE CHECK
# # ============================================================

# class TestDepartmentExistence:

#     @pytest.mark.asyncio
#     async def test_department_exists_returns_true(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="LAB",
#                 name="Laboratory",
#             )
#         )

#         exists = await service.department_exists(
#             department.dept_id
#         )

#         assert exists is True


#     @pytest.mark.asyncio
#     async def test_department_exists_returns_false_for_unknown_id(self, db):
#         service = DepartmentService(db)

#         exists = await service.department_exists(uuid4())

#         assert exists is False


# # ============================================================
# # DEPARTMENT UPDATE
# # ============================================================

# class TestDepartmentUpdate:

#     @pytest.mark.asyncio
#     async def test_update_department_name(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="OPD",
#                 name="Outpatient",
#             )
#         )

#         updated = await service.update_department(
#             department.dept_id,
#             DepartmentUpdate(
#                 name="Outpatient Department",
#             ),
#         )

#         assert updated.dept_id == department.dept_id
#         assert updated.name == "Outpatient Department"
#         assert updated.department_code == "OPD"


#     @pytest.mark.asyncio
#     async def test_update_department_code_normalizes_to_uppercase(
#         self,
#         db,
#     ):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="OPD",
#                 name="Outpatient",
#             )
#         )

#         updated = await service.update_department(
#             department.dept_id,
#             DepartmentUpdate(
#                 department_code="outpatient",
#             ),
#         )

#         assert updated.department_code == "OUTPATIENT"


# # ============================================================
# # DEPARTMENT ACTIVATION / DEACTIVATION
# # ============================================================

# class TestDepartmentActivation:

#     @pytest.mark.asyncio
#     async def test_deactivate_department(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="MATERNITY",
#                 name="Maternity",
#             )
#         )

#         assert department.is_active is True

#         deactivated = await service.deactivate_department(
#             department.dept_id
#         )

#         assert deactivated.is_active is False


#     @pytest.mark.asyncio
#     async def test_activate_department(self, db):
#         service = DepartmentService(db)

#         department = await service.create_department(
#             DepartmentCreate(
#                 department_code="MATERNITY",
#                 name="Maternity",
#             )
#         )

#         await service.deactivate_department(
#             department.dept_id
#         )

#         activated = await service.activate_department(
#             department.dept_id
#         )

#         assert activated.is_active is True


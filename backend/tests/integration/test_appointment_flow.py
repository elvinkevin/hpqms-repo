# import pytest

# from fastapi import HTTPException, status

# from app.domain.models.models import (
#     EntryType,
#     QueueEntryStatus,
#     QueuePriority,
#     VisitStage,
# )

# from app.domain.schemas.schemas import (
#     PatientCreate,
#     VisitCreate,
# )

# from app.domain.services.patient_service import PatientService
# from app.domain.services.visit_service import VisitService
# from app.domain.services.routing_service import RoutingService


# # ======================================================================
# # APPOINTMENT ARRIVAL
# # ======================================================================

# class TestAppointmentArrival:
#     """
#     Patients with scheduled appointments should bypass Reception
#     and be routed directly to Triage.
#     """

#     @pytest.mark.asyncio
#     async def test_appointment_patient_registration(
#         self,
#         db,
#     ):
#         """
#         Appointment patient arrives.

#         Registration
#               ↓
#         Appointment Visit
#         """

#         patient_service = PatientService(db)
#         visit_service = VisitService(db)

#         patient = await patient_service.register_standard_patient(
#             PatientCreate(
#                 first_name="Alice",
#                 last_name="Mwangi",
#                 national_id="12345678",
#                 phone="+254700111111",
#                 gender="FEMALE",
#                 date_of_birth="1996-05-12",
#             )
#         )

#         visit = await visit_service.start_visit(
#             VisitCreate(
#                 patient_id=patient.patient_id,
#                 entry_type=EntryType.APPOINTMENT,
#                 visit_reason="Scheduled Consultation",
#             )
#         )

#         assert patient.registration_status.name == "COMPLETE"

#         assert visit.patient_id == patient.patient_id
#         assert visit.stage == VisitStage.ACTIVE
#         assert visit.entry_type == EntryType.APPOINTMENT


# # ======================================================================
# # APPOINTMENT ROUTING
# # ======================================================================

# class TestAppointmentRouting:

#     @pytest.mark.asyncio
#     async def test_appointment_patient_routed_to_triage(
#         self,
#         db,
#         routing_departments,
#     ):
#         """
#         Appointment patients bypass Reception.
#         """

#         patient_service = PatientService(db)
#         visit_service = VisitService(db)
#         routing_service = RoutingService(db)

#         patient = await patient_service.register_standard_patient(
#             PatientCreate(
#                 first_name="Peter",
#                 last_name="Otieno",
#                 national_id="87654321",
#                 phone="+254711111111",
#                 gender="MALE",
#                 date_of_birth="1994-01-20",
#             )
#         )

#         visit = await visit_service.start_visit(
#             VisitCreate(
#                 patient_id=patient.patient_id,
#                 entry_type=EntryType.APPOINTMENT,
#                 visit_reason="Review Clinic",
#             )
#         )

#         queue_entry = await routing_service.dispatch_initial_kiosk_route(
#             visit.visit_id
#         )

#         await db.refresh(visit)

#         assert (
#             queue_entry.dept_id
#             == routing_departments["triage"].dept_id
#         )

#         assert (
#             queue_entry.dept_id
#             != routing_departments["reception"].dept_id
#         )

#         assert queue_entry.status == QueueEntryStatus.WAITING
#         assert queue_entry.priority == QueuePriority.NORMAL

#         assert visit.current_queue_entry_id == queue_entry.queue_entry_id

# class TestAppointmentQueueProgression:

#     @pytest.mark.asyncio
#     async def test_appointment_queue_progression(
#         self,
#         db,
#         routing_departments,
#     ):
#         """
#         WAITING
#             ↓
#         CALLED
#             ↓
#         IN_PROGRESS
#             ↓
#         COMPLETED
#         """

#         patient_service = PatientService(db)
#         visit_service = VisitService(db)
#         routing_service = RoutingService(db)

#         patient = await patient_service.register_standard_patient(
#             PatientCreate(
#                 first_name="Mary",
#                 last_name="Kimani",
#                 national_id="44445555",
#                 phone="+254722222222",
#                 gender="FEMALE",
#                 date_of_birth="1990-08-01",
#             )
#         )

#         visit = await visit_service.start_visit(
#             VisitCreate(
#                 patient_id=patient.patient_id,
#                 entry_type=EntryType.APPOINTMENT,
#                 visit_reason="Hypertension Review",
#             )
#         )

#         queue = await routing_service.dispatch_initial_kiosk_route(
#             visit.visit_id
#         )

#         assert queue.status == QueueEntryStatus.WAITING

#         queue = await routing_service.call_queue_entry(queue.queue_entry_id)
#         assert queue.status == QueueEntryStatus.CALLED

#         queue = await routing_service.start_queue_entry(queue.queue_entry_id)
#         assert queue.status == QueueEntryStatus.IN_PROGRESS

#         queue = await routing_service.complete_queue_entry(queue.queue_entry_id)
#         assert queue.status == QueueEntryStatus.COMPLETED

# class TestAppointmentCompletion:

#     @pytest.mark.asyncio
#     async def test_appointment_visit_completion(
#         self,
#         db,
#         routing_departments,
#     ):
#         """
#         Appointment completed successfully.
#         """

#         patient_service = PatientService(db)
#         visit_service = VisitService(db)
#         routing_service = RoutingService(db)

#         patient = await patient_service.register_standard_patient(
#             PatientCreate(
#                 first_name="Kevin",
#                 last_name="Njoroge",
#                 national_id="55667788",
#                 phone="+254733333333",
#                 gender="MALE",
#                 date_of_birth="1992-07-14",
#             )
#         )

#         visit = await visit_service.start_visit(
#             VisitCreate(
#                 patient_id=patient.patient_id,
#                 entry_type=EntryType.APPOINTMENT,
#                 visit_reason="Dermatology Clinic",
#             )
#         )

#         queue = await routing_service.dispatch_initial_kiosk_route(
#             visit.visit_id
#         )

#         await routing_service.call_queue_entry(queue.queue_entry_id)
#         await routing_service.start_queue_entry(queue.queue_entry_id)
#         await routing_service.complete_queue_entry(queue.queue_entry_id)

#         visit = await visit_service.complete_visit(visit.visit_id)

#         assert visit.stage == VisitStage.COMPLETED
#         assert visit.completed_at is not None

# class TestDuplicateAppointmentRejection:

#     @pytest.mark.asyncio
#     async def test_duplicate_appointment_visit_rejected(
#         self,
#         db,
#     ):
#         """
#         A patient cannot have two active appointment visits.
#         """

#         patient_service = PatientService(db)
#         visit_service = VisitService(db)

#         patient = await patient_service.register_standard_patient(
#             PatientCreate(
#                 first_name="James",
#                 last_name="Kiptoo",
#                 national_id="99887766",
#                 phone="+254744444444",
#                 gender="MALE",
#                 date_of_birth="1989-06-18",
#             )
#         )

#         await visit_service.start_visit(
#             VisitCreate(
#                 patient_id=patient.patient_id,
#                 entry_type=EntryType.APPOINTMENT,
#                 visit_reason="First Appointment",
#             )
#         )

#         with pytest.raises(HTTPException) as exc:
#             await visit_service.start_visit(
#                 VisitCreate(
#                     patient_id=patient.patient_id,
#                     entry_type=EntryType.APPOINTMENT,
#                     visit_reason="Duplicate Appointment",
#                 )
#             )

#         assert exc.value.status_code == status.HTTP_409_CONFLICT
#         assert exc.value.detail == "Patient already has an active visit."
backend/app/api/v1/endpoints/tokens.py
backend/app/domain/services/queue_service.py
backend/app/domain/models/models.py
backend/app/domain/schemas/schemas.py
backend/app/domain/services/audit_service.py
backend/app/domain/services/auth_service.py
backend/app/db/session.py

1. Receptionist/admin sends patient_id and department_id.
2. Backend checks the user is logged in.
3. Backend checks the user is RECEPTIONIST or ADMIN.
4. Backend confirms the patient exists.
5. Backend confirms the department exists and is active.
6. Backend finds today's queue for that department.
7. If today's queue does not exist, backend creates it.
8. Backend counts existing tokens in that queue.
9. Backend generates the next token number, e.g. OPD-004.
10. Backend creates a QueueToken.
11. Backend records an audit log.
12. Backend returns the created token.


the service checks
Patient exists
Department exists
Department is active
Today's queue exists or can be created
Existing token count for next token number
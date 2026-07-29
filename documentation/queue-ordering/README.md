After a patient receives a queue token, how does the system decide who appears next in the queue?

Find today's queue for a department
  -> get active queue tokens
  -> load patient details
  -> sort tokens by triage priority
  -> if same priority, sort by arrival time
  -> return ordered list


backend/app/api/v1/endpoints/queues.py
backend/app/domain/services/queue_service.py
backend/app/domain/models/models.py
backend/app/domain/schemas/schemas.py
backend/app/domain/services/auth_service.py
backend/app/db/session.py

Client/frontend
  -> GET /api/v1/queues/{dept_id}/tokens
  -> queues.py/get_queue_tokens()
  -> get_current_user()
  -> get_db()
  -> SQLAlchemy SELECT Queue WHERE dept_id = ... AND queue_date = today
  -> if no queue: return []
  -> QueueService(db)
  -> QueueService.get_ordered_tokens(queue.queue_id)
  -> SQLAlchemy SELECT QueueToken WHERE queue_id = ... AND status is active
  -> load patient details with each token
  -> sort tokens by triage_level and issued_at
  -> convert each token to QueueTokenSummary
  -> return ordered list

1. Staff opens a department queue screen.
2. Frontend asks backend for today’s tokens for that department.
3. Backend checks that the staff member is logged in.
4. Backend looks for today’s queue for that department.
5. If no queue exists yet, backend returns an empty list.
6. If the queue exists, backend gets active tokens.
7. Backend sorts tokens by medical priority.
8. Backend returns the ordered queue list.



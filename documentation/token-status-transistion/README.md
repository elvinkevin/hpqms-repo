Client/frontend
  -> PATCH /api/v1/tokens/{token_id}/status
  -> tokens.py/update_token_status()
  -> get_current_user()
  -> get_db()
  -> QueueService(db)
  -> QueueService.update_token_status(token_id, data.status, data.notes)
  -> db.get(QueueToken, token_id)
  -> check VALID_TRANSITIONS[current_status]
  -> if invalid: raise 422
  -> update token.status
  -> optionally update token.notes
  -> set called_at if new status is CALLED
  -> set completed_at if new status is COMPLETED or TRANSFERRED
  -> db.flush()
  -> audit_service.log_action(...)
  -> QueueTokenRead.model_validate(token)
  -> get_db commits transaction
  -> HTTP response

l41. Staff chooses a new status for a patient token.
2. Backend checks the staff member is logged in.
3. Backend loads the queue token.
4. Backend checks whether the requested status change is allowed.
5. If not allowed, backend rejects it.
6. If allowed, backend updates the token status.
7. Backend records timestamps if needed.
8. Backend writes an audit log.
9. Backend returns the updated token.
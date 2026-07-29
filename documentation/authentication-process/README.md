A. Login: employee_id + password -> JWT token
B. Protected route access: JWT token -> CurrentUser -> optional role check

auth.py
  HTTP login endpoint

auth_service.py
  authentication business logic, current-user loading, role guards

security.py
  password hashing, password verification, JWT creation, JWT decoding

schemas.py
  request/response shapes: LoginRequest, TokenResponse, StaffRead, CurrentUser

models.py
  Staff database table and StaffRole enum

session.py
  gives the route a database session

config.py
  provides SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
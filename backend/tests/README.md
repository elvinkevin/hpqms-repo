tests/
│
├── conftest.py          # Shared fixtures
│
├── services/
│   ├── test_patient_service.py
│   ├── test_visit_service.py
│   ├── test_queue_service.py
│   ├── test_routing_service.py
│   ├── test_token_service.py
│   ├── test_department_service.py
│   ├── test_staff_service.py
│   └── test_auth_service.py
│
├── api/
│   ├── test_patients.py
│   ├── test_visits.py
│   ├── test_queue.py
│   ├── test_routing.py
│   ├── test_staff.py
│   ├── test_departments.py
│   └── test_auth.py
│
└── factories/
    ├── patient_factory.py
    ├── staff_factory.py
    ├── visit_factory.py
    └── queue_factory.py

Phase 1

tests/
    conftest.py

This file creates:                       Result
1. test database                           
2. async session
3. rollback after every test
4. reusable objects

Everything else uses it.
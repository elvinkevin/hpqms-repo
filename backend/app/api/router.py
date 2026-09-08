from fastapi import APIRouter

from app.api.routes import (
    auth,
    patients,
    visits,
    vitals,
    queue,
    routing,
    departments,
    staff,
    token,
    display,
    kiosk,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(patients.router)
api_router.include_router(visits.router)
api_router.include_router(vitals.router, prefix="/visits")
api_router.include_router(queue.router)
api_router.include_router(routing.router)
api_router.include_router(departments.router)
api_router.include_router(staff.router)
api_router.include_router(token.router)
api_router.include_router(display.router)
api_router.include_router(kiosk.router)
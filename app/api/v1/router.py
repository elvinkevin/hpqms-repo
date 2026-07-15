from fastapi import APIRouter
from app.api.v1.endpoints import auth, patients, tokens, queues

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(patients.router)
api_router.include_router(tokens.router)
api_router.include_router(queues.router)

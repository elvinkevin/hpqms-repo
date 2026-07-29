# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from app.api.v1.router import api_router
# from app.api.v1.endpoints import websocket
# from app.core.config import settings

# app = FastAPI(
#     title="Hospital Patient Queue Management System",
#     description="HPQMS API — Phase 1",
#     version="1.0.0",
#     docs_url="/docs",
#     redoc_url="/redoc",
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],  # Vite dev server
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(api_router)
# app.include_router(websocket.router)

# # Add this endpoint
# @app.get("/")
# def read_root():
#     return {"message": "Welcome to the HQMS Clinic Queue API Engine"}

# @app.get("/health")
# async def health():
#     return {"status": "ok", "environment": settings.ENVIRONMENT}


from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(
    title="Hospital Queue Management API",
    version="1.0.0",
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "Hospital Queue Management API"}
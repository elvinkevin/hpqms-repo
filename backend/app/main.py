from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.routes.display import websocket_router

app = FastAPI(
    title="Hospital Queue Management API",
    version="1.0.0",
)

# Configure CORS for local dev and LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount(
    "/static",
    StaticFiles(directory=str(frontend_dir), html=True),
    name="frontend",
)

app.include_router(api_router)
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {"message": "Hospital Queue Management API"}
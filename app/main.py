from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.logging import get_logger
from app.services.auth import authenticate
from app.api.endpoints import router
from app.api.server_events import router as server_events_router
from app.api.appearance_events import router as appearance_events_router
from app.scheduler.face_events_scheduler import start_scheduler
from app.scheduler.generic_events_scheduler import start_event_schedulers
# from app.scheduler.generic_events_scheduler import start_data_pipeline_schedulers
from app.scheduler.generic_events_media_scheduler import start_generic_events_media_scheduler
from app.scheduler.event_facial_recognition_scheduler import start_event_facial_recognition_scheduler
from app.scheduler.auth_token_scheduler import start_auth_scheduler

logger = get_logger("avigilon-base")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up and authenticating with Avigilon API...")
    await authenticate()
    logger.info("Authentication complete.")
    start_scheduler()
    # start_data_pipeline_schedulers()
    start_event_schedulers()
    start_generic_events_media_scheduler()
    start_event_facial_recognition_scheduler()
    start_auth_scheduler()
    yield
    logger.info("Shutting down...")

app = FastAPI(
    title="Avigilon Integration API",
    description="FastAPI application for interacting with Avigilon REST APIs and receiving event webhooks.",
    version="1.0.0",
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
)

@app.get("/")
def index():
    return "Welcome to Duke proxy API"

app.include_router(router)
app.include_router(server_events_router)
app.include_router(appearance_events_router)

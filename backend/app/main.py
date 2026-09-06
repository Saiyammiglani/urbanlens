"""FastAPI application factory. Optionally runs the MQTT worker in-process."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal, init_db

log = logging.getLogger("urbanlens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.RUN_MQTT_WORKER and settings.MQTT_HOST:
        from .mqtt_worker import run_worker
        run_worker(background=True)
        log.info("MQTT worker started (topic=%s)", settings.MQTT_TOPIC)
    yield


app = FastAPI(title="UrbanLens API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo; lock down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

from . import incidents, ingest, media, routing, live, weather, aqi, traffic  # noqa: E402

app.include_router(ingest.router)
app.include_router(incidents.router)
app.include_router(routing.router)
app.include_router(media.router)
app.include_router(live.router)
app.include_router(weather.router)
app.include_router(aqi.router)
app.include_router(traffic.router)


@app.get("/", tags=["health"])
def root():
    return {"service": "urbanlens", "status": "ok"}


@app.get("/api/v1/health", tags=["health"])
def health():
    db = SessionLocal()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    finally:
        db.close()

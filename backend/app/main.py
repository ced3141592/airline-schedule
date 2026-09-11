from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Initializing database schema")
    init_db()
    yield


settings = get_settings()
app = FastAPI(title="Airline Schedule", version="1.0.0", lifespan=lifespan)
app.include_router(router, prefix="/api")

frontend_dir = Path(settings.frontend_dir)
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

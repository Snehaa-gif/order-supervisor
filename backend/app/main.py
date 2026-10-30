"""FastAPI application. Run with:  uv run uvicorn app.main:app --reload --port 8000"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db import repository as repo
from app.db.session import init_db, session_scope
from app.templates import TEMPLATES

logger = logging.getLogger("order_supervisor.api")


async def seed_templates() -> None:
    """Insert the built-in supervisor templates if they are missing."""
    async with session_scope() as session:
        for template in TEMPLATES:
            if await repo.get_supervisor(session, template.id) is None:
                await repo.create_supervisor(session, template, is_template=True)
                logger.info("Seeded supervisor template %s", template.id)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await seed_templates()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Order Supervisor API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

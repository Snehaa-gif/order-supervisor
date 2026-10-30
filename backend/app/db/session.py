"""Async engine/session factory with Supabase-friendly URL handling."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base


def normalize_database_url(raw: str) -> tuple[str, dict[str, Any]]:
    """Turn a plain `postgres://` / `postgresql://` URL (as Supabase shows it) into an asyncpg URL.

    Returns the URL and extra `connect_args` for the driver.
    """
    url = make_url(raw)
    connect_args: dict[str, Any] = {}
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg":
        host = url.host or ""
        if host not in ("localhost", "127.0.0.1") and "ssl" not in url.query and "sslmode" not in url.query:
            connect_args["ssl"] = "require"
        if "pooler.supabase.com" in host:
            # Supabase's pooler can't keep prepared statements across connections.
            connect_args["statement_cache_size"] = 0
    return url.render_as_string(hide_password=False), connect_args


@lru_cache
def get_engine() -> AsyncEngine:
    url, connect_args = normalize_database_url(get_settings().database_url)
    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


_SCHEMA_LOCK_ID = 73_012_026  # arbitrary, app-wide advisory lock key


async def init_db() -> None:
    async with get_engine().begin() as conn:
        if conn.dialect.name == "postgresql":
            # The API and the worker both call this on startup; serialize them so a fresh database
            # doesn't see two concurrent CREATE TABLEs. The lock is released when the transaction ends.
            await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SCHEMA_LOCK_ID})
        await conn.run_sync(Base.metadata.create_all)

from __future__ import annotations

import asyncpg
from fastapi import FastAPI

from .config import settings

_pool: asyncpg.Pool | None = None


async def get_pool(app: FastAPI) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DSN,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool  # type: ignore[return-value]


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

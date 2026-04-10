from __future__ import annotations

import logging
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import close_pool, get_pool
from .routes.rest import router as rest_router
from .routes.schema import router as schema_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("data-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await get_pool(app)
    logger.info("✅ asyncpg pool connected to %s:%s/%s",
                settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB)
    yield
    await close_pool()
    logger.info("asyncpg pool closed.")


app = FastAPI(
    title="Sentinel Data API",
    description=(
        "PostgREST-style REST API for your Postgres tables. "
        "All queries are tenant-scoped and JWT-authenticated."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(schema_router)


@app.get("/")
async def root():
    return {
        "service": "Sentinel Data API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "data-service"}


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.DATA_SERVICE_PORT,
        reload=True,
    )

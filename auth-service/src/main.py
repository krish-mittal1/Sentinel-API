import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import engine
from .middleware import metrics_middleware
from .routes.admin import router as admin_router
from .routes.auth import router as auth_router
from .utils.exceptions import AppException, app_exception_handler
from .utils.metrics import MetricsRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)-5s | %(message)s",
)
logger = logging.getLogger("auth.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.metrics = MetricsRegistry()
    app.state.redis = None
    try:
        app.state.redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
        await app.state.redis.ping()
        logger.info("Connected to Redis at %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
    except Exception as exc:
        logger.warning("Redis unavailable for auth throttling: %s", exc)
        app.state.redis = None

    yield

    if app.state.redis is not None:
        await app.state.redis.close()
    await engine.dispose()

app = FastAPI(
    title="Sentinel Auth Service",
    description="Handles user registration, login, and JWT issuance.",
    version="1.0.0",
    lifespan=lifespan,
)

app.middleware("http")(metrics_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)

app.include_router(auth_router)
app.include_router(admin_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "auth-service"}

@app.get("/ready")
async def readiness_check():
    db_ok = False
    redis_ok = app.state.redis is not None
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: None)
        db_ok = True
    except Exception as exc:
        logger.warning("Database readiness failed: %s", exc)

    return {
        "status": "ready" if db_ok else "degraded",
        "service": "auth-service",
        "checks": {"database": db_ok, "redis": redis_ok},
    }

@app.get("/metrics")
async def metrics():
    return app.state.metrics.snapshot()

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.AUTH_SERVICE_PORT,
        reload=True,
    )

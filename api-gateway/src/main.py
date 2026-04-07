import logging

import redis.asyncio as aioredis
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .routes.proxy import router as proxy_router
from .middleware.rate_limiter import RateLimiterMiddleware
from .middleware.logger import LoggerMiddleware
from .middleware.auth import verify_jwt_middleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-8s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gateway")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
        await app.state.redis.ping()
        logger.info("✅ Connected to Redis at %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
    except Exception as e:
        logger.warning("⚠️  Redis unavailable (%s). Rate limiting disabled.", e)
        app.state.redis = None

    yield

    if app.state.redis:
        await app.state.redis.close()
        logger.info("Redis connection closed.")

app = FastAPI(
    title="Sentinel API Gateway",
    description="Central entry point — routing, rate limiting, logging, JWT verification.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(LoggerMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=verify_jwt_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(proxy_router)

@app.get("/")
async def root():
    return {"service": "Sentinel API Gateway", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway"}

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.GATEWAY_PORT,
        reload=True,
    )

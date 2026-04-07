import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings

class RateLimiterMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request: Request, call_next):
        redis = request.app.state.redis
        if redis is None:
            return await call_next(request)

        client_ip = request.client.host
        key = f"rate_limit:{client_ip}"
        now = time.time()
        window_start = now - settings.RATE_LIMIT_WINDOW_SEC

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}": now})
        pipe.expire(key, settings.RATE_LIMIT_WINDOW_SEC)
        results = await pipe.execute()

        request_count = results[1] 

        if request_count >= settings.RATE_LIMIT_MAX_REQUESTS:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded. Max {settings.RATE_LIMIT_MAX_REQUESTS} requests per {settings.RATE_LIMIT_WINDOW_SEC}s."},
            )

        return await call_next(request)

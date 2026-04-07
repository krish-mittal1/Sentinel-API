import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = logging.getLogger("gateway")

class LoggerMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)

        logger.info(
            "%s %s → %s  [%sms]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response

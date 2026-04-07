import time

from fastapi import Request

async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    response.headers["X-Process-Time"] = f"{duration_ms}ms"
    request.app.state.metrics.record_request(request.url.path, request.method, response.status_code)
    return response

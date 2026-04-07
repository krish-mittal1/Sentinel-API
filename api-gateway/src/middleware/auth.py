from fastapi import Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from ..config import settings

PUBLIC_PREFIXES = ["/auth", "/health", "/docs", "/openapi.json", "/redoc"]
PUBLIC_EXACT = ["/"]

def is_public_route(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

async def verify_jwt_middleware(request: Request, call_next):
    if is_public_route(request.url.path):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid Authorization header"},
        )

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or expired token"},
        )

    request.state.user = payload
    return await call_next(request)

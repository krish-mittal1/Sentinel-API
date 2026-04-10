from __future__ import annotations

from typing import Annotated, Optional

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from .config import settings

# ── Tables that belong to Sentinel internals — never exposed via Data API ──
BLOCKED_TABLES = frozenset(
    {
        "tenants",
        "users",
        "refresh_sessions",
        "auth_tokens",
        "audit_logs",
        "alembic_version",
    }
)


async def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.pool  # type: ignore[return-value]


DbDep = Annotated[asyncpg.Pool, Depends(get_db)]


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return auth[len("Bearer "):]


async def get_current_user(request: Request) -> dict:
    token = _extract_token(request)
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    tenant_id: Optional[str] = payload.get("tenant_id")
    sub: Optional[str] = payload.get("sub")
    if not tenant_id or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
        )
    return {
        "user_id": sub,
        "tenant_id": tenant_id,
        "role": payload.get("role", "user"),
        "email": payload.get("email"),
    }


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_table_access(table: str) -> None:
    """Raise 403 if the table is an internal Sentinel table."""
    if table.lower() in BLOCKED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Table '{table}' is protected and cannot be accessed via the Data API",
        )

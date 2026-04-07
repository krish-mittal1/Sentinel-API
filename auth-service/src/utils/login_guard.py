from __future__ import annotations

from redis.asyncio import Redis
from typing import Optional

from ..config import settings

def _key(identity: str) -> str:
    return f"auth:login:{identity.lower()}"

async def ensure_login_allowed(redis: Optional[Redis], identity: str) -> None:
    if redis is None:
        return

    ttl = await redis.ttl(_key(identity))
    attempts = await redis.get(_key(identity))
    if attempts and int(attempts) >= settings.LOGIN_MAX_ATTEMPTS and ttl > 0:
        from ..utils.exceptions import ForbiddenError
        raise ForbiddenError("Too many failed login attempts. Try again later.")

async def record_failed_attempt(redis: Optional[Redis], identity: str) -> int:
    if redis is None:
        return 0

    key = _key(identity)
    attempts = await redis.incr(key)
    if attempts == 1:
        await redis.expire(key, settings.LOGIN_WINDOW_SEC)
    if attempts >= settings.LOGIN_MAX_ATTEMPTS:
        await redis.expire(key, settings.LOGIN_LOCKOUT_SEC)
    return int(attempts)

async def clear_failed_attempts(redis: Optional[Redis], identity: str) -> None:
    if redis is not None:
        await redis.delete(_key(identity))

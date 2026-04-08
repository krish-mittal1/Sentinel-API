from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog

logger = logging.getLogger("auth.audit")

async def record_audit_event(
    db: AsyncSession,
    *,
    tenant_id,
    event_type: str,
    user_id=None,
    email: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "success",
    details: Optional[str] = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            event_type=event_type,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255] or None,
            status=status,
            details=details,
        )
    )
    logger.info(
        "audit event=%s status=%s tenant_id=%s user_id=%s email=%s ip=%s",
        event_type,
        status,
        tenant_id,
        user_id,
        email,
        ip_address,
    )

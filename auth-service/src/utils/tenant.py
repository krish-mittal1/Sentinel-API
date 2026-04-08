from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Tenant
from .exceptions import ConflictError, ForbiddenError, NotFoundError

_slug_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_tenant_slug(value: str) -> str:
    slug = (value or "").strip().lower()
    if not _slug_pattern.fullmatch(slug):
        raise ConflictError(
            "Tenant slug must use lowercase letters, numbers, and hyphens only"
        )
    return slug


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.slug == normalize_tenant_slug(slug)))
    return result.scalar_one_or_none()


async def ensure_tenant(db: AsyncSession, slug: str) -> Tenant:
    tenant = await get_tenant_by_slug(db, slug)
    if not tenant:
        raise NotFoundError(f"Tenant '{slug}' not found")
    if not tenant.is_active:
        raise ForbiddenError("Tenant is inactive")
    return tenant


async def ensure_default_tenant(db: AsyncSession) -> Tenant:
    slug = normalize_tenant_slug(settings.DEFAULT_TENANT_SLUG)
    tenant = await get_tenant_by_slug(db, slug)
    if tenant:
        return tenant

    tenant = Tenant(name="Default Tenant", slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    return tenant


async def create_tenant(db: AsyncSession, *, name: str, slug: str) -> Tenant:
    normalized_slug = normalize_tenant_slug(slug)
    existing = await get_tenant_by_slug(db, normalized_slug)
    if existing:
        raise ConflictError("Tenant slug already exists")

    tenant = Tenant(name=name.strip(), slug=normalized_slug, is_active=True)
    db.add(tenant)
    await db.flush()
    return tenant

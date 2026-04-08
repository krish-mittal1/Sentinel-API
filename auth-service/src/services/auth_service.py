from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import AuditLog, AuthToken, RefreshSession, Tenant, User
from ..schemas import ForgotPasswordRequest, LoginRequest, SignupRequest
from ..utils.audit import record_audit_event
from ..utils.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from ..utils.hashing import hash_password, verify_password
from ..utils.jwt import create_access_token, verify_token
from ..utils.login_guard import clear_failed_attempts, ensure_login_allowed, record_failed_attempt
from ..utils.metrics import MetricsRegistry
from ..utils.tenant import create_tenant as create_tenant_record
from ..utils.tenant import ensure_default_tenant, ensure_tenant
from ..utils.tokens import generate_secure_token, hash_token

EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _create_action_token(
    db: AsyncSession,
    tenant: Tenant,
    user: User,
    token_type: str,
    expires_in_minutes: int,
) -> str:
    await db.execute(
        delete(AuthToken).where(
            AuthToken.tenant_id == tenant.id,
            AuthToken.user_id == user.id,
            AuthToken.token_type == token_type,
            AuthToken.consumed_at.is_(None),
        )
    )

    plain_token = generate_secure_token()
    db.add(
        AuthToken(
            tenant_id=tenant.id,
            user_id=user.id,
            token_type=token_type,
            token_hash=hash_token(plain_token),
            expires_at=_utcnow() + timedelta(minutes=expires_in_minutes),
        )
    )
    await db.flush()
    return plain_token


async def _consume_action_token(
    db: AsyncSession, token: str, token_type: str
) -> Optional[AuthToken]:
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(token),
            AuthToken.token_type == token_type,
            AuthToken.consumed_at.is_(None),
            AuthToken.expires_at > _utcnow(),
        )
    )
    auth_token = result.scalar_one_or_none()
    if auth_token:
        auth_token.consumed_at = _utcnow()
        await db.flush()
    return auth_token


async def _revoke_family(
    db: AsyncSession,
    family_id: uuid.UUID,
    reason: str,
) -> None:
    await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow(), revoked_reason=reason)
    )


async def _issue_refresh_session(
    tenant: Tenant,
    user: User,
    db: AsyncSession,
    ip_address: Optional[str],
    user_agent: Optional[str],
    *,
    family_id: Optional[uuid.UUID] = None,
    parent_session_id: Optional[uuid.UUID] = None,
) -> RefreshSession:
    refresh_token = generate_secure_token()
    session = RefreshSession(
        tenant_id=tenant.id,
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        parent_session_id=parent_session_id,
        token_hash=hash_token(refresh_token),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        last_used_at=_utcnow(),
    )
    db.add(session)
    user.last_login_at = _utcnow()
    await db.flush()
    session.plain_token = refresh_token  # type: ignore[attr-defined]
    return session


async def _build_auth_response(
    tenant: Tenant,
    user: User,
    db: AsyncSession,
    ip_address: Optional[str],
    user_agent: Optional[str],
    *,
    family_id: Optional[uuid.UUID] = None,
    parent_session_id: Optional[uuid.UUID] = None,
) -> Tuple[User, str, str]:
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "tenant_id": str(tenant.id),
            "tenant_slug": tenant.slug,
            "email": user.email,
            "role": user.role,
        }
    )
    session = await _issue_refresh_session(
        tenant,
        user,
        db,
        ip_address,
        user_agent,
        family_id=family_id,
        parent_session_id=parent_session_id,
    )
    await db.refresh(user)
    return user, access_token, session.plain_token  # type: ignore[attr-defined]


async def signup(
    tenant_slug: str,
    data: SignupRequest,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> Tuple[User, str]:
    tenant = await ensure_tenant(db, tenant_slug)
    result = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == data.email)
    )
    existing = result.scalar_one_or_none()
    if existing:
        if metrics:
            metrics.record_auth_event("signup", "conflict")
        await record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="signup",
            email=data.email,
            ip_address=ip_address,
            user_agent=user_agent,
            status="conflict",
            details="duplicate_email",
        )
        await db.commit()
        raise ConflictError("Email already registered for this tenant")

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        password=hash_password(data.password),
        name=data.name,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        if metrics:
            metrics.record_auth_event("signup", "conflict")
        raise ConflictError("Email already registered for this tenant")

    verification_token = await _create_action_token(
        db,
        tenant,
        user,
        EMAIL_VERIFICATION,
        settings.EMAIL_VERIFICATION_TOKEN_MINUTES,
    )
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="signup",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        details="verification_token_issued",
    )
    if metrics:
        metrics.record_auth_event("signup", "success")
    return user, verification_token


async def verify_email(
    token: str,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> Tuple[User, str, str]:
    auth_token = await _consume_action_token(db, token, EMAIL_VERIFICATION)
    if not auth_token:
        if metrics:
            metrics.record_auth_event("verify_email", "failed")
        await record_audit_event(
            db,
            tenant_id=await _default_tenant_id(db),
            event_type="verify_email",
            ip_address=ip_address,
            user_agent=user_agent,
            status="failed",
            details="invalid_token",
        )
        await db.commit()
        raise UnauthorizedError("Invalid or expired verification token")

    user = await db.get(User, auth_token.user_id)
    tenant = await db.get(Tenant, auth_token.tenant_id)
    if not user or not tenant:
        raise UnauthorizedError("Invalid verification token")

    user.email_verified = True
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="verify_email",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if metrics:
        metrics.record_auth_event("verify_email", "success")
    return await _build_auth_response(tenant, user, db, ip_address, user_agent)


async def login(
    tenant_slug: str,
    data: LoginRequest,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    redis: Optional[Redis] = None,
    metrics: Optional[MetricsRegistry] = None,
) -> Tuple[User, str, str]:
    tenant = await ensure_tenant(db, tenant_slug)
    login_key = f"{tenant.slug}:{data.email}"
    await ensure_login_allowed(redis, login_key)

    result = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password):
        await record_failed_attempt(redis, login_key)
        await record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="login",
            email=data.email,
            ip_address=ip_address,
            user_agent=user_agent,
            status="failed",
            details="invalid_credentials",
        )
        await db.commit()
        if metrics:
            metrics.record_auth_event("login", "failed")
        raise UnauthorizedError("Invalid email or password")

    if not user.email_verified:
        await record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="login",
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            status="blocked",
            details="email_not_verified",
        )
        await db.commit()
        if metrics:
            metrics.record_auth_event("login", "blocked")
        raise ForbiddenError("Verify your email before logging in")

    await clear_failed_attempts(redis, login_key)
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="login",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if metrics:
        metrics.record_auth_event("login", "success")
    return await _build_auth_response(tenant, user, db, ip_address, user_agent)


async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> Tuple[User, str, str]:
    token_hash_value = hash_token(refresh_token)
    result = await db.execute(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash_value)
    )
    session = result.scalar_one_or_none()
    if not session:
        if metrics:
            metrics.record_auth_event("refresh", "failed")
        raise UnauthorizedError("Invalid or expired refresh token")

    tenant = await db.get(Tenant, session.tenant_id)
    if not tenant:
        raise UnauthorizedError("Tenant no longer exists")

    if session.revoked_at is not None:
        await _revoke_family(db, session.family_id, "replay_detected")
        await record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="refresh_reuse_detected",
            user_id=session.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status="failed",
            details="family_revoked",
        )
        await db.commit()
        if metrics:
            metrics.record_auth_event("refresh", "replay_detected")
        raise UnauthorizedError("Refresh token reuse detected. Please log in again.")

    if _normalize_datetime(session.expires_at) <= _utcnow():
        session.revoked_at = _utcnow()
        session.revoked_reason = "expired"
        await db.commit()
        if metrics:
            metrics.record_auth_event("refresh", "expired")
        raise UnauthorizedError("Invalid or expired refresh token")

    user = await db.get(User, session.user_id)
    if not user or user.tenant_id != tenant.id:
        raise UnauthorizedError("Refresh session is no longer valid")

    session.revoked_at = _utcnow()
    session.revoked_reason = "rotated"
    user.last_login_at = _utcnow()
    next_user, access_token, next_refresh_token = await _build_auth_response(
        tenant,
        user,
        db,
        ip_address,
        user_agent,
        family_id=session.family_id,
        parent_session_id=session.id,
    )
    replacement = await db.execute(
        select(RefreshSession)
        .where(RefreshSession.parent_session_id == session.id)
        .order_by(RefreshSession.created_at.desc())
    )
    replacement_session = replacement.scalars().first()
    if replacement_session:
        session.replaced_by_session_id = replacement_session.id

    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="refresh",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if metrics:
        metrics.record_auth_event("refresh", "success")
    return next_user, access_token, next_refresh_token


async def logout(
    refresh_token: str,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> None:
    result = await db.execute(
        select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token))
    )
    session = result.scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = _utcnow()
        session.revoked_reason = "logout"
        await record_audit_event(
            db,
            tenant_id=session.tenant_id,
            event_type="logout",
            user_id=session.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if metrics:
            metrics.record_auth_event("logout", "success")


async def forgot_password(
    tenant_slug: str,
    data: ForgotPasswordRequest,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> Optional[str]:
    tenant = await ensure_tenant(db, tenant_slug)
    result = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == data.email)
    )
    user = result.scalar_one_or_none()
    if not user:
        await record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="forgot_password",
            email=data.email,
            ip_address=ip_address,
            user_agent=user_agent,
            status="ignored",
            details="unknown_email",
        )
        await db.commit()
        if metrics:
            metrics.record_auth_event("forgot_password", "ignored")
        return None

    token = await _create_action_token(
        db,
        tenant,
        user,
        PASSWORD_RESET,
        settings.PASSWORD_RESET_TOKEN_MINUTES,
    )
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="forgot_password",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if metrics:
        metrics.record_auth_event("forgot_password", "success")
    return token


async def reset_password(
    token: str,
    new_password: str,
    db: AsyncSession,
    *,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metrics: Optional[MetricsRegistry] = None,
) -> None:
    auth_token = await _consume_action_token(db, token, PASSWORD_RESET)
    if not auth_token:
        if metrics:
            metrics.record_auth_event("reset_password", "failed")
        await db.commit()
        raise UnauthorizedError("Invalid or expired password reset token")

    user = await db.get(User, auth_token.user_id)
    tenant = await db.get(Tenant, auth_token.tenant_id)
    if not user or not tenant:
        raise UnauthorizedError("Reset token is no longer valid")

    user.password = hash_password(new_password)
    await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="reset_password",
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if metrics:
        metrics.record_auth_event("reset_password", "success")


async def get_user_from_access_token(token: str, db: AsyncSession) -> User:
    payload = verify_token(token)
    if not payload or not payload.get("sub") or not payload.get("tenant_id"):
        raise UnauthorizedError("Invalid or expired token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user or str(user.tenant_id) != str(payload["tenant_id"]):
        raise UnauthorizedError("User no longer exists")

    return user


async def list_tenants(db: AsyncSession) -> list[Tenant]:
    await ensure_default_tenant(db)
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.asc()))
    return list(result.scalars().all())


async def create_tenant(name: str, slug: str, db: AsyncSession) -> Tenant:
    tenant = await create_tenant_record(db, name=name, slug=slug)
    await record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="tenant_created",
        details=f"slug={tenant.slug}",
    )
    return tenant


async def dashboard_snapshot(db: AsyncSession) -> dict:
    await ensure_default_tenant(db)
    total_users = await db.scalar(select(func.count(User.id)))
    verified_users = await db.scalar(select(func.count(User.id)).where(User.email_verified.is_(True)))
    admin_users = await db.scalar(select(func.count(User.id)).where(User.role.in_(["admin", "super_admin"])))
    active_sessions = await db.scalar(
        select(func.count(RefreshSession.id)).where(
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > _utcnow(),
        )
    )
    pending_verifications = await db.scalar(
        select(func.count(AuthToken.id)).where(
            AuthToken.token_type == EMAIL_VERIFICATION,
            AuthToken.consumed_at.is_(None),
            AuthToken.expires_at > _utcnow(),
        )
    )
    pending_password_resets = await db.scalar(
        select(func.count(AuthToken.id)).where(
            AuthToken.token_type == PASSWORD_RESET,
            AuthToken.consumed_at.is_(None),
            AuthToken.expires_at > _utcnow(),
        )
    )
    failed_logins_24h = await db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.event_type == "login",
            AuditLog.status == "failed",
            AuditLog.created_at > (_utcnow() - timedelta(hours=24)),
        )
    )

    recent_users_result = await db.execute(select(User).order_by(User.created_at.desc()).limit(10))
    recent_audit_result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(15))
    tenants_result = await db.execute(select(Tenant).order_by(Tenant.created_at.asc()))

    return {
        "metrics": {
            "total_users": total_users or 0,
            "verified_users": verified_users or 0,
            "admin_users": admin_users or 0,
            "active_sessions": active_sessions or 0,
            "pending_verifications": pending_verifications or 0,
            "pending_password_resets": pending_password_resets or 0,
            "failed_logins_24h": failed_logins_24h or 0,
        },
        "recent_users": [
            {
                "tenant_id": str(user.tenant_id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "email_verified": user.email_verified,
                "created_at": user.created_at.isoformat(),
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            for user in recent_users_result.scalars().all()
        ],
        "recent_audit_events": [
            {
                "tenant_id": str(item.tenant_id),
                "event_type": item.event_type,
                "email": item.email,
                "status": item.status,
                "details": item.details,
                "created_at": item.created_at.isoformat(),
            }
            for item in recent_audit_result.scalars().all()
        ],
        "tenants": [
            {
                "id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": tenant.is_active,
                "created_at": tenant.created_at.isoformat(),
            }
            for tenant in tenants_result.scalars().all()
        ],
    }


async def _default_tenant_id(db: AsyncSession) -> uuid.UUID:
    tenant = await ensure_default_tenant(db)
    return tenant.id

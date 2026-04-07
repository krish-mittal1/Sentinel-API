import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("AUTH_DEBUG_RETURN_TOKENS", "true")
os.environ.setdefault("EMAIL_DELIVERY_MODE", "file")
os.environ.setdefault("EMAIL_OUTPUT_DIR", str(Path(tempfile.gettempdir()) / "sentinel-auth-tests-outbox"))

from src.database import Base
from src.main import app
from src.models import User
from src.database import get_db
from src.utils.hashing import hash_password
from src.utils.metrics import MetricsRegistry

@pytest_asyncio.fixture
async def client(tmp_path: Path):
    db_path = tmp_path / "auth-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.state.metrics = MetricsRegistry()
    app.state.redis = None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_signup_verify_login_refresh_and_reuse_detection(client):
    async_client, _ = client

    signup = await async_client.post(
        "/signup",
        json={"email": "user@example.com", "password": "Password123", "name": "User"},
    )
    assert signup.status_code == 201
    verification_token = signup.json()["verification_token"]
    assert verification_token

    blocked_login = await async_client.post(
        "/login",
        json={"email": "user@example.com", "password": "Password123"},
    )
    assert blocked_login.status_code == 403

    verify = await async_client.post("/verify-email", json={"token": verification_token})
    assert verify.status_code == 200
    auth = verify.json()
    first_refresh = auth["refresh_token"]

    refresh = await async_client.post("/refresh", json={"refresh_token": first_refresh})
    assert refresh.status_code == 200
    second_refresh = refresh.json()["refresh_token"]
    assert second_refresh != first_refresh

    reused = await async_client.post("/refresh", json={"refresh_token": first_refresh})
    assert reused.status_code == 401
    assert "reuse detected" in reused.json()["detail"].lower()

    family_revoked = await async_client.post("/refresh", json={"refresh_token": second_refresh})
    assert family_revoked.status_code == 401

@pytest.mark.asyncio
async def test_forgot_and_reset_password_flow(client):
    async_client, _ = client

    signup = await async_client.post(
        "/signup",
        json={"email": "reset@example.com", "password": "Password123", "name": "Reset User"},
    )
    verification_token = signup.json()["verification_token"]
    await async_client.post("/verify-email", json={"token": verification_token})

    forgot = await async_client.post("/forgot-password", json={"email": "reset@example.com"})
    assert forgot.status_code == 200
    reset_token = forgot.json()["token"]
    assert reset_token

    reset = await async_client.post(
        "/reset-password",
        json={"token": reset_token, "new_password": "NewPassword123"},
    )
    assert reset.status_code == 200

    old_login = await async_client.post(
        "/login",
        json={"email": "reset@example.com", "password": "Password123"},
    )
    assert old_login.status_code == 401

    new_login = await async_client.post(
        "/login",
        json={"email": "reset@example.com", "password": "NewPassword123"},
    )
    assert new_login.status_code == 200

@pytest.mark.asyncio
async def test_admin_dashboard_requires_admin(client):
    async_client, session_factory = client

    async with session_factory() as session:
        admin = User(
            email="admin@example.com",
            password=hash_password("Password123"),
            name="Admin",
            role="admin",
            email_verified=True,
        )
        user = User(
            email="member@example.com",
            password=hash_password("Password123"),
            name="Member",
            role="user",
            email_verified=True,
        )
        session.add_all([admin, user])
        await session.commit()

    admin_login = await async_client.post(
        "/login",
        json={"email": "admin@example.com", "password": "Password123"},
    )
    admin_token = admin_login.json()["access_token"]

    dashboard = await async_client.get(
        "/admin/overview",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert dashboard.status_code == 200
    assert "metrics" in dashboard.json()

    member_login = await async_client.post(
        "/login",
        json={"email": "member@example.com", "password": "Password123"},
    )
    member_token = member_login.json()["access_token"]

    forbidden = await async_client.get(
        "/admin/overview",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert forbidden.status_code == 403

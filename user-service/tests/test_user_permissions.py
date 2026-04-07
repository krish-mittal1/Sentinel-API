import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")

from src.config import settings
from src.database import Base, get_db
from src.main import app
from src.models import User

def make_token(user_id: uuid.UUID, email: str, role: str) -> str:
    return jwt.encode(
        {"sub": str(user_id), "email": email, "role": role},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

@pytest_asyncio.fixture
async def client(tmp_path: Path):
    db_path = tmp_path / "user-test.db"
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_user_permissions_and_admin_controls(client):
    async_client, session_factory = client

    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    async with session_factory() as session:
        session.add_all(
            [
                User(id=user_id, email="user@example.com", password="x", name="User", role="user"),
                User(id=other_id, email="other@example.com", password="x", name="Other", role="user"),
                User(id=admin_id, email="admin@example.com", password="x", name="Admin", role="admin"),
            ]
        )
        await session.commit()

    user_headers = {"Authorization": f"Bearer {make_token(user_id, 'user@example.com', 'user')}"}
    admin_headers = {"Authorization": f"Bearer {make_token(admin_id, 'admin@example.com', 'admin')}"}

    own_profile = await async_client.get(f"/{user_id}", headers=user_headers)
    assert own_profile.status_code == 200

    other_profile = await async_client.get(f"/{other_id}", headers=user_headers)
    assert other_profile.status_code == 403

    list_forbidden = await async_client.get("/", headers=user_headers)
    assert list_forbidden.status_code == 403

    admin_list = await async_client.get("/", headers=admin_headers)
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] == 3

    delete_forbidden = await async_client.delete(f"/{other_id}", headers=user_headers)
    assert delete_forbidden.status_code == 403

    delete_allowed = await async_client.delete(f"/{other_id}", headers=admin_headers)
    assert delete_allowed.status_code == 204

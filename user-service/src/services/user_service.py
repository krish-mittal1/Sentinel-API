import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.exceptions import ConflictError, ForbiddenError, NotFoundError
from ..models import User
from ..schemas import UserUpdateRequest


def _is_super_admin(current_user: dict) -> bool:
    return current_user.get("role") == "super_admin"


def _tenant_id(current_user: dict) -> str:
    return str(current_user["tenant_id"])


async def get_all_users(current_user: dict, db: AsyncSession) -> tuple[list[User], int]:
    user_query = select(User).order_by(User.created_at.desc())
    count_query = select(func.count(User.id))

    if not _is_super_admin(current_user):
        tenant_filter = User.tenant_id == uuid.UUID(_tenant_id(current_user))
        user_query = user_query.where(tenant_filter)
        count_query = count_query.where(tenant_filter)

    result = await db.execute(user_query)
    users = list(result.scalars().all())

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return users, total


async def get_user_by_id(
    user_id: uuid.UUID,
    current_user: dict,
    db: AsyncSession,
) -> User:
    if str(user_id) != current_user["sub"] and current_user.get("role") not in ("admin", "super_admin"):
        raise ForbiddenError("You can only view your own profile")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if not _is_super_admin(current_user) and str(user.tenant_id) != _tenant_id(current_user):
        raise NotFoundError(f"User {user_id} not found")
    return user


async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: dict,
    db: AsyncSession,
) -> User:
    if str(user_id) != current_user["sub"] and current_user.get("role") not in ("admin", "super_admin"):
        raise ForbiddenError("You can only update your own profile")

    user = await get_user_by_id(user_id, current_user, db)

    if data.email and data.email != user.email:
        existing = await db.execute(
            select(User).where(User.tenant_id == user.tenant_id, User.email == data.email)
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email already in use for this tenant")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.flush()
    await db.refresh(user)
    return user


async def delete_user(user_id: uuid.UUID, current_user: dict, db: AsyncSession) -> None:
    user = await get_user_by_id(user_id, current_user, db)
    await db.delete(user)
    await db.flush()

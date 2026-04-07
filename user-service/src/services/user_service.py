import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..schemas import UserUpdateRequest
from ..middleware.exceptions import NotFoundError, ConflictError, ForbiddenError

async def get_all_users(db: AsyncSession) -> tuple[list[User], int]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())

    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar()

    return users, total

async def get_user_by_id(
    user_id: uuid.UUID,
    current_user: dict,
    db: AsyncSession,
) -> User:
    if str(user_id) != current_user["sub"] and current_user.get("role") != "admin":
        raise ForbiddenError("You can only view your own profile")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    return user

async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: dict,
    db: AsyncSession,
) -> User:
    if str(user_id) != current_user["sub"] and current_user.get("role") != "admin":
        raise ForbiddenError("You can only update your own profile")

    user = await get_user_by_id(user_id, current_user, db)

    if data.email and data.email != user.email:
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise ConflictError("Email already in use")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.flush()
    await db.refresh(user)
    return user

async def delete_user(user_id: uuid.UUID, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    await db.delete(user)
    await db.flush()

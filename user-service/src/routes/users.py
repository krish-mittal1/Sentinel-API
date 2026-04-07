import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import UserResponse, UserUpdateRequest, UserListResponse
from ..services import user_service
from ..middleware.auth import get_current_user
from ..middleware.role_guard import require_role

router = APIRouter(tags=["Users"])

@router.get("/", response_model=UserListResponse)
async def list_users(
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    users, total = await user_service.get_all_users(db)
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user_by_id(user_id, current_user, db)
    return UserResponse.model_validate(user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.update_user(user_id, data, current_user, db)
    return UserResponse.model_validate(user)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    await user_service.delete_user(user_id, db)

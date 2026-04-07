from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    email_verified: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, min_length=5, max_length=255)

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int

class ErrorResponse(BaseModel):
    detail: str

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

class SignupRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(...)

class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=255)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, max_length=255)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    email_verified: bool
    last_login_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class SignupResponse(BaseModel):
    message: str
    verification_token: Optional[str] = None
    user: UserResponse

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class MessageResponse(BaseModel):
    message: str

class TokenMessageResponse(BaseModel):
    message: str
    token: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str

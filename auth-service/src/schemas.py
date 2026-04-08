from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

class SignupRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)

class StartupOnboardingRequest(BaseModel):
    startup_name: str = Field(..., min_length=2, max_length=120)
    startup_slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    founder_email: EmailStr = Field(..., examples=["founder@example.com"])
    founder_password: str = Field(..., min_length=8, max_length=128)
    founder_name: str = Field(..., min_length=1, max_length=100)

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
    tenant_id: uuid.UUID
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

class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class StartupOnboardingResponse(BaseModel):
    message: str
    verification_token: Optional[str] = None
    tenant: TenantResponse
    founder: UserResponse

class MessageResponse(BaseModel):
    message: str

class TokenMessageResponse(BaseModel):
    message: str
    token: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str

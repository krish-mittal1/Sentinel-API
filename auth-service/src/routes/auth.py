from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple

from ..config import settings
from ..database import get_db
from ..schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenMessageResponse,
    UserResponse,
    VerifyEmailRequest,
)
from ..services import auth_service
from ..utils.email import send_email
from ..utils.exceptions import UnauthorizedError

router = APIRouter(tags=["Auth"])

def _client_meta(request: Request) -> Tuple[Optional[str], Optional[str]]:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent

@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    data: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    user, verification_token = await auth_service.signup(
        data,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    await send_email(
        to_email=user.email,
        subject="Verify your Sentinel account",
        text_body=(
            "Welcome to Sentinel.\n\n"
            f"Use this verification token to activate your account:\n{verification_token}\n"
        ),
    )
    return SignupResponse(
        message="Account created. Check your inbox for the verification token.",
        verification_token=verification_token if settings.AUTH_DEBUG_RETURN_TOKENS else None,
        user=UserResponse.model_validate(user),
    )

@router.post("/verify-email", response_model=AuthResponse)
async def verify_email(
    data: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    user, access_token, refresh_token = await auth_service.verify_email(
        data.token,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )

@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    user, access_token, refresh_token = await auth_service.login(
        data,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        redis=request.app.state.redis,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )

@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    data: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    user, access_token, refresh_token = await auth_service.refresh_access_token(
        data.refresh_token,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )

@router.post("/forgot-password", response_model=TokenMessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    token = await auth_service.forgot_password(
        data,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    if token:
        await send_email(
            to_email=data.email,
            subject="Reset your Sentinel password",
            text_body=(
                "A password reset was requested for your Sentinel account.\n\n"
                f"Use this reset token:\n{token}\n"
            ),
        )
    return TokenMessageResponse(
        message="If the account exists, a password reset message has been sent.",
        token=token if settings.AUTH_DEBUG_RETURN_TOKENS else None,
    )

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    await auth_service.reset_password(
        data.token,
        data.new_password,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    return MessageResponse(message="Password reset successful. Please log in again.")

@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_address, user_agent = _client_meta(request)
    await auth_service.logout(
        data.refresh_token,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        metrics=request.app.state.metrics,
    )
    await db.commit()
    return MessageResponse(message="Session logged out successfully.")

@router.get("/me", response_model=UserResponse)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    user = await auth_service.get_user_from_access_token(auth_header.split(" ", 1)[1], db)
    return UserResponse.model_validate(user)

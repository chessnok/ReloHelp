from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.cache import RedisCache, get_redis_client
from app.core.config import settings
from app.core.cookies import (
    delete_auth_cookies,
    set_access_token_cookie,
    set_csrf_token_cookie,
    set_refresh_token_cookie,
)
from app.core.dependencies import get_current_user, get_refresh_session
from app.core.email import email_service
from app.core.logger import logger
from app.core.rate_limit import check_login_rate_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    generate_email_verification_token,
    generate_password_reset_token,
    generate_refresh_token_value,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.models.email_verification import EmailVerificationToken
from app.db.models.password_reset import PasswordResetToken
from app.db.models.session import Session
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Register a new user."""
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        id=uuid4(),
        email=request.email,
        hashed_password=hash_password(request.password),
        is_active="active",
        roles=[],
    )

    db.add(user)
    await db.flush()

    # Create email verification token
    verification_token = generate_email_verification_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
    )

    email_token = EmailVerificationToken(
        id=uuid4(),
        user_id=user.id,
        token=verification_token,
        expires_at=expires_at,
    )

    db.add(email_token)
    await db.commit()

    logger.info(f"User registered: {user.email}")

    # Send verification email with token
    try:
        await email_service.send_verification_email(user.email, verification_token)
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        # We still return success, but log the error

    logger.info(f"Email verification token for {user.email}: {verification_token}")

    return {"message": "User registered successfully. Please verify your email."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Verify user email with token."""
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == request.token,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired",
        )

    # Mark token as used and verify user email
    token_record.used_at = datetime.now(timezone.utc)
    token_record.user.email_is_verified = True

    await db.commit()

    logger.info(f"Email verified for user: {token_record.user.email}")

    return {"message": "Email verified successfully"}


@router.post("/verify-email/resend", status_code=status.HTTP_200_OK)
async def resend_verification_email(
    request: PasswordForgotRequest,  # Reusing this schema as it only has email
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Resend email verification token."""
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user:
        # Don't reveal if user exists
        return {
            "message": "If the email exists and is not verified, a verification link has been sent."
        }

    if user.email_is_verified:
        return {
            "message": "If the email exists and is not verified, a verification link has been sent."
        }

    # Check for existing valid token
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > datetime.now(timezone.utc),
        )
    )
    existing_token = result.scalars().first()

    if existing_token:
        verification_token = existing_token.token
    else:
        # Create new token
        verification_token = generate_email_verification_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )

        email_token = EmailVerificationToken(
            id=uuid4(),
            user_id=user.id,
            token=verification_token,
            expires_at=expires_at,
        )

        db.add(email_token)
        await db.commit()

    # Send email
    try:
        await email_service.send_verification_email(user.email, verification_token)
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")

    logger.info(f"Resent verification token for {user.email}")

    return {
        "message": "If the email exists and is not verified, a verification link has been sent."
    }


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LoginResponse)
async def login(
    request: LoginRequest,
    response: Response,
    http_request: Request = None,
    db: AsyncSession = Depends(get_db_session),
    redis_client: RedisCache = Depends(get_redis_client),
) -> LoginResponse:
    """Login user and set authentication cookies."""
    # Rate limiting
    await check_login_rate_limit(redis_client, http_request, request.email)

    # Find user
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.is_active != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Create session
    session_id = uuid4()
    refresh_token_random = generate_refresh_token_value()
    refresh_token_value = create_refresh_token(session_id, refresh_token_random)
    refresh_token_hash = hash_refresh_token(refresh_token_random)

    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    session = Session(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at,
        ip=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent"),
    )

    db.add(session)
    await db.commit()

    # Create access token
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
        jti=session_id,
    )

    # Set cookies
    set_access_token_cookie(response, access_token)
    set_refresh_token_cookie(response, refresh_token_value)

    # Generate and set CSRF token
    csrf_token = generate_csrf_token()
    set_csrf_token_cookie(response, csrf_token)

    logger.info(f"User logged in: {user.email}")

    return LoginResponse(user=UserResponse.model_validate(user))


@router.post("/token/refresh", status_code=status.HTTP_200_OK)
async def refresh_token(
    response: Response,
    session_data: tuple[Session, str] = Depends(get_refresh_session),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Refresh access token with refresh token rotation."""
    session, _ = session_data  # Hash already verified in dependency

    # Update last_used_at for current session
    session.last_used_at = datetime.now(timezone.utc)

    # Create new session (rotation)
    new_session_id = uuid4()
    new_refresh_token_random = generate_refresh_token_value()
    new_refresh_token_value = create_refresh_token(
        new_session_id, new_refresh_token_random
    )
    new_refresh_token_hash = hash_refresh_token(new_refresh_token_random)

    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Update session (mark old as revoked and create new)
    session.revoked_at = datetime.now(timezone.utc)

    new_session = Session(
        id=new_session_id,
        user_id=session.user_id,
        refresh_token_hash=new_refresh_token_hash,
        expires_at=expires_at,
        rotation_counter=session.rotation_counter + 1,
        ip=session.ip,
        user_agent=session.user_agent,
    )

    db.add(new_session)
    await db.commit()

    # Get user for access token
    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one()

    # Create new access token
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
        jti=new_session_id,
    )

    # Set new cookies
    set_access_token_cookie(response, access_token)
    set_refresh_token_cookie(response, new_refresh_token_value)

    logger.info(f"Token refreshed for user: {user.email}")

    return {"message": "Token refreshed successfully"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session_data: tuple[Session, str] = Depends(get_refresh_session),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Logout user and revoke session."""
    session, _ = session_data
    # Revoke session
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    # Delete cookies
    delete_auth_cookies(response)

    logger.info(f"User logged out: session {session.id}")

    return None


@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get current user information."""
    return UserResponse.model_validate(current_user)


@router.get(
    "/sessions", status_code=status.HTTP_200_OK, response_model=list[SessionResponse]
)
async def get_user_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    """Get all active sessions for current user."""
    result = await db.execute(
        select(Session).where(
            Session.user_id == current_user.id,
            Session.revoked_at.is_(None),
            Session.expires_at > datetime.now(timezone.utc),
        )
    )
    sessions = result.scalars().all()

    return [SessionResponse.model_validate(session) for session in sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a specific session."""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"Session revoked: {session_id}")

    return None


@router.post("/password/forgot", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: PasswordForgotRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Request password reset."""
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Don't reveal if user exists (security best practice)
    if not user:
        return {"message": "If the email exists, a password reset link has been sent."}

    # Create password reset token
    reset_token = generate_password_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )

    password_reset = PasswordResetToken(
        id=uuid4(),
        user_id=user.id,
        token=reset_token,
        expires_at=expires_at,
    )

    db.add(password_reset)
    await db.commit()

    logger.info(f"Password reset requested for: {user.email}")

    # Send password reset email
    try:
        await email_service.send_password_reset_email(user.email, reset_token)
    except Exception as e:
        logger.error(f"Failed to send password reset email: {e}")
        # We still return success to avoid enumeration, but log the error

    logger.info(f"Password reset token for {user.email}: {reset_token}")

    return {"message": "If the email exists, a password reset link has been sent."}


@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Reset password with token."""
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == request.token,
            PasswordResetToken.used_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if token_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )

    # Update password
    token_record.user.hashed_password = hash_password(request.new_password)
    token_record.used_at = datetime.now(timezone.utc)

    # Revoke all sessions (force re-login)
    sessions_result = await db.execute(
        select(Session).where(
            Session.user_id == token_record.user_id,
            Session.revoked_at.is_(None),
        )
    )
    sessions = sessions_result.scalars().all()
    for session in sessions:
        session.revoked_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(f"Password reset for user: {token_record.user.email}")

    return {"message": "Password reset successfully"}

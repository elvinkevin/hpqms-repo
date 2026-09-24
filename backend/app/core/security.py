from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)


# ---------------------------------------------------------
# PASSWORDS
# ---------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


# ---------------------------------------------------------
# JWT CREATION
# ---------------------------------------------------------

def _create_token(
    payload: dict[str, Any],
    expires_delta: timedelta,
    token_type: str,
) -> str:

    to_encode = payload.copy()

    to_encode.update(
        {
            "type": token_type,
            "exp": datetime.now(timezone.utc) + expires_delta,
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_access_token(payload: dict[str, Any]) -> str:
    return _create_token(
        payload=payload,
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        token_type="access",
    )


def create_refresh_token(staff_id: str) -> str:
    return _create_token(
        payload={"sub": staff_id},
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        token_type="refresh",
    )


def create_admin_setup_token(staff_id: str) -> str:
    """Issue a short-lived token that can only complete initial admin setup."""
    return _create_token(
        payload={"sub": staff_id, "scope": "admin_setup"},
        expires_delta=timedelta(minutes=15),
        token_type="admin_setup",
    )


def create_password_change_token(staff_id: str) -> str:
    """Issue a short-lived token restricted to changing a temporary password."""
    return _create_token(
        payload={"sub": staff_id, "scope": "password_change"},
        expires_delta=timedelta(minutes=15),
        token_type="password_change",
    )


# ---------------------------------------------------------
# JWT DECODING
# ---------------------------------------------------------

def _decode_token(token: str) -> dict[str, Any]:

    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_access_token(token: str) -> dict[str, Any]:

    payload = _decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required.",
        )

    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:

    payload = _decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
        )

    return payload


def decode_admin_setup_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    if (
        payload.get("type") != "admin_setup"
        or payload.get("scope") != "admin_setup"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator setup token required.",
        )
    return payload


def decode_password_change_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    if (
        payload.get("type") != "password_change"
        or payload.get("scope") != "password_change"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password change token required.",
        )
    return payload

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config import settings


def create_access_token(agent_id: str, scopes: list[str]) -> str:
    """Create a JWT access token with agent_id as subject and scopes."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": agent_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Verify and decode a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

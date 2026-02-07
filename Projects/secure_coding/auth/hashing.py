import hashlib
import secrets

from config import settings


def generate_api_key() -> str:
    """Generate a random API key with the configured prefix."""
    random_part = secrets.token_hex(32)
    return f"{settings.API_KEY_PREFIX}{random_part}"


def hash_api_key(raw_key: str) -> str:
    """Hash an API key using SHA-256. Returns hex digest."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def get_key_prefix(raw_key: str) -> str:
    """Extract the first 8 characters of a raw key for identification."""
    return raw_key[:8]

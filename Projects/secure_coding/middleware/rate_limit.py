import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding window rate limiter.

    - /auth/token: limited per IP
    - All other endpoints: limited per IP (per agent_id would require parsing JWT here)
    """

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, list[float]] = defaultdict(list)

    def reset(self):
        """Clear all rate limit windows. Useful for testing."""
        self._windows.clear()

    def _check_rate(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        timestamps = self._windows[key]
        # Remove expired entries
        self._windows[key] = [t for t in timestamps if now - t < window_seconds]
        if len(self._windows[key]) >= max_requests:
            return False
        self._windows[key].append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if path == "/auth/token" and request.method == "POST":
            if not self._check_rate(f"auth:{ip}", settings.RATE_LIMIT_AUTH_PER_MINUTE):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for authentication",
                )
        elif not path.startswith("/_") and not path.startswith("/docs") and not path.startswith("/openapi"):
            if not self._check_rate(f"api:{ip}", settings.RATE_LIMIT_API_PER_MINUTE):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )

        return await call_next(request)

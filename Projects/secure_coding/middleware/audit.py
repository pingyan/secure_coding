import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class AuditMiddleware(BaseHTTPMiddleware):
    """Logs request/response metadata for observability."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)

        # Add timing header to every response
        response.headers["X-Request-Duration-Ms"] = str(duration_ms)

        return response

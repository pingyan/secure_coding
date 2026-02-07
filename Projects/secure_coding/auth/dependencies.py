from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from auth.jwt import verify_jwt

bearer_scheme = HTTPBearer()


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Extract and verify JWT from Authorization header.
    Returns dict with 'agent_id' and 'scopes'.
    """
    token = credentials.credentials
    try:
        payload = verify_jwt(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    agent_id = payload.get("sub")
    scopes = payload.get("scopes", [])
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return {"agent_id": agent_id, "scopes": scopes}


def require_capability(required: str):
    """Return a dependency that checks the JWT scopes for a required capability.
    The 'admin:*' scope bypasses all capability checks.
    """

    async def _check(current_agent: dict = Depends(get_current_agent)) -> dict:
        scopes = current_agent.get("scopes", [])
        if "admin:*" in scopes or required in scopes:
            return current_agent
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required capability: {required}",
        )

    return _check

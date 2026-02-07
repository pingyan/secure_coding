from fastapi import FastAPI

from database import Base, engine
from middleware.audit import AuditMiddleware
from middleware.rate_limit import RateLimitMiddleware
from routers import agents, api_keys, audit, auth, capabilities

# Import models so Base.metadata sees all tables
import models  # noqa: F401

app = FastAPI(title="Agent Identity Management System", version="1.0.0")

# Middleware (order matters: last added = first executed)
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)

# Routers
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(api_keys.router)
app.include_router(capabilities.router)
app.include_router(audit.router)

# Create tables
Base.metadata.create_all(bind=engine)


@app.get("/_health", tags=["health"])
async def health_check():
    return {"status": "ok"}

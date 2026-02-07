import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from middleware.rate_limit import RateLimitMiddleware
from auth.hashing import generate_api_key, get_key_prefix, hash_api_key
from models.agent import Agent
from models.api_key import ApiKey
from models.capability import AgentCapability, Capability

TEST_DB_URL = "sqlite:///./test_aims.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _get_rate_limiter():
    """Find the RateLimitMiddleware instance in the app middleware stack."""
    middleware = app.middleware_stack
    while middleware:
        if isinstance(middleware, RateLimitMiddleware):
            return middleware
        middleware = getattr(middleware, "app", None)
    return None


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after. Reset rate limiter."""
    Base.metadata.create_all(bind=engine)
    rl = _get_rate_limiter()
    if rl:
        rl.reset()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


DEFAULT_CAPABILITIES = [
    ("agents:read", "Read agent information"),
    ("agents:write", "Create and update agents"),
    ("keys:manage", "Create, rotate, and revoke API keys"),
    ("audit:read", "Read audit logs"),
    ("admin:*", "Full administrative access"),
]


@pytest.fixture
def admin_setup(db):
    """Create admin agent with all capabilities and return (agent, raw_api_key)."""
    cap_objects = {}
    for name, desc in DEFAULT_CAPABILITIES:
        cap = Capability(name=name, description=desc)
        db.add(cap)
        db.flush()
        cap_objects[name] = cap

    admin = Agent(
        name="admin",
        description="Test admin",
        owner="system",
        agent_type="orchestrator",
    )
    db.add(admin)
    db.flush()

    for cap in cap_objects.values():
        grant = AgentCapability(
            agent_id=admin.id,
            capability_id=cap.id,
            granted_by="system",
        )
        db.add(grant)

    raw_key = generate_api_key()
    api_key = ApiKey(
        agent_id=admin.id,
        key_prefix=get_key_prefix(raw_key),
        key_hash=hash_api_key(raw_key),
        name="test-admin-key",
    )
    db.add(api_key)
    db.commit()

    return admin, raw_key


@pytest.fixture
def admin_token(client, admin_setup):
    """Get a JWT for the admin agent."""
    _, raw_key = admin_setup
    resp = client.post("/auth/token", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    """Authorization headers with admin JWT."""
    return {"Authorization": f"Bearer {admin_token}"}

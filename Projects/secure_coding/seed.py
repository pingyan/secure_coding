"""Bootstrap script: creates admin agent, default capabilities, and first API key."""

from database import Base, SessionLocal, engine
from auth.hashing import generate_api_key, get_key_prefix, hash_api_key
from models.agent import Agent
from models.api_key import ApiKey
from models.capability import AgentCapability, Capability

# Import all models so tables are registered
import models  # noqa: F401

DEFAULT_CAPABILITIES = [
    ("agents:read", "Read agent information"),
    ("agents:write", "Create and update agents"),
    ("keys:manage", "Create, rotate, and revoke API keys"),
    ("audit:read", "Read audit logs"),
    ("admin:*", "Full administrative access"),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if admin already exists
        existing = db.query(Agent).filter(Agent.name == "admin").first()
        if existing:
            print("Admin agent already exists. Skipping seed.")
            return

        # Create capabilities
        cap_objects = {}
        for name, desc in DEFAULT_CAPABILITIES:
            cap = Capability(name=name, description=desc)
            db.add(cap)
            db.flush()
            cap_objects[name] = cap

        # Create admin agent
        admin = Agent(
            name="admin",
            description="System administrator agent",
            owner="system",
            agent_type="orchestrator",
        )
        db.add(admin)
        db.flush()

        # Grant all capabilities to admin
        for cap in cap_objects.values():
            grant = AgentCapability(
                agent_id=admin.id,
                capability_id=cap.id,
                granted_by="system",
            )
            db.add(grant)

        # Create first API key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        prefix = get_key_prefix(raw_key)

        api_key = ApiKey(
            agent_id=admin.id,
            key_prefix=prefix,
            key_hash=key_hash,
            name="admin-bootstrap",
        )
        db.add(api_key)

        db.commit()

        print("=" * 60)
        print("AIMS Bootstrap Complete")
        print("=" * 60)
        print(f"Admin Agent ID: {admin.id}")
        print(f"Admin API Key:  {raw_key}")
        print()
        print("SAVE THIS KEY - it will not be shown again!")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    seed()

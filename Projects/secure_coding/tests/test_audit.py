def test_query_audit_logs(client, auth_headers):
    # The admin_setup and token exchange already generate audit events
    resp = client.get("/audit", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # At least the token exchange log


def test_query_audit_logs_filter_by_action(client, auth_headers):
    resp = client.get("/audit?action=auth.token_issued", headers=auth_headers)
    assert resp.status_code == 200
    for entry in resp.json():
        assert entry["action"] == "auth.token_issued"


def test_query_audit_logs_pagination(client, auth_headers):
    resp = client.get("/audit?limit=1&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 1


def test_audit_trail_on_agent_creation(client, auth_headers):
    # Create an agent
    client.post(
        "/agents",
        json={"name": "audit-test-agent", "owner": "tester"},
        headers=auth_headers,
    )

    # Check audit log
    resp = client.get("/audit?action=agent.created", headers=auth_headers)
    assert resp.status_code == 200
    logs = resp.json()
    created_logs = [l for l in logs if "audit-test-agent" in l.get("details_json", "")]
    assert len(created_logs) >= 1


def test_audit_log_forbidden_without_capability(client, admin_setup, db):
    """Create an agent with limited capabilities and verify audit access is denied."""
    from auth.hashing import generate_api_key, get_key_prefix, hash_api_key
    from models.agent import Agent
    from models.api_key import ApiKey
    from models.capability import AgentCapability, Capability

    # Create agent with only agents:read
    agent = Agent(name="limited-agent", owner="tester", agent_type="llm")
    db.add(agent)
    db.flush()

    cap = db.query(Capability).filter(Capability.name == "agents:read").first()
    grant = AgentCapability(agent_id=agent.id, capability_id=cap.id, granted_by="system")
    db.add(grant)

    raw_key = generate_api_key()
    api_key = ApiKey(
        agent_id=agent.id,
        key_prefix=get_key_prefix(raw_key),
        key_hash=hash_api_key(raw_key),
        name="limited-key",
    )
    db.add(api_key)
    db.commit()

    # Get JWT for limited agent
    resp = client.post("/auth/token", headers={"X-API-Key": raw_key})
    token = resp.json()["access_token"]

    # Try audit endpoint - should be forbidden
    resp = client.get("/audit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403

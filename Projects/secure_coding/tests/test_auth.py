def test_health_check(client):
    resp = client.get("/_health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_token_exchange_valid_key(client, admin_setup):
    _, raw_key = admin_setup
    resp = client.post("/auth/token", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_token_exchange_invalid_key(client, admin_setup):
    resp = client.post("/auth/token", headers={"X-API-Key": "aims_invalidkey123"})
    assert resp.status_code == 401


def test_token_exchange_revoked_key(client, admin_setup, db):
    admin, raw_key = admin_setup
    from models.api_key import ApiKey
    key = db.query(ApiKey).filter(ApiKey.agent_id == admin.id).first()
    key.status = "revoked"
    db.commit()

    resp = client.post("/auth/token", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401


def test_token_exchange_suspended_agent(client, admin_setup, db):
    admin, raw_key = admin_setup
    admin.status = "suspended"
    db.commit()

    resp = client.post("/auth/token", headers={"X-API-Key": raw_key})
    assert resp.status_code == 403


def test_protected_endpoint_no_token(client, admin_setup):
    resp = client.get("/agents")
    assert resp.status_code == 403


def test_protected_endpoint_invalid_token(client, admin_setup):
    resp = client.get("/agents", headers={"Authorization": "Bearer invalidtoken"})
    assert resp.status_code == 401

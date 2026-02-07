def test_create_api_key(client, auth_headers):
    # Create an agent first
    resp = client.post(
        "/agents",
        json={"name": "key-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "test-key"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "raw_key" in data
    assert data["raw_key"].startswith("aims_")
    assert data["name"] == "test-key"
    assert data["status"] == "active"


def test_list_api_keys(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "list-key-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "key1"},
        headers=auth_headers,
    )
    client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "key2"},
        headers=auth_headers,
    )

    resp = client.get(f"/agents/{agent_id}/keys", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Ensure raw key is NOT in list response
    for key in data:
        assert "raw_key" not in key


def test_rotate_api_key(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "rotate-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "rotate-key"},
        headers=auth_headers,
    )
    key_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/keys/{key_id}/rotate",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["old_key_id"] == key_id
    assert "new_key" in data
    assert data["new_key"]["raw_key"].startswith("aims_")
    assert data["grace_period_hours"] > 0


def test_rotate_non_active_key_fails(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "rot-fail-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "rot-key"},
        headers=auth_headers,
    )
    key_id = resp.json()["id"]

    # Rotate once
    client.post(f"/agents/{agent_id}/keys/{key_id}/rotate", headers=auth_headers)

    # Try rotating the now-rotated key
    resp = client.post(f"/agents/{agent_id}/keys/{key_id}/rotate", headers=auth_headers)
    assert resp.status_code == 400


def test_revoke_api_key(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "rev-key-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/keys",
        json={"name": "rev-key"},
        headers=auth_headers,
    )
    key_id = resp.json()["id"]

    resp = client.delete(f"/agents/{agent_id}/keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify key is revoked
    resp = client.get(f"/agents/{agent_id}/keys", headers=auth_headers)
    keys = resp.json()
    revoked_key = [k for k in keys if k["id"] == key_id][0]
    assert revoked_key["status"] == "revoked"


def test_create_key_for_nonexistent_agent(client, auth_headers):
    resp = client.post(
        "/agents/nonexistent-id/keys",
        json={"name": "bad-key"},
        headers=auth_headers,
    )
    assert resp.status_code == 404

def test_create_capability(client, auth_headers):
    resp = client.post(
        "/capabilities",
        json={"name": "test:cap", "description": "A test capability"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test:cap"


def test_create_duplicate_capability(client, auth_headers):
    client.post(
        "/capabilities",
        json={"name": "dup:cap"},
        headers=auth_headers,
    )
    resp = client.post(
        "/capabilities",
        json={"name": "dup:cap"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_list_capabilities(client, auth_headers):
    resp = client.get("/capabilities", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # Should have the default capabilities from admin_setup
    assert len(resp.json()) >= 5


def test_grant_capability(client, auth_headers, db):
    # Create agent
    resp = client.post(
        "/agents",
        json={"name": "cap-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    # Get an existing capability
    resp = client.get("/capabilities", headers=auth_headers)
    cap_id = resp.json()[0]["id"]

    resp = client.post(
        f"/agents/{agent_id}/capabilities",
        json={"capability_id": cap_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_grant_duplicate_capability(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "dup-cap-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.get("/capabilities", headers=auth_headers)
    cap_id = resp.json()[0]["id"]

    client.post(
        f"/agents/{agent_id}/capabilities",
        json={"capability_id": cap_id},
        headers=auth_headers,
    )
    resp = client.post(
        f"/agents/{agent_id}/capabilities",
        json={"capability_id": cap_id},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_grant_self_capability_fails(client, auth_headers, admin_setup):
    admin, _ = admin_setup
    resp = client.get("/capabilities", headers=auth_headers)
    cap_id = resp.json()[0]["id"]

    resp = client.post(
        f"/agents/{admin.id}/capabilities",
        json={"capability_id": cap_id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_revoke_capability(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "revoke-cap-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.get("/capabilities", headers=auth_headers)
    cap_id = resp.json()[0]["id"]

    client.post(
        f"/agents/{agent_id}/capabilities",
        json={"capability_id": cap_id},
        headers=auth_headers,
    )
    resp = client.delete(
        f"/agents/{agent_id}/capabilities/{cap_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


def test_revoke_self_capability_fails(client, auth_headers, admin_setup):
    admin, _ = admin_setup
    resp = client.get("/capabilities", headers=auth_headers)
    cap_id = resp.json()[0]["id"]

    resp = client.delete(
        f"/agents/{admin.id}/capabilities/{cap_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 400

def test_create_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "test-agent", "owner": "tester", "agent_type": "llm"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["status"] == "active"
    assert data["agent_type"] == "llm"


def test_create_agent_duplicate_name(client, auth_headers):
    client.post(
        "/agents",
        json={"name": "dup-agent", "owner": "tester"},
        headers=auth_headers,
    )
    resp = client.post(
        "/agents",
        json={"name": "dup-agent", "owner": "tester"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_create_agent_invalid_name(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "bad name!", "owner": "tester"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_list_agents(client, auth_headers):
    resp = client.get("/agents", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_agents_filter_by_status(client, auth_headers):
    client.post(
        "/agents",
        json={"name": "filter-agent", "owner": "tester"},
        headers=auth_headers,
    )
    resp = client.get("/agents?status=active", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "get-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.get(f"/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-agent"


def test_get_agent_not_found(client, auth_headers):
    resp = client.get("/agents/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


def test_update_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "upd-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.patch(
        f"/agents/{agent_id}",
        json={"description": "Updated description"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"


def test_suspend_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "sus-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/suspend",
        json={"reason": "Testing suspension"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


def test_suspend_self_fails(client, auth_headers, admin_setup):
    admin, _ = admin_setup
    resp = client.post(
        f"/agents/{admin.id}/suspend",
        json={"reason": "Self suspend"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_reactivate_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "react-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    client.post(
        f"/agents/{agent_id}/suspend",
        json={"reason": "Testing"},
        headers=auth_headers,
    )
    resp = client.post(f"/agents/{agent_id}/reactivate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_reactivate_non_suspended_fails(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "active-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(f"/agents/{agent_id}/reactivate", headers=auth_headers)
    assert resp.status_code == 400


def test_revoke_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "rev-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.post(
        f"/agents/{agent_id}/revoke",
        json={"reason": "Testing revocation"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


def test_revoke_self_fails(client, auth_headers, admin_setup):
    admin, _ = admin_setup
    resp = client.post(
        f"/agents/{admin.id}/revoke",
        json={"reason": "Self revoke"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_delete_agent(client, auth_headers):
    resp = client.post(
        "/agents",
        json={"name": "del-agent", "owner": "tester"},
        headers=auth_headers,
    )
    agent_id = resp.json()["id"]

    resp = client.delete(f"/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/agents/{agent_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_self_fails(client, auth_headers, admin_setup):
    admin, _ = admin_setup
    resp = client.delete(f"/agents/{admin.id}", headers=auth_headers)
    assert resp.status_code == 400

"""
RBAC Permission Matrix Tests
Verifies that DEVELOPER receives 403 on dispute overrides and user creation,
while MANAGER and MASTER_ADMIN hold appropriate permissions.
"""

import uuid

from src.core.auth import UserRole, create_access_token
from src.core.ledger import append_compliance_record


def _create_token(org_id: str, role: UserRole, email: str) -> str:
    return create_access_token(
        {
            "id": str(uuid.uuid4()),
            "sub": email,
            "email": email,
            "org_id": org_id,
            "role": role.value,
            "org_name": "Test RBAC Org",
        }
    )


def test_developer_role_forbidden_on_override(client, test_organization):
    org_id = test_organization["id"]
    dev_token = _create_token(org_id, UserRole.DEVELOPER, "dev@test.org")

    # Seed an audit record in the org ledger to dispute
    audit_receipt = append_compliance_record(
        user_query="Biometric authorization testing",
        payload={"is_compliant": False, "risk_category": "High-Risk"},
        org_id=org_id,
    )
    assert audit_receipt is not None
    audit_id = audit_receipt["audit_id"]

    # Developer attempts override -> must return 403 Forbidden
    response = client.post(
        "/api/v1/override",
        json={
            "audit_id": audit_id,
            "justification": "Developer trying to override high-risk decision without compliance authorization",
        },
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert response.status_code == 403
    assert "DEVELOPER" in response.json().get("detail", "")


def test_developer_role_forbidden_on_user_creation(client, test_organization):
    org_id = test_organization["id"]
    dev_token = _create_token(org_id, UserRole.DEVELOPER, "dev@test.org")

    response = client.post(
        "/api/v1/auth/create-user",
        json={"email": "another_dev@test.org", "password": "Password123!", "role": "DEVELOPER"},
        headers={"Authorization": f"Bearer {dev_token}"},
    )
    assert response.status_code == 403


def test_manager_role_can_override_but_cannot_create_users(client, test_organization):
    org_id = test_organization["id"]
    mgr_token = _create_token(org_id, UserRole.MANAGER, "mgr@test.org")

    # Seed an audit record
    audit_receipt = append_compliance_record(
        user_query="Cross-border EMT settlement",
        payload={"is_compliant": False, "risk_category": "Pending Clarification"},
        org_id=org_id,
    )
    assert audit_receipt is not None
    audit_id = audit_receipt["audit_id"]

    # Manager can override -> 200 OK
    override_resp = client.post(
        "/api/v1/override",
        json={
            "audit_id": audit_id,
            "justification": "Compliance manager exemption under MiCA Article 50 transitional provision",
        },
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert override_resp.status_code == 200
    assert override_resp.json()["status"] == "OVERRIDDEN_BY_HUMAN"

    # Manager cannot create users -> 403 Forbidden
    create_user_resp = client.post(
        "/api/v1/auth/create-user",
        json={"email": "newbie@test.org", "password": "Password123!", "role": "DEVELOPER"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert create_user_resp.status_code == 403


def test_master_admin_permissions(client, test_organization):
    org_id = test_organization["id"]
    admin_token = _create_token(org_id, UserRole.MASTER_ADMIN, "admin@test.org")

    # Admin can create user
    create_resp = client.post(
        "/api/v1/auth/create-user",
        json={"email": f"dev_{uuid.uuid4().hex[:6]}@test.org", "password": "SecurePassword123!", "role": "DEVELOPER"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201

    # Admin can view organization users
    users_resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert users_resp.status_code == 200
    data = users_resp.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    assert len(data["users"]) >= 1


def test_unauthenticated_requests_rejected(client):
    client.cookies.clear()
    assert client.get("/api/v1/ledger").status_code == 401
    assert (
        client.post("/api/v1/override", json={"audit_id": str(uuid.uuid4()), "justification": "none"}).status_code
        == 401
    )

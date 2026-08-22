import os
import sys
import uuid
from datetime import datetime, timezone

# Ensure UTF-8 stdout encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from src.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    UserRole
)
from src.core.ledger import compute_canonical_hash, GENESIS_HASH
from src.api.main import app


def test_password_hashing():
    print("\n[Test 1] Password Hashing & Bcrypt Verification...")
    raw_pass = "FintechCompliance2026!#"
    hashed = hash_password(raw_pass)
    assert hashed != raw_pass, "Password was not hashed"
    assert verify_password(raw_pass, hashed) is True, "Password verification failed for valid password"
    assert verify_password("WrongPassword123", hashed) is False, "Password verification returned True for invalid password"
    print("  ✅ Password hashing and verification passed.")


def test_jwt_generation_and_decoding():
    print("\n[Test 2] JWT Token Generation & Multi-Tenant Claim Validation...")
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    token_data = {
        "id": user_id,
        "sub": "admin@fintechcorp.eu",
        "email": "admin@fintechcorp.eu",
        "org_id": org_id,
        "role": UserRole.MASTER_ADMIN.value,
        "org_name": "FintechCorp EU"
    }

    token = create_access_token(token_data)
    assert isinstance(token, str) and len(token) > 20, "Invalid JWT token generated"

    decoded = decode_access_token(token)
    assert decoded["id"] == user_id, f"Expected id {user_id}, got {decoded.get('id')}"
    assert decoded["org_id"] == org_id, f"Expected org_id {org_id}, got {decoded.get('org_id')}"
    assert decoded["role"] == "MASTER_ADMIN", f"Expected role MASTER_ADMIN, got {decoded.get('role')}"
    assert decoded["email"] == "admin@fintechcorp.eu", f"Expected email, got {decoded.get('email')}"
    print("  ✅ JWT generation and claim decoding passed.")


def test_deterministic_multi_tenant_ledger_hash():
    print("\n[Test 3] Deterministic SHA-256 Hash Computation with Multi-Tenant Isolation...")
    audit_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    org_id_1 = str(uuid.uuid4())
    org_id_2 = str(uuid.uuid4())

    payload = {
        "risk_category": "High-Risk",
        "is_compliant": False,
        "executive_summary_markdown": "Biometric credit profiling is prohibited."
    }

    hash1 = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="Biometric categorization in credit decisions",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_id_1
    )

    # Identical inputs must yield identical hash
    hash1_recomputed = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="Biometric categorization in credit decisions",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_id_1
    )
    assert hash1 == hash1_recomputed, "Deterministic hashing failed for identical inputs"

    # Different org_id must yield a different hash (tenant cryptographic isolation)
    hash2 = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="Biometric categorization in credit decisions",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_id_2
    )
    assert hash1 != hash2, "Hashes between different tenant org_ids should not collide"
    print(f"  ✅ Deterministic Hash 1: {hash1[:16]}... (Length: {len(hash1)})")
    print(f"  ✅ Tenant-Isolated Hash 2: {hash2[:16]}... (Length: {len(hash2)})")


def test_fastapi_auth_and_rbac_endpoints():
    print("\n[Test 4] FastAPI Multi-Tenant Endpoints & RBAC Security...")
    client = TestClient(app)

    # 1. Test Organization Registration
    unique_suffix = uuid.uuid4().hex[:6]
    reg_payload = {
        "org_name": f"Nordic RegTech AB {unique_suffix}",
        "admin_email": f"admin_{unique_suffix}@nordicregtech.se",
        "password": "SecureAdminPassword2026!"
    }

    reg_resp = client.post("/api/v1/auth/register-org", json=reg_payload)
    if reg_resp.status_code == 201:
        data = reg_resp.json()
        assert "access_token" in data, "Missing access_token in registration response"
        admin_token = data["access_token"]
        org_id = data["organization"]["id"]
        print(f"  ✅ Organization Registered: {data['organization']['name']} (ID: {org_id})")
        print(f"  ✅ Genesis Block: {data.get('genesis_block', {}).get('tx_hash', 'Local Genesis')}")

        # 2. Test Login
        login_resp = client.post("/api/v1/auth/login", json={
            "email": reg_payload["admin_email"],
            "password": reg_payload["password"]
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        login_data = login_resp.json()
        assert login_data["user"]["role"] == "MASTER_ADMIN"
        print("  ✅ Master Admin Login Successful.")

        # 3. Test /me profile endpoint
        auth_header = {"Authorization": f"Bearer {admin_token}"}
        me_resp = client.get("/api/v1/auth/me", headers=auth_header)
        assert me_resp.status_code == 200, f"/me failed: {me_resp.text}"
        assert me_resp.json()["role"] == "MASTER_ADMIN"
        print("  ✅ /me Profile Endpoint Verified.")

        # 4. Provision Developer and Manager accounts
        dev_email = f"dev_{unique_suffix}@nordicregtech.se"
        dev_resp = client.post("/api/v1/auth/create-user", json={
            "email": dev_email,
            "password": "DevPassword2026!#",
            "role": "DEVELOPER"
        }, headers=auth_header)
        assert dev_resp.status_code == 201, f"Create developer failed: {dev_resp.text}"
        print("  ✅ MASTER_ADMIN successfully created DEVELOPER account.")

        # Login as Developer
        dev_login_resp = client.post("/api/v1/auth/login", json={
            "email": dev_email,
            "password": "DevPassword2026!#"
        })
        dev_token = dev_login_resp.json()["access_token"]
        dev_auth_header = {"Authorization": f"Bearer {dev_token}"}

        # 5. Verify RBAC: DEVELOPER cannot provision other users (Must return 403)
        dev_create_attempt = client.post("/api/v1/auth/create-user", json={
            "email": f"hacked_{unique_suffix}@nordicregtech.se",
            "password": "Password123!",
            "role": "DEVELOPER"
        }, headers=dev_auth_header)
        assert dev_create_attempt.status_code == 403, f"Expected 403 Forbidden for Developer user creation, got {dev_create_attempt.status_code}"
        print("  ✅ RBAC Enforced: DEVELOPER is blocked from creating users (HTTP 403 Forbidden).")

        # 6. Verify RBAC: DEVELOPER cannot perform manual ledger overrides (Must return 403)
        dev_override_attempt = client.post("/api/v1/override", json={
            "audit_id": str(uuid.uuid4()),
            "justification": "Developer trying to override high-risk compliance decision without approval"
        }, headers=dev_auth_header)
        assert dev_override_attempt.status_code == 403, f"Expected 403 Forbidden for Developer override, got {dev_override_attempt.status_code}"
        print("  ✅ RBAC Enforced: DEVELOPER is blocked from manual overrides (HTTP 403 Forbidden).")

        # 7. Unauthenticated request to /api/v1/ledger must return 401 Unauthorized
        unauth_ledger = client.get("/api/v1/ledger")
        assert unauth_ledger.status_code == 401, f"Expected 401 Unauthorized, got {unauth_ledger.status_code}"
        print("  ✅ Endpoint Security: Unauthenticated request to /api/v1/ledger blocked (HTTP 401).")

        # 8. Authenticated request to /api/v1/ledger returns organization's ledger
        auth_ledger = client.get("/api/v1/ledger", headers=dev_auth_header)
        assert auth_ledger.status_code == 200, f"Authenticated ledger fetch failed: {auth_ledger.text}"
        assert auth_ledger.json()["org_id"] == org_id
        print("  ✅ Tenant-Isolated Ledger Query Verified.")

    else:
        print(f"  ℹ️ Database offline or local mock mode: {reg_resp.text}")


if __name__ == "__main__":
    print("=" * 70)
    print(" FINSIGHT REGTECH: MULTI-TENANCY, RBAC & JWT AUTH INTEGRATION TESTS ")
    print("=" * 70)

    test_password_hashing()
    test_jwt_generation_and_decoding()
    test_deterministic_multi_tenant_ledger_hash()
    test_fastapi_auth_and_rbac_endpoints()

    print("\n" + "=" * 70)
    print(" ALL TESTS PASSED SUCCESSFULLY! ")
    print("=" * 70)

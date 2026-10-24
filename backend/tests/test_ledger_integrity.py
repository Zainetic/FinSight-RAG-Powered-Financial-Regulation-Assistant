"""
Ledger Chaining, Deterministic Hashing & Tamper Detection Tests
Verifies that modifying any single block breaks cryptographic verification,
and that hashes are deterministic with strict tenant isolation.
"""

import uuid
from datetime import UTC, datetime

from src.core.database import get_db_connection
from src.core.ledger import (
    GENESIS_HASH,
    append_compliance_record,
    compute_canonical_hash,
    create_genesis_block,
    override_ledger_record,
    verify_ledger_chain,
)


def test_deterministic_hashing_and_tenant_isolation():
    audit_id = uuid.uuid4()
    now_utc = datetime.now(UTC)
    org_1 = str(uuid.uuid4())
    org_2 = str(uuid.uuid4())
    payload = {"status": "COMPLIANT", "risk_category": "Minimal Risk"}

    hash_a = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="SEPA instant payment audit",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_1,
    )

    # Identical inputs must yield identical hash
    hash_a_recomputed = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="SEPA instant payment audit",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_1,
    )
    assert hash_a == hash_a_recomputed
    assert len(hash_a) == 64

    # Tenant isolation: different org_id must produce a different hash
    hash_b = compute_canonical_hash(
        audit_id=audit_id,
        timestamp_utc=now_utc,
        model_provenance="gemini-3.6-flash",
        user_query="SEPA instant payment audit",
        payload=payload,
        prev_hash=GENESIS_HASH,
        org_id=org_2,
    )
    assert hash_a != hash_b


def test_genesis_block_and_linear_chaining(test_organization):
    org_id = test_organization["id"]

    # 1. Anchor Genesis Block #0
    genesis = create_genesis_block(org_id, test_organization["name"], "admin@test.org")
    assert genesis is not None
    assert genesis["prev_hash"] == GENESIS_HASH
    assert genesis["is_genesis"] is True
    genesis_tx_hash = genesis["tx_hash"]

    # 2. Append Block #1
    rec1 = append_compliance_record(user_query="Audit 1", payload={"is_compliant": True, "turn": 1}, org_id=org_id)
    assert rec1 is not None
    assert rec1["prev_hash"] == genesis_tx_hash

    # 3. Append Block #2
    rec2 = append_compliance_record(user_query="Audit 2", payload={"is_compliant": False, "turn": 2}, org_id=org_id)
    assert rec2 is not None
    assert rec2["prev_hash"] == rec1["tx_hash"]

    # 4. Append Human Dispute Override Block #3
    override = override_ledger_record(
        audit_id=rec2["audit_id"],
        justification="Manual risk mitigation confirmed by compliance team",
        org_id=org_id,
        operator_email="admin@test.org",
    )
    assert override is not None
    assert override["prev_hash"] == rec2["tx_hash"]

    # 5. Full cryptographic verification of the 4-block chain
    is_valid, count, error_msg = verify_ledger_chain(org_id)
    assert is_valid is True, f"Chain verification failed: {error_msg}"
    assert count == 4
    assert error_msg is None


def test_tamper_detection_breaks_verification(test_organization):
    org_id = test_organization["id"]

    # Create Genesis + 2 records
    create_genesis_block(org_id, test_organization["name"], "admin@test.org")
    rec1 = append_compliance_record("Initial Audit", {"flag": "A"}, org_id=org_id)
    rec2 = append_compliance_record("Second Audit", {"flag": "B"}, org_id=org_id)

    # Initial chain must be valid
    is_valid, count, _ = verify_ledger_chain(org_id)
    assert is_valid is True
    assert count == 3

    # Tamper with Block 1 payload directly in PostgreSQL (simulating unauthorized DB tampering)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE compliance_ledger 
                SET payload = '{"flag": "TAMPERED_BY_ATTACKER"}'::jsonb
                WHERE audit_id = %s;
            """,
                (rec1["audit_id"],),
            )
        conn.commit()

    # Re-run verification -> Must immediately detect tampering at Block index 1
    tampered_valid, tampered_idx, error_msg = verify_ledger_chain(org_id)
    assert tampered_valid is False
    assert tampered_idx == 1
    assert "Tampered content at block index 1" in error_msg


def test_tampered_prev_hash_breaks_chain_link(test_organization):
    org_id = test_organization["id"]

    create_genesis_block(org_id, test_organization["name"], "admin@test.org")
    rec1 = append_compliance_record("Audit 1", {"data": 1}, org_id=org_id)
    rec2 = append_compliance_record("Audit 2", {"data": 2}, org_id=org_id)

    # Corrupt prev_hash of Block 2
    corrupted_hash = "f" * 64
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE compliance_ledger 
                SET prev_hash = %s
                WHERE audit_id = %s;
            """,
                (corrupted_hash, rec2["audit_id"]),
            )
        conn.commit()

    is_valid, broken_idx, error_msg = verify_ledger_chain(org_id)
    assert is_valid is False
    assert broken_idx == 2
    assert "Broken chain link at block index 2" in error_msg

import os
import sys
import json
import uuid
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
import psycopg2
from psycopg2.extras import Json, RealDictCursor

from src.core.database import get_db_connection, get_connection_pool, _db_initialized, init_db

# Genesis hash for the initial block in the chain (64 hex zeros)
GENESIS_HASH = "0" * 64
_ledger_lock = threading.Lock()
_ledger_table_initialized = False


def init_ledger_table() -> bool:
    """
    Initializes the PostgreSQL compliance_ledger table with SHA-256 hash chaining columns,
    org_id foreign key, and performance indexes.
    """
    global _ledger_table_initialized
    if _ledger_table_initialized:
        return True

    try:
        if init_db():
            _ledger_table_initialized = True
            return True
        return False
    except Exception as e:
        sys.stderr.write(f"[Ledger Error] Failed to initialize compliance_ledger table: {e}\n")
        return False


def compute_canonical_hash(
    audit_id: uuid.UUID,
    timestamp_utc: datetime,
    model_provenance: str,
    user_query: str,
    payload: Dict[str, Any],
    prev_hash: str,
    org_id: Optional[str] = None
) -> str:
    """
    Computes a deterministic SHA-256 hash of the record's canonical data.
    Keys are sorted and JSON is formatted deterministically without arbitrary whitespace.
    Includes org_id to ensure tenant cryptographic uniqueness.
    """
    canonical_dict = {
        "audit_id": str(audit_id),
        "model_provenance": str(model_provenance),
        "org_id": str(org_id) if org_id else "",
        "payload": payload,
        "prev_hash": str(prev_hash),
        "timestamp": timestamp_utc.isoformat(),
        "user_query": str(user_query)
    }

    canonical_bytes = json.dumps(
        canonical_dict,
        sort_keys=True,
        separators=(",", ":"),
        default=str
    ).encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


def append_compliance_record(
    user_query: str,
    payload: Dict[str, Any],
    model_provenance: Optional[str] = None,
    org_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Appends a new compliance judgment to the immutable PostgreSQL ledger:
    1. Locks the ledger table in EXCLUSIVE MODE to guarantee linear hash-chain integrity.
    2. Fetches the latest tx_hash for the specific organization to use as prev_hash.
    3. Computes the new deterministic SHA-256 tx_hash over canonical data.
    4. Inserts the record tied to the organization and commits the transaction.
    5. Returns the cryptographic receipt dictionary.
    """
    if not user_query or not payload:
        raise ValueError("user_query and payload must not be empty.")

    if not model_provenance:
        model_provenance = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    # Ensure table exists
    if not _ledger_table_initialized:
        if not init_ledger_table():
            return None

    audit_id = uuid.uuid4()
    timestamp_utc = datetime.now(timezone.utc)

    with _ledger_lock:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Acquire exclusive table lock within the transaction to prevent concurrent forks
                    cursor.execute("LOCK TABLE compliance_ledger IN EXCLUSIVE MODE;")

                    # 1. Fetch the tx_hash of the most recent ledger record FOR THIS SPECIFIC ORG
                    if org_id:
                        cursor.execute("""
                            SELECT tx_hash 
                            FROM compliance_ledger 
                            WHERE org_id = %s
                            ORDER BY timestamp DESC, audit_id DESC 
                            LIMIT 1;
                        """, (str(org_id),))
                    else:
                        cursor.execute("""
                            SELECT tx_hash 
                            FROM compliance_ledger 
                            WHERE org_id IS NULL
                            ORDER BY timestamp DESC, audit_id DESC 
                            LIMIT 1;
                        """)

                    row = cursor.fetchone()
                    prev_hash = row[0].strip() if row else GENESIS_HASH

                    # 2. Compute canonical SHA-256 hash for current record
                    tx_hash = compute_canonical_hash(
                        audit_id=audit_id,
                        timestamp_utc=timestamp_utc,
                        model_provenance=model_provenance,
                        user_query=user_query,
                        payload=payload,
                        prev_hash=prev_hash,
                        org_id=org_id
                    )

                    # 3. Insert the linked record into PostgreSQL
                    cursor.execute("""
                        INSERT INTO compliance_ledger 
                        (audit_id, org_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        str(audit_id),
                        str(org_id) if org_id else None,
                        timestamp_utc,
                        model_provenance,
                        user_query,
                        Json(payload),
                        prev_hash,
                        tx_hash
                    ))

                    conn.commit()

                    # 4. Return cryptographic receipt
                    receipt = {
                        "audit_id": str(audit_id),
                        "org_id": str(org_id) if org_id else None,
                        "timestamp": timestamp_utc.isoformat(),
                        "model_provenance": model_provenance,
                        "prev_hash": prev_hash,
                        "tx_hash": tx_hash,
                        "is_genesis": (prev_hash == GENESIS_HASH),
                        "status": "SECURED_IMMUTABLE"
                    }
                    return receipt

        except Exception as e:
            sys.stderr.write(f"[Ledger Error] Failed to append record to hash chain: {e}\n")
            return None


def create_genesis_block(
    org_id: str,
    org_name: str,
    admin_email: str
) -> Optional[Dict[str, Any]]:
    """
    Generates and anchors the initial 'Genesis Block' (Block #0) for a newly registered organization.
    Prev_hash is guaranteed to be 64 zeros, anchoring the organization's independent ledger chain.
    """
    genesis_payload = {
        "event": "GENESIS_BLOCK_INITIALIZATION",
        "org_id": str(org_id),
        "org_name": org_name,
        "admin_email": admin_email,
        "description": f"Initial Genesis Block for {org_name} regulatory compliance audit ledger.",
        "status": "INITIALIZED"
    }

    user_query = f"GENESIS INITIALIZATION [{org_name}]"
    model_provenance = "SYSTEM_GENESIS_INITIALIZER"

    return append_compliance_record(
        user_query=user_query,
        payload=genesis_payload,
        model_provenance=model_provenance,
        org_id=str(org_id)
    )


def override_ledger_record(
    audit_id: str,
    justification: str,
    org_id: Optional[str] = None,
    operator_email: Optional[str] = None,
    model_provenance: str = "HUMAN_OPERATOR"
) -> Optional[Dict[str, Any]]:
    """
    Implements the 'Human-in-the-Loop' dispute protocol:
    1. Validates that the original audit record exists within the tenant's organization.
    2. Does NOT modify or delete the original row.
    3. Inserts a new dispute record linked to the latest tx_hash in the organization's chain.
    4. Sets payload status to 'OVERRIDDEN_BY_HUMAN' with the operator's justification.
    5. Computes and returns the new SHA-256 cryptographic receipt.
    """
    if not audit_id or not justification or not justification.strip():
        raise ValueError("Both audit_id and justification must be provided.")

    if not _ledger_table_initialized:
        if not init_ledger_table():
            return None

    new_audit_id = uuid.uuid4()
    timestamp_utc = datetime.now(timezone.utc)

    with _ledger_lock:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Lock table to prevent race conditions during dispute block creation
                    cursor.execute("LOCK TABLE compliance_ledger IN EXCLUSIVE MODE;")

                    # 1. Fetch the original record and verify tenant isolation
                    if org_id:
                        cursor.execute("""
                            SELECT user_query, payload, org_id 
                            FROM compliance_ledger 
                            WHERE audit_id = %s AND (org_id = %s OR org_id IS NULL);
                        """, (str(audit_id), str(org_id)))
                    else:
                        cursor.execute("""
                            SELECT user_query, payload, org_id 
                            FROM compliance_ledger 
                            WHERE audit_id = %s;
                        """, (str(audit_id),))

                    orig_row = cursor.fetchone()
                    if not orig_row:
                        raise ValueError(f"Audit record '{audit_id}' not found in organization's ledger.")

                    orig_query = orig_row[0] if orig_row else f"Dispute for audit record {audit_id}"
                    record_org_id = str(orig_row[2]) if orig_row and orig_row[2] else org_id

                    # 2. Fetch the most recent tx_hash in the organization's blockchain ledger
                    if record_org_id:
                        cursor.execute("""
                            SELECT tx_hash 
                            FROM compliance_ledger 
                            WHERE org_id = %s
                            ORDER BY timestamp DESC, audit_id DESC 
                            LIMIT 1;
                        """, (str(record_org_id),))
                    else:
                        cursor.execute("""
                            SELECT tx_hash 
                            FROM compliance_ledger 
                            WHERE org_id IS NULL
                            ORDER BY timestamp DESC, audit_id DESC 
                            LIMIT 1;
                        """)

                    row = cursor.fetchone()
                    prev_hash = row[0].strip() if row else GENESIS_HASH

                    # 3. Construct dispute payload
                    override_payload = {
                        "original_audit_id": str(audit_id),
                        "audit_id": str(audit_id),
                        "justification": str(justification).strip(),
                        "operator_email": operator_email or "SYSTEM_OPERATOR",
                        "status": "OVERRIDDEN_BY_HUMAN",
                        "override_timestamp": timestamp_utc.isoformat(),
                        "action": "HUMAN_DISPUTE_OVERRIDE"
                    }

                    dispute_query_label = f"[DISPUTE/OVERRIDE] {orig_query}"

                    # 4. Compute deterministic SHA-256 hash
                    tx_hash = compute_canonical_hash(
                        audit_id=new_audit_id,
                        timestamp_utc=timestamp_utc,
                        model_provenance=model_provenance,
                        user_query=dispute_query_label,
                        payload=override_payload,
                        prev_hash=prev_hash,
                        org_id=record_org_id
                    )

                    # 5. Insert new dispute block into PostgreSQL ledger
                    cursor.execute("""
                        INSERT INTO compliance_ledger 
                        (audit_id, org_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        str(new_audit_id),
                        str(record_org_id) if record_org_id else None,
                        timestamp_utc,
                        model_provenance,
                        dispute_query_label,
                        Json(override_payload),
                        prev_hash,
                        tx_hash
                    ))

                    conn.commit()

                    receipt = {
                        "audit_id": str(new_audit_id),
                        "original_audit_id": str(audit_id),
                        "org_id": str(record_org_id) if record_org_id else None,
                        "timestamp": timestamp_utc.isoformat(),
                        "model_provenance": model_provenance,
                        "prev_hash": prev_hash,
                        "tx_hash": tx_hash,
                        "status": "OVERRIDDEN_BY_HUMAN",
                        "justification": str(justification).strip()
                    }
                    return receipt

        except Exception as e:
            sys.stderr.write(f"[Ledger Error] Failed to record dispute override: {e}\n")
            raise


def verify_ledger_chain(org_id: Optional[str] = None) -> Tuple[bool, int, Optional[str]]:
    """
    Validates the entire cryptographic hash chain for a specific organization from genesis to the most recent block.
    Returns (is_valid, total_records, error_message).
    """
    if not init_ledger_table():
        return False, 0, "Could not initialize database connection."

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if org_id:
                    cursor.execute("""
                        SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash, org_id
                        FROM compliance_ledger
                        WHERE org_id = %s
                        ORDER BY timestamp ASC, audit_id ASC;
                    """, (str(org_id),))
                else:
                    cursor.execute("""
                        SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash, org_id
                        FROM compliance_ledger
                        ORDER BY timestamp ASC, audit_id ASC;
                    """)

                rows = cursor.fetchall()

                if not rows:
                    return True, 0, None

                expected_prev_hash = GENESIS_HASH

                for idx, row in enumerate(rows):
                    row_audit_id, row_ts, row_model, row_query, row_payload, row_prev_hash, row_tx_hash, row_org_id = row

                    # Verify previous hash pointer matches expected link in chain
                    if row_prev_hash.strip() != expected_prev_hash.strip():
                        return False, idx, (
                            f"Broken chain link at block index {idx} (Audit ID: {row_audit_id}). "
                            f"Expected prev_hash '{expected_prev_hash}', found '{row_prev_hash.strip()}'."
                        )

                    # Recompute canonical hash
                    recomputed_hash = compute_canonical_hash(
                        audit_id=row_audit_id,
                        timestamp_utc=row_ts,
                        model_provenance=row_model,
                        user_query=row_query,
                        payload=row_payload,
                        prev_hash=row_prev_hash.strip(),
                        org_id=str(row_org_id) if row_org_id else None
                    )

                    # Verify transaction hash authenticity
                    if recomputed_hash != row_tx_hash.strip():
                        return False, idx, (
                            f"Tampered content at block index {idx} (Audit ID: {row_audit_id}). "
                            f"Recorded tx_hash '{row_tx_hash.strip()}', computed '{recomputed_hash}'."
                        )

                    expected_prev_hash = row_tx_hash.strip()

                return True, len(rows), None

    except Exception as e:
        return False, 0, f"Ledger verification failed with error: {e}"


def get_recent_ledger_blocks(org_id: Optional[str] = None, limit: int = 10) -> list:
    """
    Fetches the most recent `limit` cryptographic ledger blocks from PostgreSQL for a specific organization,
    ordered newest first. Ensures strict multi-tenant row-level data isolation.
    """
    if not init_ledger_table():
        return []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if org_id:
                    cursor.execute("""
                        SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash, org_id
                        FROM compliance_ledger
                        WHERE org_id = %s
                        ORDER BY timestamp DESC, audit_id DESC
                        LIMIT %s;
                    """, (str(org_id), limit))
                else:
                    cursor.execute("""
                        SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash, org_id
                        FROM compliance_ledger
                        ORDER BY timestamp DESC, audit_id DESC
                        LIMIT %s;
                    """, (limit,))

                rows = cursor.fetchall()
                blocks = []
                for row in rows:
                    row_audit_id, row_ts, row_model, row_query, row_payload, row_prev_hash, row_tx_hash, row_org_id = row
                    blocks.append({
                        "audit_id": str(row_audit_id),
                        "org_id": str(row_org_id) if row_org_id else None,
                        "timestamp": row_ts.isoformat() if hasattr(row_ts, "isoformat") else str(row_ts),
                        "model_provenance": str(row_model),
                        "user_query": str(row_query),
                        "payload": row_payload,
                        "prev_hash": str(row_prev_hash).strip(),
                        "tx_hash": str(row_tx_hash).strip()
                    })
                return blocks
    except Exception as e:
        sys.stderr.write(f"[Ledger Error] Failed to fetch recent ledger blocks: {e}\n")
        return []



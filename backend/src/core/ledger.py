import os
import sys
import json
import uuid
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import Json

from src.core.database import get_db_connection, get_connection_pool, _db_initialized

# Genesis hash for the initial block in the chain (64 hex zeros)
GENESIS_HASH = "0" * 64
_ledger_lock = threading.Lock()
_ledger_table_initialized = False


def init_ledger_table() -> bool:
    """
    Initializes the PostgreSQL compliance_ledger table with SHA-256 hash chaining columns
    and performance indexes.
    """
    global _ledger_table_initialized
    if _ledger_table_initialized:
        return True

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Create the immutable compliance ledger table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS compliance_ledger (
                        audit_id UUID PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        model_provenance VARCHAR(100) NOT NULL,
                        user_query TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        prev_hash CHAR(64) NOT NULL,
                        tx_hash CHAR(64) NOT NULL UNIQUE
                    );
                """)

                # 2. Add indexes for audit tracing, chronological ordering, and GIN querying
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_compliance_ledger_timestamp 
                    ON compliance_ledger (timestamp);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_compliance_ledger_prev_hash 
                    ON compliance_ledger (prev_hash);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_compliance_ledger_tx_hash 
                    ON compliance_ledger (tx_hash);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_compliance_ledger_payload_gin 
                    ON compliance_ledger USING gin (payload);
                """)

                conn.commit()
                _ledger_table_initialized = True
                return True
    except Exception as e:
        sys.stderr.write(f"[Ledger Error] Failed to initialize compliance_ledger table: {e}\n")
        return False


def compute_canonical_hash(
    audit_id: uuid.UUID,
    timestamp_utc: datetime,
    model_provenance: str,
    user_query: str,
    payload: Dict[str, Any],
    prev_hash: str
) -> str:
    """
    Computes a deterministic SHA-256 hash of the record's canonical data.
    Keys are sorted and JSON is formatted deterministically without arbitrary whitespace.
    """
    canonical_dict = {
        "audit_id": str(audit_id),
        "model_provenance": str(model_provenance),
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
    model_provenance: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Appends a new compliance judgment to the immutable PostgreSQL ledger:
    1. Locks the ledger table in EXCLUSIVE MODE to guarantee linear hash-chain integrity.
    2. Fetches the latest tx_hash to use as prev_hash (or GENESIS_HASH if empty).
    3. Computes the new SHA-256 tx_hash over canonical data.
    4. Inserts the record and commits the transaction.
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

                    # 1. Fetch the tx_hash of the most recent ledger record
                    cursor.execute("""
                        SELECT tx_hash 
                        FROM compliance_ledger 
                        ORDER BY timestamp DESC, audit_id DESC 
                        LIMIT 1;
                    """)
                    row = cursor.fetchone()
                    prev_hash = row[0] if row else GENESIS_HASH

                    # 2. Compute canonical SHA-256 hash for current record
                    tx_hash = compute_canonical_hash(
                        audit_id=audit_id,
                        timestamp_utc=timestamp_utc,
                        model_provenance=model_provenance,
                        user_query=user_query,
                        payload=payload,
                        prev_hash=prev_hash
                    )

                    # 3. Insert the linked record into PostgreSQL
                    cursor.execute("""
                        INSERT INTO compliance_ledger 
                        (audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """, (
                        str(audit_id),
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


def override_ledger_record(
    audit_id: str,
    justification: str,
    model_provenance: str = "HUMAN_OPERATOR"
) -> Optional[Dict[str, Any]]:
    """
    Implements the 'Human-in-the-Loop' dispute protocol:
    1. Validates the original audit record.
    2. Does NOT modify or delete the original row.
    3. Inserts a new dispute record linked to the latest tx_hash in the chain.
    4. Sets payload status to 'OVERRIDDEN_BY_HUMAN' with the developer's justification.
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

                    # 1. Fetch the original record to preserve context and original query
                    cursor.execute("""
                        SELECT user_query, payload 
                        FROM compliance_ledger 
                        WHERE audit_id = %s;
                    """, (str(audit_id),))
                    orig_row = cursor.fetchone()
                    orig_query = orig_row[0] if orig_row else f"Dispute for audit record {audit_id}"

                    # 2. Fetch the most recent tx_hash in the blockchain ledger
                    cursor.execute("""
                        SELECT tx_hash 
                        FROM compliance_ledger 
                        ORDER BY timestamp DESC, audit_id DESC 
                        LIMIT 1;
                    """)
                    row = cursor.fetchone()
                    prev_hash = row[0] if row else GENESIS_HASH

                    # 3. Construct dispute payload
                    override_payload = {
                        "original_audit_id": str(audit_id),
                        "audit_id": str(audit_id),
                        "justification": str(justification).strip(),
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
                        prev_hash=prev_hash
                    )

                    # 5. Insert new dispute block into PostgreSQL ledger
                    cursor.execute("""
                        INSERT INTO compliance_ledger 
                        (audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """, (
                        str(new_audit_id),
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
            return None



def verify_ledger_chain() -> Tuple[bool, int, Optional[str]]:
    """
    Validates the entire cryptographic hash chain from genesis to the most recent block.
    Returns (is_valid, total_records, error_message).
    """
    if not init_ledger_table():
        return False, 0, "Could not initialize database connection."

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash
                    FROM compliance_ledger
                    ORDER BY timestamp ASC, audit_id ASC;
                """)
                rows = cursor.fetchall()

                if not rows:
                    return True, 0, None

                expected_prev_hash = GENESIS_HASH

                for idx, row in enumerate(rows):
                    row_audit_id, row_ts, row_model, row_query, row_payload, row_prev_hash, row_tx_hash = row

                    # Verify previous hash pointer matches expected link in chain
                    if row_prev_hash.strip() != expected_prev_hash.strip():
                        return False, idx, (
                            f"Broken chain link at block index {idx} (Audit ID: {row_audit_id}). "
                            f"Expected prev_hash '{expected_prev_hash}', found '{row_prev_hash}'."
                        )

                    # Recompute canonical hash
                    recomputed_hash = compute_canonical_hash(
                        audit_id=row_audit_id,
                        timestamp_utc=row_ts,
                        model_provenance=row_model,
                        user_query=row_query,
                        payload=row_payload,
                        prev_hash=row_prev_hash.strip()
                    )

                    # Verify transaction hash authenticity
                    if recomputed_hash != row_tx_hash.strip():
                        return False, idx, (
                            f"Tampered content at block index {idx} (Audit ID: {row_audit_id}). "
                            f"Recorded tx_hash '{row_tx_hash}', computed '{recomputed_hash}'."
                        )

                    expected_prev_hash = row_tx_hash.strip()

                return True, len(rows), None

    except Exception as e:
        return False, 0, f"Ledger verification failed with error: {e}"


def get_recent_ledger_blocks(limit: int = 10) -> list:
    """
    Fetches the most recent `limit` cryptographic ledger blocks from PostgreSQL,
    ordered newest first.
    """
    if not init_ledger_table():
        return []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT audit_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash
                    FROM compliance_ledger
                    ORDER BY timestamp DESC, audit_id DESC
                    LIMIT %s;
                """, (limit,))
                rows = cursor.fetchall()
                blocks = []
                for row in rows:
                    row_audit_id, row_ts, row_model, row_query, row_payload, row_prev_hash, row_tx_hash = row
                    blocks.append({
                        "audit_id": str(row_audit_id),
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


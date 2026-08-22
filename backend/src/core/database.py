import os
import sys
import socket
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Generator
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json
from dotenv import load_dotenv

# Load database credentials from the .env file
load_dotenv()

_db_initialized = False
_db_lock = threading.Lock()
_pool_instance: Optional[pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()
_db_unreachable = False


def _get_resolved_db_url() -> str:
    """
    Resolves the database connection string. If configured with Docker hostname 'db'
    and executed outside Docker container, automatically falls back to 'localhost'.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("CRITICAL ERROR: DATABASE_URL missing from environment configuration.")

    # Check if host 'db' is reachable (Docker environment check)
    if "@db:" in db_url:
        try:
            socket.gethostbyname("db")
        except socket.gaierror:
            # Fallback for local development outside Docker network
            local_fallback = db_url.replace("@db:", "@localhost:")
            return os.getenv("LOCAL_DATABASE_URL", local_fallback)

    return db_url


def get_connection_pool() -> Optional[pool.ThreadedConnectionPool]:
    """
    Returns a thread-safe singleton instance of ThreadedConnectionPool.
    Reuses existing connections to avoid connection churn in multi-user workloads.
    """
    global _pool_instance, _db_unreachable
    if _db_unreachable:
        return None

    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                try:
                    db_url = _get_resolved_db_url()
                    _pool_instance = pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=20,
                        dsn=db_url,
                        connect_timeout=3
                    )
                except Exception as e:
                    sys.stderr.write(f"[Database Warning] Connection pool initialization failed: {e}\n")
                    _db_unreachable = True
                    return None
    return _pool_instance


@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager that checks out a connection from the ThreadedConnectionPool,
    guarantees clean transaction state (rollback on error), and prevents pool poisoning.
    """
    conn_pool = get_connection_pool()
    if conn_pool is None:
        # Fallback to direct connection if pool could not be instantiated
        db_url = _get_resolved_db_url()
        direct_conn = psycopg2.connect(db_url, connect_timeout=3)
        try:
            yield direct_conn
        except Exception:
            try:
                direct_conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                direct_conn.close()
            except Exception:
                pass
        return

    conn = conn_pool.getconn()
    has_error = False
    try:
        yield conn
    except Exception:
        has_error = True
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        # Prevent returning poisoned connections to pool
        if conn.closed:
            conn_pool.putconn(conn, close=True)
        else:
            try:
                if conn.status != psycopg2.extensions.STATUS_READY:
                    conn.rollback()
            except Exception:
                pass
            conn_pool.putconn(conn, close=has_error)


def init_db() -> bool:
    """
    Initializes the PostgreSQL database, creates the audit table, and configures
    B-tree and GIN indexes for high-speed compliance querying.
    """
    global _db_initialized, _db_unreachable
    if _db_initialized:
        return True

    with _db_lock:
        if _db_initialized:
            return True

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Create the legacy compliance audit logs table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS compliance_logs (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP NOT NULL,
                            user_query TEXT NOT NULL,
                            risk_category VARCHAR(50) NOT NULL,
                            is_compliant BOOLEAN NOT NULL,
                            full_json_payload JSONB NOT NULL
                        );
                    """)

                    # 2. Create the immutable SHA-256 hash-chained compliance ledger table
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

                    # 3. Add performance & search indexes
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_compliance_logs_timestamp 
                        ON compliance_logs (timestamp);
                    """)
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
                    _db_initialized = True
                    print("✅ PostgreSQL Compliance Ledger & GIN indexes initialized successfully.")
                    return True

        except Exception as e:
            sys.stderr.write(f"[Database Error] DB initialization failed: {e}\n")
            return False


def save_compliance_record(user_query: str, result_dict: dict) -> bool:
    """
    Extracts indexed fields and writes the full payload to PostgreSQL JSONB storage.
    Returns True if successfully persisted, False otherwise.
    """
    global _db_initialized
    if not _db_initialized:
        initialized = init_db()
        if not initialized:
            return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                timestamp = datetime.now()
                risk_category = result_dict.get("risk_category", "Unknown")
                is_compliant = bool(result_dict.get("is_compliant", False))

                cursor.execute("""
                    INSERT INTO compliance_logs 
                    (timestamp, user_query, risk_category, is_compliant, full_json_payload)
                    VALUES (%s, %s, %s, %s, %s)
                """, (timestamp, user_query, risk_category, is_compliant, Json(result_dict)))

                conn.commit()
                print("Payload successfully routed to PostgreSQL JSONB storage.")
                return True

    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to persist compliance record: {e}\n")
        return False
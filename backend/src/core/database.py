import os
import sys
import uuid
import socket
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Generator, Dict, Any, List
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json, RealDictCursor
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
    Initializes the PostgreSQL database with multi-tenant B2B schema:
    1. organizations table (id UUID, name String, created_at TIMESTAMPTZ)
    2. users table (id UUID, org_id UUID FK, email String UNIQUE, hashed_password String, role Enum)
    3. compliance_ledger table with SHA-256 hash chaining columns & org_id FK
    4. Indexes for high-speed multi-tenant audit querying.
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
                    # 1. Create the organizations table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS organizations (
                            id UUID PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                    """)

                    # 2. Create the users table with RBAC role check
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id UUID PRIMARY KEY,
                            org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            hashed_password VARCHAR(255) NOT NULL,
                            role VARCHAR(50) NOT NULL CHECK (role IN ('DEVELOPER', 'MANAGER', 'MASTER_ADMIN')),
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                    """)

                    # 3. Create the immutable SHA-256 hash-chained compliance ledger table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS compliance_ledger (
                            audit_id UUID PRIMARY KEY,
                            org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
                            timestamp TIMESTAMPTZ NOT NULL,
                            model_provenance VARCHAR(100) NOT NULL,
                            user_query TEXT NOT NULL,
                            payload JSONB NOT NULL,
                            prev_hash CHAR(64) NOT NULL,
                            tx_hash CHAR(64) NOT NULL UNIQUE
                        );
                    """)

                    # Migration: Add org_id to compliance_ledger if table already existed
                    cursor.execute("""
                        ALTER TABLE compliance_ledger 
                        ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
                    """)

                    # 4. Create the legacy compliance audit logs table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS compliance_logs (
                            id SERIAL PRIMARY KEY,
                            org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
                            timestamp TIMESTAMP NOT NULL,
                            user_query TEXT NOT NULL,
                            risk_category VARCHAR(50) NOT NULL,
                            is_compliant BOOLEAN NOT NULL,
                            full_json_payload JSONB NOT NULL
                        );
                    """)

                    cursor.execute("""
                        ALTER TABLE compliance_logs 
                        ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;
                    """)

                    # 5. Add performance & search indexes
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations (name);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_org_id ON users (org_id);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compliance_ledger_org_id ON compliance_ledger (org_id);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compliance_ledger_timestamp ON compliance_ledger (timestamp);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compliance_ledger_prev_hash ON compliance_ledger (prev_hash);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compliance_ledger_tx_hash ON compliance_ledger (tx_hash);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compliance_ledger_payload_gin ON compliance_ledger USING gin (payload);")

                    conn.commit()
                    _db_initialized = True
                    print("✅ PostgreSQL Multi-Tenant Schema, Organizations, Users, & Ledger indexes initialized.")
                    return True

        except Exception as e:
            sys.stderr.write(f"[Database Error] DB initialization failed: {e}\n")
            return False


# =====================================================================
# Multi-Tenant & User Management Helpers
# =====================================================================

def create_organization(name: str, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Creates a new organization record."""
    if not _db_initialized:
        init_db()

    new_id = org_id if org_id else str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO organizations (id, name, created_at)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, created_at;
                """, (new_id, name.strip(), now_utc))
                row = cursor.fetchone()
                conn.commit()
                if row:
                    row["id"] = str(row["id"])
                    row["created_at"] = row["created_at"].isoformat()
                return dict(row) if row else None
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to create organization: {e}\n")
        return None


def get_organization_by_id(org_id: str) -> Optional[Dict[str, Any]]:
    """Fetches an organization by its UUID."""
    if not _db_initialized:
        init_db()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT id, name, created_at
                    FROM organizations
                    WHERE id = %s;
                """, (str(org_id),))
                row = cursor.fetchone()
                if row:
                    row["id"] = str(row["id"])
                    row["created_at"] = row["created_at"].isoformat()
                    return dict(row)
                return None
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to fetch organization: {e}\n")
        return None


def create_user(
    org_id: str,
    email: str,
    hashed_password: str,
    role: str,
    user_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Creates a new user record tied to an organization."""
    if not _db_initialized:
        init_db()

    new_id = user_id if user_id else str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO users (id, org_id, email, hashed_password, role, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, org_id, email, role, created_at;
                """, (
                    new_id,
                    str(org_id),
                    email.strip().lower(),
                    hashed_password,
                    role.upper(),
                    now_utc
                ))
                row = cursor.fetchone()
                conn.commit()
                if row:
                    row["id"] = str(row["id"])
                    row["org_id"] = str(row["org_id"])
                    row["created_at"] = row["created_at"].isoformat()
                return dict(row) if row else None
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to create user: {e}\n")
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Fetches a user by email along with their organization name."""
    if not _db_initialized:
        init_db()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT u.id, u.org_id, u.email, u.hashed_password, u.role, u.created_at,
                           o.name AS org_name
                    FROM users u
                    JOIN organizations o ON u.org_id = o.id
                    WHERE u.email = %s;
                """, (email.strip().lower(),))
                row = cursor.fetchone()
                if row:
                    row["id"] = str(row["id"])
                    row["org_id"] = str(row["org_id"])
                    row["created_at"] = row["created_at"].isoformat()
                    return dict(row)
                return None
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to fetch user by email: {e}\n")
        return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a user by UUID along with their organization name."""
    if not _db_initialized:
        init_db()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT u.id, u.org_id, u.email, u.role, u.created_at,
                           o.name AS org_name
                    FROM users u
                    JOIN organizations o ON u.org_id = o.id
                    WHERE u.id = %s;
                """, (str(user_id),))
                row = cursor.fetchone()
                if row:
                    row["id"] = str(row["id"])
                    row["org_id"] = str(row["org_id"])
                    row["created_at"] = row["created_at"].isoformat()
                    return dict(row)
                return None
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to fetch user by id: {e}\n")
        return None


def list_users_by_org(org_id: str) -> List[Dict[str, Any]]:
    """Lists all users belonging to a specific organization."""
    if not _db_initialized:
        init_db()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT id, org_id, email, role, created_at
                    FROM users
                    WHERE org_id = %s
                    ORDER BY created_at ASC;
                """, (str(org_id),))
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    row["id"] = str(row["id"])
                    row["org_id"] = str(row["org_id"])
                    row["created_at"] = row["created_at"].isoformat()
                    results.append(dict(row))
                return results
    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to list users by org: {e}\n")
        return []


def save_compliance_record(
    user_query: str,
    result_dict: dict,
    org_id: Optional[str] = None
) -> bool:
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
                    (org_id, timestamp, user_query, risk_category, is_compliant, full_json_payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    str(org_id) if org_id else None,
                    timestamp,
                    user_query,
                    risk_category,
                    is_compliant,
                    Json(result_dict)
                ))

                conn.commit()
                print("Payload successfully routed to PostgreSQL JSONB storage.")
                return True

    except Exception as e:
        sys.stderr.write(f"[Database Error] Failed to persist compliance record: {e}\n")
        return False
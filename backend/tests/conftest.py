import os
import sys
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

# Ensure UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Load environment configuration (.env)
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Resolve DATABASE_URL for local test execution
db_url = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/finsight_db")
if "@db:" in db_url:
    db_url = db_url.replace("@db:", "@localhost:")
os.environ["DATABASE_URL"] = db_url

os.environ.setdefault("JWT_SECRET_KEY", "ci-test-secret-key-32-chars-long-2026")
os.environ.setdefault("GEMINI_MODEL", "gemini-3.6-flash")

from src.api.main import app
from src.core.database import get_db_connection, init_db
from src.core.ledger import init_ledger_table


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database schema and ledger tables are initialized once per test session."""
    init_db()
    init_ledger_table()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def test_organization():
    """
    Creates an isolated organization for a test and cleans it up after.
    Cascades to all users, ledger records, and prompts tied to org_id.
    """
    org_id = str(uuid.uuid4())
    org_name = f"TestOrg_{org_id[:8]}"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO organizations (id, name, created_at) VALUES (%s, %s, %s)",
                (org_id, org_name, datetime.now(UTC)),
            )
        conn.commit()

    yield {"id": org_id, "name": org_name}

    # Teardown
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
            conn.commit()
    except Exception:
        pass

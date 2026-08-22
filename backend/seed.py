import asyncio
import os
import sys
import uuid
import json
import hashlib
import socket
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from passlib.context import CryptContext
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashes a password with bcrypt."""
    import bcrypt
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def compute_canonical_hash(
    audit_id: uuid.UUID,
    timestamp_utc: datetime,
    model_provenance: str,
    user_query: str,
    payload: dict,
    prev_hash: str,
    org_id: str
) -> str:
    """
    Computes deterministic SHA-256 hash matching backend/src/core/ledger.py.
    """
    canonical_dict = {
        "audit_id": str(audit_id),
        "model_provenance": str(model_provenance),
        "org_id": str(org_id),
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


def get_async_db_url() -> str:
    """
    Resolves the async PostgreSQL database URL.
    Converts postgresql:// to postgresql+asyncpg:// and handles host fallback.
    """
    raw_url = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/finsight_db")
    
    # Check if host 'db' is reachable (Docker environment check)
    if "@db:" in raw_url:
        try:
            socket.gethostbyname("db")
        except socket.gaierror:
            raw_url = raw_url.replace("@db:", "@localhost:")

    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)

    return raw_url


async def seed_database():
    print("=" * 70)
    print(" FINSIGHT REGTECH: ASYNC DATABASE SEEDING ")
    print("=" * 70)

    db_url = get_async_db_url()
    print(f"Connecting to database at: {db_url.split('@')[-1]}")

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        print("\n1. Dropping existing tables...")
        await conn.execute(text("DROP TABLE IF EXISTS compliance_logs CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS compliance_ledger CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS organizations CASCADE;"))

        print("2. Creating schema with multi-tenant tables and indexes...")
        await conn.execute(text("""
            CREATE TABLE organizations (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))

        await conn.execute(text("""
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                email VARCHAR(255) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL CHECK (role IN ('DEVELOPER', 'MANAGER', 'MASTER_ADMIN')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))

        await conn.execute(text("""
            CREATE TABLE compliance_ledger (
                audit_id UUID PRIMARY KEY,
                org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
                timestamp TIMESTAMPTZ NOT NULL,
                model_provenance VARCHAR(100) NOT NULL,
                user_query TEXT NOT NULL,
                payload JSONB NOT NULL,
                prev_hash CHAR(64) NOT NULL,
                tx_hash CHAR(64) NOT NULL UNIQUE
            );
        """))

        await conn.execute(text("""
            CREATE TABLE compliance_logs (
                id SERIAL PRIMARY KEY,
                org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
                timestamp TIMESTAMP NOT NULL,
                user_query TEXT NOT NULL,
                risk_category VARCHAR(50) NOT NULL,
                is_compliant BOOLEAN NOT NULL,
                full_json_payload JSONB NOT NULL
            );
        """))

        await conn.execute(text("CREATE INDEX idx_organizations_name ON organizations (name);"))
        await conn.execute(text("CREATE INDEX idx_users_email ON users (email);"))
        await conn.execute(text("CREATE INDEX idx_users_org_id ON users (org_id);"))
        await conn.execute(text("CREATE INDEX idx_compliance_ledger_org_id ON compliance_ledger (org_id);"))
        await conn.execute(text("CREATE INDEX idx_compliance_ledger_timestamp ON compliance_ledger (timestamp);"))
        await conn.execute(text("CREATE INDEX idx_compliance_ledger_prev_hash ON compliance_ledger (prev_hash);"))
        await conn.execute(text("CREATE INDEX idx_compliance_ledger_tx_hash ON compliance_ledger (tx_hash);"))
        await conn.execute(text("CREATE INDEX idx_compliance_ledger_payload_gin ON compliance_ledger USING gin (payload);"))

        print("3. Seeding Organizations...")
        org1_id = uuid.UUID("d3b07384-d113-4966-9c0e-698b80b2a6f1")
        org2_id = uuid.UUID("e5c18495-e224-4a77-ad1f-7a9c91c3b7f2")

        await conn.execute(
            text("INSERT INTO organizations (id, name, created_at) VALUES (:id, :name, :created_at)"),
            [
                {"id": org1_id, "name": "Nordic Payments Group", "created_at": datetime.now(timezone.utc)},
                {"id": org2_id, "name": "Apex Credit AI", "created_at": datetime.now(timezone.utc)},
            ]
        )
        print("  - Inserted Org 1: Nordic Payments Group (UUID: d3b07384...)")
        print("  - Inserted Org 2: Apex Credit AI (UUID: e5c18495...)")

        print("\n4. Seeding Users (Password: 'demo123')...")
        hashed_demo_pw = hash_password("demo123")

        users_to_insert = [
            # Organization 1: Nordic Payments Group
            {
                "id": uuid.uuid4(),
                "org_id": org1_id,
                "email": "admin@nordicpayments.eu",
                "hashed_password": hashed_demo_pw,
                "role": "MASTER_ADMIN",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": uuid.uuid4(),
                "org_id": org1_id,
                "email": "manager@nordicpayments.eu",
                "hashed_password": hashed_demo_pw,
                "role": "MANAGER",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": uuid.uuid4(),
                "org_id": org1_id,
                "email": "dev@nordicpayments.eu",
                "hashed_password": hashed_demo_pw,
                "role": "DEVELOPER",
                "created_at": datetime.now(timezone.utc),
            },
            # Organization 2: Apex Credit AI
            {
                "id": uuid.uuid4(),
                "org_id": org2_id,
                "email": "admin@apexcredit.ai",
                "hashed_password": hashed_demo_pw,
                "role": "MASTER_ADMIN",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": uuid.uuid4(),
                "org_id": org2_id,
                "email": "manager@apexcredit.ai",
                "hashed_password": hashed_demo_pw,
                "role": "MANAGER",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": uuid.uuid4(),
                "org_id": org2_id,
                "email": "dev@apexcredit.ai",
                "hashed_password": hashed_demo_pw,
                "role": "DEVELOPER",
                "created_at": datetime.now(timezone.utc),
            },
        ]

        for u in users_to_insert:
            await conn.execute(
                text("""
                    INSERT INTO users (id, org_id, email, hashed_password, role, created_at)
                    VALUES (:id, :org_id, :email, :hashed_password, :role, :created_at)
                """),
                u
            )
            print(f"  - User: {u['email']} [{u['role']}]")

        print("\n5. Generating 5 Mathematically Linked SHA-256 Ledger Blocks for Nordic Payments Group...")
        genesis_hash = "0" * 64

        # Block 0: Genesis Block
        b0_id = uuid.UUID("a0000000-0000-0000-0000-000000000001")
        b0_time = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        b0_prov = "SYSTEM_GENESIS_INITIALIZER"
        b0_query = "Genesis Block Initialization: Nordic Payments Group"
        b0_payload = {
            "event": "GENESIS_BLOCK_INITIALIZATION",
            "org_id": str(org1_id),
            "org_name": "Nordic Payments Group",
            "admin_email": "admin@nordicpayments.eu",
            "chain_version": "v1.0-sha256",
            "status": "ANCHORED"
        }
        b0_prev = genesis_hash
        b0_tx = compute_canonical_hash(b0_id, b0_time, b0_prov, b0_query, b0_payload, b0_prev, str(org1_id))

        # Block 1: Fraud Detection Monitoring (Minimal Risk)
        b1_id = uuid.UUID("a0000000-0000-0000-0000-000000000002")
        b1_time = datetime(2026, 8, 21, 9, 15, 0, tzinfo=timezone.utc)
        b1_prov = "gemini-3.6-flash"
        b1_query = "Real-time payment transaction monitoring system utilizing behavioral telemetry to flag and freeze suspicious PSD2 open banking transactions with human compliance officer review."
        b1_payload = {
            "risk_category": "Minimal Risk",
            "is_compliant": True,
            "executive_summary_markdown": "### Architectural Determination\nThe proposed behavioral telemetry transaction monitoring system operates under the PSD2 RTS Article 18 exemption framework and satisfies GDPR Article 6(1)(f) legitimate interest requirements.\n\n* **PSD2 Compliance**: Transaction risk analysis with dynamic SCA meets standard exemptions.\n* **GDPR Compliance**: Pseudonymized behavioral metrics adhere to data minimization principles.",
            "jurisdictions": ["EU (AI Act, GDPR, PSD2)"],
            "citations": [
                {
                    "document": "PSD2 Regulatory Technical Standards (EU) 2018/389",
                    "page": "12",
                    "quoted_text": "Payment service providers shall be allowed not to apply strong customer authentication where the payer initiates a remote electronic payment transaction identified by the payment service provider as posing a low level of risk according to the transaction monitoring mechanisms."
                },
                {
                    "document": "GDPR (EU) 2016/679",
                    "page": "38",
                    "quoted_text": "Processing shall be lawful only if processing is necessary for the purposes of the legitimate interests pursued by the controller or by a third party."
                }
            ]
        }
        b1_prev = b0_tx
        b1_tx = compute_canonical_hash(b1_id, b1_time, b1_prov, b1_query, b1_payload, b1_prev, str(org1_id))

        # Block 2: Biometric Facial Recognition Gateway (High-Risk)
        b2_id = uuid.UUID("a0000000-0000-0000-0000-000000000003")
        b2_time = datetime(2026, 8, 21, 14, 30, 0, tzinfo=timezone.utc)
        b2_prov = "gemini-3.6-flash"
        b2_query = "We are developing a cloud-hosted biometric facial recognition gateway to categorize retail banking users and authorize high-value transactions automatically without human intervention."
        b2_payload = {
            "risk_category": "Prohibited / High-Risk",
            "is_compliant": False,
            "executive_summary_markdown": "### Architectural Determination\nAutomated biometric categorization and unconstrained facial verification for automated decision-making is classified as High-Risk under EU AI Act Annex III and prohibited under GDPR Article 9(1) without explicit consent exceptions.\n\n* **EU AI Act**: Annex III Section 1 categorizes remote biometric identification as High-Risk.\n* **GDPR Art. 22**: Solely automated decisions producing legal effects require human oversight mechanisms.",
            "jurisdictions": ["EU (AI Act, GDPR, PSD2)"],
            "citations": [
                {
                    "document": "EU AI Act 2024/1689",
                    "page": "84",
                    "quoted_text": "Biometric identification and categorisation systems intended to be used for the evaluation of natural persons shall be classified as high-risk AI systems."
                },
                {
                    "document": "GDPR (EU) 2016/679",
                    "page": "46",
                    "quoted_text": "The data subject shall have the right not to be subject to a decision based solely on automated processing, including profiling, which produces legal effects concerning him or her."
                }
            ]
        }
        b2_prev = b1_tx
        b2_tx = compute_canonical_hash(b2_id, b2_time, b2_prov, b2_query, b2_payload, b2_prev, str(org1_id))

        # Block 3: Human-in-the-Loop Dispute Override of Block 2
        b3_id = uuid.UUID("a0000000-0000-0000-0000-000000000004")
        b3_time = datetime(2026, 8, 21, 16, 45, 0, tzinfo=timezone.utc)
        b3_prov = "HUMAN_OVERRIDE_AUTHORITY"
        b3_query = "Dispute Resolution & Legal Override: a0000000-0000-0000-0000-000000000003"
        b3_payload = {
            "status": "OVERRIDDEN_BY_HUMAN",
            "original_audit_id": str(b2_id),
            "override_actor_role": "MANAGER",
            "actor_email": "manager@nordicpayments.eu",
            "justification": "Biometric verification is executed entirely localized on Secure Enclave mobile hardware with zero remote cloud transmission under GDPR Art. 9(2)(a) explicit consent and satisfies human-in-the-loop escalation criteria.",
            "risk_category": "OVERRIDDEN",
            "is_compliant": True
        }
        b3_prev = b2_tx
        b3_tx = compute_canonical_hash(b3_id, b3_time, b3_prov, b3_query, b3_payload, b3_prev, str(org1_id))

        # Block 4: PSD2 Strong Customer Authentication & Open Banking Gateway
        b4_id = uuid.UUID("a0000000-0000-0000-0000-000000000005")
        b4_time = datetime(2026, 8, 22, 11, 20, 0, tzinfo=timezone.utc)
        b4_prov = "gemini-3.6-flash"
        b4_query = "Open Banking AISP/PISP API Gateway with FAPI 1.0 Advanced dynamic client registration and mutual TLS authentication."
        b4_payload = {
            "risk_category": "Minimal Risk",
            "is_compliant": True,
            "executive_summary_markdown": "### Architectural Determination\nFAPI 1.0 Advanced specification with eIDAS QWAC/QSeal certificates fully satisfies PSD2 Article 67/68 access requirements and EBA Open Banking Guidelines.\n\n* **PSD2 Regulatory Compliance**: Mutual TLS with QWAC certificates guarantees secure communication.\n* **GDPR Data Protection**: Scoped OAuth 2.0 consent tokens enforce strict access minimization.",
            "jurisdictions": ["EU (AI Act, GDPR, PSD2)"],
            "citations": [
                {
                    "document": "PSD2 Directive (EU) 2015/2366",
                    "page": "55",
                    "quoted_text": "Account servicing payment service providers shall allow payment initiation service providers and account information service providers to rely on the authentication procedures provided by the account servicing payment service provider to the payment service user."
                },
                {
                    "document": "PSD2 Regulatory Technical Standards (EU) 2018/389",
                    "page": "19",
                    "quoted_text": "Payment service providers shall ensure secure communication between the software application of the payment service user and the payment service provider."
                }
            ]
        }
        b4_prev = b3_tx
        b4_tx = compute_canonical_hash(b4_id, b4_time, b4_prov, b4_query, b4_payload, b4_prev, str(org1_id))

        blocks = [
            (b0_id, b0_time, b0_prov, b0_query, b0_payload, b0_prev, b0_tx),
            (b1_id, b1_time, b1_prov, b1_query, b1_payload, b1_prev, b1_tx),
            (b2_id, b2_time, b2_prov, b2_query, b2_payload, b2_prev, b2_tx),
            (b3_id, b3_time, b3_prov, b3_query, b3_payload, b3_prev, b3_tx),
            (b4_id, b4_time, b4_prov, b4_query, b4_payload, b4_prev, b4_tx),
        ]

        for i, (b_id, b_t, b_prv, b_q, b_pl, b_prev_h, b_tx_h) in enumerate(blocks):
            await conn.execute(
                text("""
                    INSERT INTO compliance_ledger (
                        audit_id, org_id, timestamp, model_provenance, user_query, payload, prev_hash, tx_hash
                    ) VALUES (
                        :audit_id, :org_id, :timestamp, :model_provenance, :user_query, :payload, :prev_hash, :tx_hash
                    )
                """),
                {
                    "audit_id": b_id,
                    "org_id": org1_id,
                    "timestamp": b_t,
                    "model_provenance": b_prv,
                    "user_query": b_q,
                    "payload": json.dumps(b_pl),
                    "prev_hash": b_prev_h,
                    "tx_hash": b_tx_h,
                }
            )
            print(f"  - Block #{i}: {b_q[:45]}...")
            print(f"      prev_hash: {b_prev_h[:16]}...  ->  tx_hash: {b_tx_h[:16]}...")

    await engine.dispose()

    print("\n" + "=" * 70)
    print(" DATABASE SEEDED SUCCESSFULLY! ")
    print(" Default Login Credentials (All Users): password = 'demo123'")
    print("   1. Master Admin: admin@nordicpayments.eu")
    print("   2. Manager:      manager@nordicpayments.eu")
    print("   3. Developer:    dev@nordicpayments.eu")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_database())

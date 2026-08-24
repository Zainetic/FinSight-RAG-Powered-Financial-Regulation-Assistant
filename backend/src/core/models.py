"""
FinSight RegTech - SQLAlchemy Data Models
Defines ORM mappings for Organizations, Users, Compliance Ledgers, and Transaction Gatekeeper Ledgers.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # DEVELOPER, MANAGER, MASTER_ADMIN
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="users")


class ComplianceLedger(Base):
    __tablename__ = "compliance_ledger"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    model_provenance = Column(String(100), nullable=False)
    user_query = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    prev_hash = Column(String(64), nullable=False, index=True)
    tx_hash = Column(String(64), unique=True, nullable=False, index=True)


class TransactionLedger(Base):
    """
    SQLAlchemy Model for Machine-to-Machine Financial Transaction Compliance & Gatekeeper Audit.
    Persists zero-trust sanitized payloads, rule outcomes, risk scores, and SHA-256 audit hashes.
    """
    __tablename__ = "transaction_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String(100), nullable=False, index=True)
    payload_data = Column(JSONB, nullable=False)
    verdict = Column(String(10), nullable=False)  # PASS, FAIL
    risk_score = Column(Integer, nullable=False)
    rule_triggered = Column(Text, nullable=True)
    legal_basis = Column(Text, nullable=True)
    sha256_hash = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "transaction_id": self.transaction_id,
            "payload_data": self.payload_data,
            "verdict": self.verdict,
            "risk_score": self.risk_score,
            "rule_triggered": self.rule_triggered,
            "legal_basis": self.legal_basis,
            "sha256_hash": self.sha256_hash,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

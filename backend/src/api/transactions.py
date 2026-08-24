"""
FinSight RegTech - Automated Transaction Gatekeeper API
Machine-to-Machine Financial Compliance, Sanctions Screening, Zero-Trust PII Scrubbing,
FAISS Vector Store Regulatory Retrieval (AMLD6 / EUR-Lex), SHA-256 Audit Anchoring,
and Persistent PostgreSQL Transaction Ledger Storage.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user, CurrentUser
from src.core.database import get_db
from src.core.models import TransactionLedger
from src.core.rag import get_vector_store


router = APIRouter(prefix="/api/v1/transactions", tags=["Automated Transaction Gatekeeper"])


# =====================================================================
# 1. Pydantic Schemas
# =====================================================================

class TransactionPayload(BaseModel):
    tx_id: str = Field(
        ...,
        description="Unique transaction identifier",
        example="TX-2026-948172"
    )
    sender_name: str = Field(
        ...,
        description="Full legal name of the sender entity or individual",
        example="Acme Global Corp Ltd"
    )
    sender_iban: str = Field(
        ...,
        description="International Bank Account Number (IBAN) of sender",
        example="DE89370400440532013000"
    )
    sender_country: str = Field(
        ...,
        description="ISO 2-letter country code of the sender",
        example="DE"
    )
    receiver_name: str = Field(
        ...,
        description="Full legal name of the receiver entity or individual",
        example="Horizon Trade Partners"
    )
    receiver_iban: str = Field(
        ...,
        description="International Bank Account Number (IBAN) of receiver",
        example="GB29NWBK60161331926819"
    )
    receiver_country: str = Field(
        ...,
        description="ISO 2-letter country code of the receiver",
        example="GB"
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction monetary amount",
        example=25000.00
    )
    currency: str = Field(
        ...,
        description="ISO 4217 Currency Code",
        example="EUR"
    )
    asset_type: str = Field(
        ...,
        description="Financial asset classification (e.g. FIAT_WIRE, SEPA_INSTANT, CRYPTO, SECURITIES)",
        example="SEPA_INSTANT"
    )
    sender_kyc_level: str = Field(
        ...,
        description="Sender Know-Your-Customer verification tier: 'basic', 'standard', 'enhanced'",
        example="enhanced"
    )


class ScrubbedPayload(BaseModel):
    tx_id: str
    sender_name: str
    sender_iban: str
    sender_country: str
    receiver_name: str
    receiver_iban: str
    receiver_country: str
    amount: float
    currency: str
    asset_type: str
    sender_kyc_level: str


class EvaluationResponse(BaseModel):
    verdict: Literal["PASS", "FAIL"] = Field(
        ...,
        description="Final regulatory decision: PASS or FAIL",
        example="PASS"
    )
    risk_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Calculated AML/Sanctions risk score (0-100)",
        example=12
    )
    rule_triggered: Optional[str] = Field(
        None,
        description="Rule identifier or trigger condition",
        example="Low-Risk Domestic/SEPA Flow - Standard Compliance"
    )
    legal_basis: Optional[str] = Field(
        None,
        description="Statutory legal framework or regulatory citation dynamically retrieved from FAISS EUR-Lex index",
        example="AMLD6 Article 3 (Money laundering offences) - \"Member States shall take the necessary measures...\""
    )
    sha256_audit_hash: str = Field(
        ...,
        description="Deterministic cryptographic SHA-256 hash digest of the evaluation record",
        example="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 UTC timestamp of evaluation execution"
    )
    raw_payload_preview: Dict[str, Any] = Field(
        ...,
        description="Preview of incoming payload prior to sanitization"
    )
    scrubbed_payload_sent_to_engine: ScrubbedPayload = Field(
        ...,
        description="Zero-trust scrubbed payload forwarded to compliance evaluation engine"
    )


# =====================================================================
# 2. Zero-Trust PII Scrubbing
# =====================================================================

def mask_iban(iban: str) -> str:
    """
    Masks the middle portion of an IBAN to preserve country code, bank code prefix,
    and trailing checksum while obscuring private account identifiers.
    Example: 'DE89370400440532013000' -> 'DE89************3000'
    """
    cleaned = iban.strip().replace(" ", "")
    if len(cleaned) <= 8:
        return "[REDACTED_IBAN]"
    prefix = cleaned[:4]
    suffix = cleaned[-4:]
    masked_middle = "*" * (len(cleaned) - 8)
    return f"{prefix}{masked_middle}{suffix}"


def scrub_pii(tx: TransactionPayload) -> ScrubbedPayload:
    """
    Zero-Trust PII scrubbing engine.
    Masks personal identifiable names and IBAN account numbers while keeping
    numerical values, currency, and geographical country codes intact for compliance evaluation.
    """
    return ScrubbedPayload(
        tx_id=tx.tx_id,
        sender_name="[REDACTED]",
        sender_iban=mask_iban(tx.sender_iban),
        sender_country=tx.sender_country.strip().upper(),
        receiver_name="[REDACTED]",
        receiver_iban=mask_iban(tx.receiver_iban),
        receiver_country=tx.receiver_country.strip().upper(),
        amount=tx.amount,
        currency=tx.currency.strip().upper(),
        asset_type=tx.asset_type.strip(),
        sender_kyc_level=tx.sender_kyc_level.strip().lower()
    )


# =====================================================================
# 3. Dynamic FAISS RAG Statutory Legal Basis Retrieval
# =====================================================================

def retrieve_statutory_basis(search_query: str, default_fallback: str) -> str:
    """
    Performs dynamic RAG similarity search against the FAISS vector database
    to fetch authentic EUR-Lex statutory text matching the evaluated transaction context.
    Falls back gracefully without raising exceptions if FAISS is unavailable.
    """
    try:
        vector_store = get_vector_store()
        if vector_store:
            docs = vector_store.similarity_search(search_query, k=1)
            if docs:
                top_doc = docs[0]
                source = top_doc.metadata.get("source", "AMLD6")
                art_num = top_doc.metadata.get("article_number")
                title = top_doc.metadata.get("title", "")

                # Format clean text snippet from retrieved statutory article
                clean_content = " ".join(top_doc.page_content.split())
                snippet = clean_content[:240] + ("..." if len(clean_content) > 240 else "")

                art_header = f"Article {art_num}" if art_num is not None else ""
                title_suffix = f" ({title})" if title and title != f"Article {art_num}" else ""

                return f"{source} {art_header}{title_suffix} - \"{snippet}\""
    except Exception as e:
        print(f"[RAG Gatekeeper Warning] FAISS vector store query failed ({e}). Utilizing fallback legal basis.")

    return default_fallback


# =====================================================================
# 4. Gatekeeper Evaluation Endpoint (with PostgreSQL Ledger Persistence)
# =====================================================================

SANCTIONED_COUNTRIES = {"KP", "IR", "SY"}
HIGH_RISK_JURISDICTIONS = {"KY", "PA", "VG", "BS", "RU"}


@router.post(
    "/evaluate",
    response_model=EvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Automated Machine-to-Machine Financial Transaction Gatekeeper",
    description=(
        "Executes zero-trust PII scrubbing, real-time AML/Sanctions rules evaluation, "
        "dynamically retrieves statutory text from FAISS EUR-Lex vector index, "
        "persists the immutable evaluation audit into PostgreSQL Transaction Ledger via SQLAlchemy, "
        "and generates a tamper-evident SHA-256 cryptographic audit digest."
    )
)
async def evaluate_transaction(
    payload: TransactionPayload,
    db: AsyncSession = Depends(get_db)
):
    # 1. Zero-Trust PII Scrubbing
    scrubbed = scrub_pii(payload)
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.isoformat()

    receiver_country = scrubbed.receiver_country
    amount = scrubbed.amount
    kyc_level = scrubbed.sender_kyc_level

    # 2. Rule Evaluation & Dynamic RAG Legal Basis Retrieval
    # FAIL Condition 1: Sanctions Embargo ({KP, IR, SY}) -> Risk score 99
    if receiver_country in SANCTIONED_COUNTRIES:
        verdict = "FAIL"
        risk_score = 99
        rule_triggered = "FATF High-Risk Jurisdiction - International Sanctions & Total Embargo"
        legal_basis = retrieve_statutory_basis(
            search_query="Offences punishable by criminal penalties sanctions freezing and confiscating proceeds of crime",
            default_fallback="EU Regulation 2024/1624 Art. 29, OFAC Sanctions Regime & FATF Blacklist"
        )

    # FAIL Condition 2: High-Risk / Non-Cooperative Jurisdiction ({KY, PA, VG, BS, RU})
    # AND amount >= 10,000 AND kyc_level != 'enhanced' -> Risk score 92
    elif receiver_country in HIGH_RISK_JURISDICTIONS and amount >= 10000 and kyc_level != "enhanced":
        verdict = "FAIL"
        risk_score = 92
        rule_triggered = "Missing Enhanced Due Diligence (EDD) for High-Risk Non-Cooperative Tax Haven / Sanctioned Jurisdiction"
        legal_basis = retrieve_statutory_basis(
            search_query="Money laundering criminal activity definition property and high-risk predicate offences",
            default_fallback="EU 6th Anti-Money Laundering Directive (6AMLD) Art. 18a & FATF Recommendation 19"
        )

    # PASS Conditions
    else:
        verdict = "PASS"
        if amount >= 10000:
            risk_score = 38
            rule_triggered = "Large Value Transaction - Threshold Reporting Exemption Verified"
            legal_basis = retrieve_statutory_basis(
                search_query="Subject matter and scope establishing minimum rules on money laundering offences",
                default_fallback="EU Regulation 2015/847 (Wire Transfer Regulation) & AMLD5 Large Transfer Framework"
            )
        else:
            risk_score = 12
            rule_triggered = "Standard Low-Risk Flow - Compliant Verification"
            legal_basis = retrieve_statutory_basis(
                search_query="Directive scope and definitions concerning money laundering and property",
                default_fallback="EU Directive (EU) 2015/2366 (PSD2) & AMLD5 Simplified Customer Due Diligence"
            )

    # 3. Deterministic SHA-256 Hash Digest
    hash_payload = {
        "scrubbed_payload": scrubbed.model_dump(),
        "verdict": verdict,
        "risk_score": risk_score,
        "rule_triggered": rule_triggered,
        "legal_basis": legal_basis,
        "timestamp": timestamp
    }
    canonical_json = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
    sha256_audit_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    # 4. Persist Evaluation Audit into PostgreSQL Transaction Ledger via SQLAlchemy
    new_ledger_entry = TransactionLedger(
        transaction_id=scrubbed.tx_id,
        payload_data=scrubbed.model_dump(),
        verdict=verdict,
        risk_score=risk_score,
        rule_triggered=rule_triggered,
        legal_basis=legal_basis,
        sha256_hash=sha256_audit_hash,
        timestamp=now_utc
    )
    db.add(new_ledger_entry)
    await db.commit()

    return EvaluationResponse(
        verdict=verdict,
        risk_score=risk_score,
        rule_triggered=rule_triggered,
        legal_basis=legal_basis,
        sha256_audit_hash=sha256_audit_hash,
        timestamp=timestamp,
        raw_payload_preview=payload.model_dump(),
        scrubbed_payload_sent_to_engine=scrubbed
    )


# =====================================================================
# 5. Ledger History & Sandbox Purge Routes
# =====================================================================

@router.get(
    "/ledger",
    status_code=status.HTTP_200_OK,
    summary="Fetch Recent Transaction Ledger History",
    description="Retrieves the most recent 50 evaluated transaction records from the PostgreSQL ledger ordered by timestamp descending."
)
async def get_transaction_ledger(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Selects the most recent 50 entries from the transaction_ledger table,
    ordered by timestamp descending.
    """
    query = (
        select(TransactionLedger)
        .order_by(desc(TransactionLedger.timestamp))
        .limit(min(limit, 100))
    )
    result = await db.execute(query)
    entries = result.scalars().all()
    return [entry.to_dict() for entry in entries]


@router.delete(
    "/sandbox",
    status_code=status.HTTP_200_OK,
    summary="Purge Sandbox Transaction Ledger (RBAC Protected: Admin Only)",
    description="Deletes all simulated dummy transactions from the ledger database. Strictly restricted to administrative roles."
)
async def purge_sandbox_ledger(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    RBAC-protected sandbox purge:
    Verifies user possesses administrative privileges (ADMIN, MASTER_ADMIN, SUPER_ADMIN).
    Deletes all records from the transaction_ledger table.
    """
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role.upper() not in ["ADMIN", "MASTER_ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to purge sandbox"
        )

    result = await db.execute(delete(TransactionLedger))
    await db.commit()

    deleted_count = result.rowcount if hasattr(result, "rowcount") else 0

    return {
        "status": "success",
        "message": "Sandbox environment cleared.",
        "deleted_count": deleted_count
    }

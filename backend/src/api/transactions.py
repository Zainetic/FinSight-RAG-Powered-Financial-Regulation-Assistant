"""
FinSight RegTech - Automated Transaction Gatekeeper API
Machine-to-Machine Financial Compliance, Sanctions Screening, Zero-Trust PII Scrubbing, and SHA-256 Audit Anchoring.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal
from fastapi import APIRouter, status
from pydantic import BaseModel, Field


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
        description="Statutory legal framework or regulatory citation",
        example="EU AMLD5 Standard Due Diligence & PSD2 Exemption"
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
# 3. Gatekeeper Evaluation Endpoint
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
        "and generates a tamper-evident SHA-256 cryptographic audit digest."
    )
)
async def evaluate_transaction(payload: TransactionPayload):
    # 1. Zero-Trust PII Scrubbing
    scrubbed = scrub_pii(payload)
    timestamp = datetime.now(timezone.utc).isoformat()

    receiver_country = scrubbed.receiver_country
    amount = scrubbed.amount
    kyc_level = scrubbed.sender_kyc_level

    # 2. Rule Evaluation
    # FAIL Condition 1: Sanctions Embargo ({KP, IR, SY}) -> Risk score 99
    if receiver_country in SANCTIONED_COUNTRIES:
        verdict = "FAIL"
        risk_score = 99
        rule_triggered = "FATF High-Risk Jurisdiction - International Sanctions & Total Embargo"
        legal_basis = "EU Regulation 2024/1624 Art. 29, OFAC Sanctions Regime & FATF Blacklist"

    # FAIL Condition 2: High-Risk / Non-Cooperative Jurisdiction ({KY, PA, VG, BS, RU})
    # AND amount >= 10,000 AND kyc_level != 'enhanced' -> Risk score 92
    elif receiver_country in HIGH_RISK_JURISDICTIONS and amount >= 10000 and kyc_level != "enhanced":
        verdict = "FAIL"
        risk_score = 92
        rule_triggered = "Missing Enhanced Due Diligence (EDD) for High-Risk Non-Cooperative Tax Haven / Sanctioned Jurisdiction"
        legal_basis = "EU 6th Anti-Money Laundering Directive (6AMLD) Art. 18a & FATF Recommendation 19"

    # PASS Conditions
    else:
        verdict = "PASS"
        if amount >= 10000:
            risk_score = 38
            rule_triggered = "Large Value Transaction - Threshold Reporting Exemption Verified"
            legal_basis = "EU Regulation 2015/847 (Wire Transfer Regulation) & AMLD5 Large Transfer Framework"
        else:
            risk_score = 12
            rule_triggered = "Standard Low-Risk Flow - Compliant Verification"
            legal_basis = "EU Directive (EU) 2015/2366 (PSD2) & AMLD5 Simplified Customer Due Diligence"

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

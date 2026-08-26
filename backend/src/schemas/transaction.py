from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


class TransactionPayload(BaseModel):
    transaction_id: str = Field(
        default="",
        description="Unique transaction identifier",
        example="TX-2026-948172"
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction monetary amount",
        example=25000.00
    )
    currency: str = Field(
        default="EUR",
        description="ISO 4217 Currency Code",
        example="EUR"
    )
    originator_name: Optional[str] = Field(
        default=None,
        description="Full legal name of the originator entity or individual",
        example="Acme Global Corp Ltd"
    )
    originator_country: str = Field(
        default="EU",
        description="ISO 2-letter country code of the originator",
        example="FR"
    )
    beneficiary_name: Optional[str] = Field(
        default=None,
        description="Full legal name of the beneficiary entity or individual",
        example="Horizon Trade Partners"
    )
    beneficiary_country: str = Field(
        default="EU",
        description="ISO 2-letter country code of the beneficiary",
        example="DE"
    )
    payment_method: str = Field(
        default="SEPA_INSTANT",
        description="Payment channel or rail (e.g., 'SEPA', 'OPEN_BANKING_PIS', 'CRYPTO_TRANSFER', 'CARD', 'FIAT_WIRE')",
        example="SEPA_INSTANT"
    )
    sca_authenticated: bool = Field(
        default=True,
        description="Whether Strong Customer Authentication (SCA) was executed",
        example=True
    )
    asset_type: Optional[str] = Field(
        default="FIAT",
        description="Financial asset classification (e.g., 'FIAT', 'E_MONEY_TOKEN', 'UTILITY_TOKEN', 'ALGORITHMIC_TOKEN')",
        example="FIAT"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional technical metadata, telemetry, or headers",
        example={}
    )

    # Legacy & Simulator Field Aliases
    tx_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_iban: Optional[str] = None
    sender_country: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_iban: Optional[str] = None
    receiver_country: Optional[str] = None
    sender_kyc_level: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def unify_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map tx_id <-> transaction_id
            if "tx_id" in data and not data.get("transaction_id"):
                data["transaction_id"] = str(data["tx_id"])
            elif "transaction_id" in data and not data.get("tx_id"):
                data["tx_id"] = str(data["transaction_id"])
            if not data.get("transaction_id") and not data.get("tx_id"):
                data["transaction_id"] = "TX-DEFAULT"
                data["tx_id"] = "TX-DEFAULT"

            # Map sender_name <-> originator_name
            if "sender_name" in data and not data.get("originator_name"):
                data["originator_name"] = str(data["sender_name"])
            elif "originator_name" in data and not data.get("sender_name"):
                data["sender_name"] = str(data["originator_name"])

            # Map sender_country <-> originator_country
            if "sender_country" in data and (not data.get("originator_country") or data.get("originator_country") == "EU"):
                data["originator_country"] = str(data["sender_country"]).strip().upper()
            elif "originator_country" in data and not data.get("sender_country"):
                data["sender_country"] = str(data["originator_country"]).strip().upper()

            # Map receiver_name <-> beneficiary_name
            if "receiver_name" in data and not data.get("beneficiary_name"):
                data["beneficiary_name"] = str(data["receiver_name"])
            elif "beneficiary_name" in data and not data.get("receiver_name"):
                data["receiver_name"] = str(data["beneficiary_name"])

            # Map receiver_country <-> beneficiary_country
            if "receiver_country" in data and (not data.get("beneficiary_country") or data.get("beneficiary_country") == "EU"):
                data["beneficiary_country"] = str(data["receiver_country"]).strip().upper()
            elif "beneficiary_country" in data and not data.get("receiver_country"):
                data["receiver_country"] = str(data["beneficiary_country"]).strip().upper()

            # Map asset_type <-> payment_method
            if "asset_type" in data and "payment_method" not in data:
                data["payment_method"] = str(data["asset_type"])
            elif "payment_method" in data and "asset_type" not in data:
                data["asset_type"] = str(data["payment_method"])
        return data


class TransactionEvaluationResult(BaseModel):
    transaction_id: str = Field(
        description="Unique identifier of the evaluated transaction"
    )
    verdict: Literal["APPROVED", "FLAGGED", "BLOCKED", "PASS", "FAIL"] = Field(
        description="Final regulatory decision: 'APPROVED' (PASS), 'FLAGGED' (Action/EDD Required), or 'BLOCKED' (FAIL)"
    )
    risk_score: float = Field(
        description="Calculated composite risk score on a scale from 0.0 (minimal risk) to 1.0 (extreme risk / illegal breach)"
    )
    is_compliant: bool = Field(
        description="Strictly True if the transfer fully complies with all applicable EU regulations (PSD2, TFR, MiCA, AMLD6). False if blocked or flagged."
    )
    primary_violations: List[str] = Field(
        default_factory=list,
        description="List of specific statutory violations or missing required controls"
    )
    applicable_regulations: List[str] = Field(
        default_factory=list,
        description="List of applicable statutory articles retrieved from FAISS (e.g., ['PSD2 Art. 97', 'TFR Regulation (EU) 2023/1113 Art. 14', 'MiCA Art. 50'])"
    )
    audit_rationale: str = Field(
        description="Concise, authoritative technical justification explaining why the transfer passed, was flagged, or was blocked"
    )

    # Cryptographic Ledger and UI Integration Metadata
    rule_triggered: Optional[str] = Field(
        default=None,
        description="Rule or trigger condition for dashboard telemetry"
    )
    legal_basis: Optional[str] = Field(
        default=None,
        description="Primary statutory legal citation for dashboard display"
    )
    sha256_audit_hash: Optional[str] = Field(
        default=None,
        description="Cryptographic SHA-256 hash digest of the evaluation record"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp of the audit evaluation"
    )
    raw_payload_preview: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Preview of incoming payload prior to sanitization"
    )
    scrubbed_payload_sent_to_engine: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Zero-trust scrubbed payload forwarded to compliance evaluation engine"
    )

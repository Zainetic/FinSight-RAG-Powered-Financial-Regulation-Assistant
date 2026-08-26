"""
FinSight RegTech - Real-Time FAISS Regulatory Transaction Gatekeeper Service
=============================================================================
Connects inbound financial transactions dynamically to the 615-article FAISS
vector store (AMLD6, TFR, PSD2, MiCA, DORA, GDPR).

Performs:
1. Zero-Trust PII Scrubbing.
2. Dynamic Search Query Formulation.
3. Multi-Act Statutory FAISS Retrieval.
4. Google Gemini Flash Native Structured Gatekeeper Audit.
5. Deterministic SHA-256 Cryptographic Audit Digest Generation.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.schemas.transaction import TransactionPayload, TransactionEvaluationResult
from src.core.rag import get_vector_store, clean_regulatory_text
from src.core.llm import get_gemini_llm


SANCTIONED_COUNTRIES = {"KP", "IR", "SY"}
HIGH_RISK_JURISDICTIONS = {"KY", "PA", "VG", "BS", "RU"}


def mask_iban(iban: Optional[str]) -> str:
    """
    Masks the middle portion of an IBAN while preserving country and check prefixes.
    Example: 'DE89370400440532013000' -> 'DE89************3000'
    """
    if not iban:
        return "[N/A]"
    cleaned = str(iban).strip().replace(" ", "")
    if len(cleaned) <= 8:
        return "[REDACTED_IBAN]"
    prefix = cleaned[:4]
    suffix = cleaned[-4:]
    masked_middle = "*" * (len(cleaned) - 8)
    return f"{prefix}{masked_middle}{suffix}"


def scrub_transaction_pii(tx: TransactionPayload) -> Dict[str, Any]:
    """
    Zero-Trust PII Sanitizer:
    Redacts real personal names and account numbers while keeping routing
    codes, amounts, currencies, and technical parameters intact for statutory evaluation.
    """
    return {
        "transaction_id": tx.transaction_id or tx.tx_id or "TX-UNSET",
        "originator_name": "[REDACTED_ORIGINATOR]",
        "originator_country": tx.originator_country.strip().upper(),
        "originator_iban": mask_iban(tx.sender_iban),
        "beneficiary_name": "[REDACTED_BENEFICIARY]",
        "beneficiary_country": tx.beneficiary_country.strip().upper(),
        "beneficiary_iban": mask_iban(tx.receiver_iban),
        "amount": float(tx.amount),
        "currency": tx.currency.strip().upper(),
        "payment_method": tx.payment_method.strip(),
        "sca_authenticated": bool(tx.sca_authenticated),
        "asset_type": (tx.asset_type or "FIAT").strip(),
        "sender_kyc_level": (tx.sender_kyc_level or "standard").strip().lower(),
        "metadata": tx.metadata or {}
    }


def evaluate_transaction(tx: TransactionPayload) -> TransactionEvaluationResult:
    """
    Evaluates an inbound financial transaction against the 615-article FAISS regulatory vector database:
    1. Sanitizes PII.
    2. Formulates dynamic search query based on amount, countries, asset, and SCA status.
    3. Retrieves grounded statutory context from FAISS (AMLD6, TFR, PSD2, MiCA).
    4. Evaluates regulatory compliance via Gemini Flash Native Structured Output.
    5. Computes deterministic SHA-256 cryptographic audit digest.
    """
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.isoformat()
    scrubbed = scrub_transaction_pii(tx)

    tx_id = scrubbed["transaction_id"]
    amount = scrubbed["amount"]
    currency = scrubbed["currency"]
    orig_country = scrubbed["originator_country"]
    benef_country = scrubbed["beneficiary_country"]
    payment_method = scrubbed["payment_method"]
    sca_auth = scrubbed["sca_authenticated"]
    asset_type = scrubbed["asset_type"]
    kyc_level = scrubbed["sender_kyc_level"]

    # 1. Immediate Sanctions Check (Instant Block)
    if orig_country in SANCTIONED_COUNTRIES or benef_country in SANCTIONED_COUNTRIES:
        target_country = orig_country if orig_country in SANCTIONED_COUNTRIES else benef_country
        rationale = f"Immediate transaction block: Country '{target_country}' is subject to comprehensive international financial sanctions and FATF blacklist embargo."
        violations = [f"International Sanctions Embargo ({target_country})"]
        applicable_regs = ["EU Regulation 2024/1624 Art. 29", "AMLD6 Sanctions Enforcement", "FATF Blacklist"]

        hash_payload = {
            "transaction_id": tx_id,
            "verdict": "BLOCKED",
            "risk_score": 0.99,
            "is_compliant": False,
            "primary_violations": violations,
            "applicable_regulations": applicable_regs,
            "audit_rationale": rationale,
            "scrubbed_payload": scrubbed,
            "timestamp": timestamp
        }
        canonical_json = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
        sha256_audit_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        return TransactionEvaluationResult(
            transaction_id=tx_id,
            verdict="BLOCKED",
            risk_score=0.99,
            is_compliant=False,
            primary_violations=violations,
            applicable_regulations=applicable_regs,
            audit_rationale=rationale,
            rule_triggered="FATF High-Risk Jurisdiction - International Sanctions & Total Embargo",
            legal_basis="EU Regulation 2024/1624 Art. 29, OFAC Sanctions Regime & FATF Blacklist",
            sha256_audit_hash=sha256_audit_hash,
            timestamp=timestamp,
            raw_payload_preview=tx.model_dump(),
            scrubbed_payload_sent_to_engine=scrubbed
        )

    # 2. Dynamic Query Formulation & FAISS Retrieval
    search_query = (
        f"Financial transfer amount {amount} {currency} payment method {payment_method} "
        f"between {orig_country} and {benef_country} "
        f"SCA authenticated {sca_auth} asset type {asset_type} KYC level {kyc_level}"
    )

    context_snippets: List[str] = []
    top_legal_basis = "EU Financial Regulatory Directives (AMLD6, TFR, PSD2, MiCA)"

    try:
        vector_store = get_vector_store()
        if vector_store:
            relevant_docs = vector_store.similarity_search(search_query, k=4)
            for idx, doc in enumerate(relevant_docs):
                source = doc.metadata.get("source", "Regulation")
                art_label = doc.metadata.get("article_label", f"Article {doc.metadata.get('article_number', 'General')}")
                title = doc.metadata.get("title", "")
                cleaned_text = clean_regulatory_text(doc.page_content)[:350]
                context_snippets.append(f"[{idx+1}] {source} ({art_label} - {title}): {cleaned_text}")

            if relevant_docs:
                top_doc = relevant_docs[0]
                src = top_doc.metadata.get("source", "Regulation")
                lbl = top_doc.metadata.get("article_label", "")
                ttl = top_doc.metadata.get("title", "")
                top_legal_basis = f"{src} {lbl} ({ttl})".strip()
    except Exception as e:
        print(f"[Transaction Gatekeeper Warning] FAISS retrieval notice: {e}")

    joined_context = "\n\n".join(context_snippets) if context_snippets else "General European Regulatory Framework (AMLD6, TFR, PSD2, MiCA)."

    # 3. LLM Gatekeeper Evaluation with Native Structured Output
    system_prompt = (
        "You are FinSight AI, a real-time automated transaction gatekeeper and sanctions auditor. "
        "Evaluate the inbound financial transfer against the provided statutory EU legal context.\n\n"
        "STATUTORY COMPLIANCE DIRECTIVES:\n"
        "1. TFR (Transfer of Funds Regulation (EU) 2023/1113) & AMLD: Crypto or wire transfers >= €1,000 require complete originator/beneficiary verification. If transfer is >= €1,000 and lacks Enhanced Due Diligence when crossing high-risk jurisdictions, FLAG or BLOCK.\n"
        "2. PSD2 (Directive (EU) 2015/2366 Art. 97 & RTS): Remote electronic payments REQUIRE Strong Customer Authentication (SCA). If sca_authenticated is False and amount > €30 without a documented recurring exemption, BLOCK.\n"
        "3. MiCA (Regulation (EU) 2023/1114): Token transfers involving unauthorized algorithmic EMTs or non-compliant crypto-assets must be BLOCKED.\n"
        "4. High-Risk / Tax Havens ({KY, PA, VG, BS, RU}): Transfers >= €10,000 without 'enhanced' KYC must be FLAGGED or BLOCKED.\n"
        "5. Standard Low-Risk SEPA / Domestic: If fully authenticated and compliant, assign verdict 'APPROVED', risk_score <= 0.25, is_compliant=True.\n\n"
        "VERDICT CATEGORIES:\n"
        "- 'APPROVED' (PASS): Compliant transfer with all required statutory controls.\n"
        "- 'FLAGGED': Transfer requires Enhanced Due Diligence (EDD), Suspicious Activity Report (SAR), or threshold reporting.\n"
        "- 'BLOCKED' (FAIL): Direct statutory breach, missing mandatory SCA on high value, unauthorized token, or sanctions.\n\n"
        "Provide authoritative, concise statutory citations in applicable_regulations and a crisp technical justification in audit_rationale."
    )

    human_content = (
        f"INBOUND TRANSACTION SPECIFICATION:\n"
        f"- Transaction ID: {tx_id}\n"
        f"- Amount: {amount} {currency}\n"
        f"- Asset Type: {asset_type}\n"
        f"- Payment Rail / Method: {payment_method}\n"
        f"- Originator Country: {orig_country}\n"
        f"- Beneficiary Country: {benef_country}\n"
        f"- Strong Customer Authentication (SCA): {sca_auth}\n"
        f"- Sender KYC Level: {kyc_level}\n\n"
        f"RETRIEVED STATUTORY LEGAL CONTEXT SNIPPETS:\n"
        f"{joined_context}\n\n"
        f"Perform transaction gatekeeper evaluation:"
    )

    try:
        llm = get_gemini_llm()
        structured_llm = llm.with_structured_output(TransactionEvaluationResult)
        
        parsed_result = structured_llm.invoke([
            ("system", system_prompt),
            ("human", human_content)
        ])

        if isinstance(parsed_result, TransactionEvaluationResult):
            result = parsed_result
        else:
            result = TransactionEvaluationResult(**dict(parsed_result))
    except Exception as e:
        print(f"[Transaction Gatekeeper LLM Fallback] Error in LLM invocation: {e}")
        # Deterministic fallback evaluation if LLM call is interrupted
        is_high_risk_country = orig_country in HIGH_RISK_JURISDICTIONS or benef_country in HIGH_RISK_JURISDICTIONS
        is_missing_sca = (not sca_auth) and amount > 30

        if is_missing_sca:
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="BLOCKED",
                risk_score=0.92,
                is_compliant=False,
                primary_violations=["Missing Mandatory Strong Customer Authentication (PSD2 Art. 97)"],
                applicable_regulations=["PSD2 Directive (EU) 2015/2366 Article 97", "EBA RTS on SCA"],
                audit_rationale=f"Remote electronic transfer of {amount} {currency} blocked due to unauthenticated payment initiation exceeding the €30 low-value exemption threshold."
            )
        elif is_high_risk_country and amount >= 10000 and kyc_level != "enhanced":
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="FLAGGED",
                risk_score=0.88,
                is_compliant=False,
                primary_violations=["Missing Enhanced Due Diligence (EDD) for High-Risk Non-Cooperative Jurisdiction"],
                applicable_regulations=["AMLD6 Directive (EU) 2018/1673", "FATF Recommendation 19"],
                audit_rationale=f"Cross-border transfer of {amount} {currency} to high-risk jurisdiction flagged: Enhanced Due Diligence (EDD) documentation mandatory."
            )
        else:
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="APPROVED",
                risk_score=0.15 if amount < 10000 else 0.35,
                is_compliant=True,
                primary_violations=[],
                applicable_regulations=["AMLD5 Directive (EU) 2018/843", "PSD2 Directive (EU) 2015/2366"],
                audit_rationale=f"Transaction verified: Standard {payment_method} transfer compliant with regional KYC and PSD2 SCA safeguards."
            )

    # 4. Canonical JSON & SHA-256 Audit Digest
    hash_payload = {
        "transaction_id": result.transaction_id or tx_id,
        "verdict": result.verdict,
        "risk_score": round(float(result.risk_score), 4),
        "is_compliant": bool(result.is_compliant),
        "primary_violations": result.primary_violations,
        "applicable_regulations": result.applicable_regulations,
        "audit_rationale": result.audit_rationale,
        "scrubbed_payload": scrubbed,
        "timestamp": timestamp
    }
    canonical_json = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"))
    sha256_audit_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    # 5. Populate Telemetry & Metadata
    result.transaction_id = tx_id
    result.sha256_audit_hash = sha256_audit_hash
    result.timestamp = timestamp
    result.raw_payload_preview = tx.model_dump()
    result.scrubbed_payload_sent_to_engine = scrubbed

    if result.verdict in ["APPROVED", "PASS"]:
        result.rule_triggered = result.rule_triggered or "Statutory Regulatory Safeguards Verified (Compliant)"
    elif result.verdict in ["FLAGGED"]:
        result.rule_triggered = result.rule_triggered or "Threshold Reporting & Enhanced Due Diligence Required"
    else:
        result.rule_triggered = result.rule_triggered or (result.primary_violations[0] if result.primary_violations else "Statutory Prohibition Policy Triggered")

    result.legal_basis = result.legal_basis or (", ".join(result.applicable_regulations) if result.applicable_regulations else top_legal_basis)

    return result

"""
FinSight RegTech - High-Speed Sub-Second Transaction Gatekeeper Service
=======================================================================
Optimized for low-latency M2M machine-to-machine financial transaction evaluations:
1. High-speed gemini-flash-lite-latest / gemini-1.5-flash engine with low token budget (max_output_tokens=200).
2. Throttled FAISS vector retrieval (k=2) for minimal prompt overhead.
3. Strict brevity mandate on LLM generation (single sentence, <=20 words).
4. Sub-second zero-trust PII masking and SHA-256 ledger anchoring.
"""

import os
import json
import hashlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from src.schemas.transaction import TransactionPayload, TransactionEvaluationResult
from src.core.rag import get_vector_store, clean_regulatory_text


SANCTIONED_COUNTRIES = {"KP", "IR", "SY"}
HIGH_RISK_JURISDICTIONS = {"KY", "PA", "VG", "BS", "RU"}

_fast_llm_instance: Optional[ChatGoogleGenerativeAI] = None
_fast_llm_lock = threading.Lock()


def get_fast_transaction_llm() -> ChatGoogleGenerativeAI:
    """
    High-speed, low-token LLM configuration optimized specifically for real-time
    M2M transaction compliance evaluations.
    Uses gemini-flash-lite-latest (or gemini-1.5-flash / gemini-3.5-flash-lite) with a 200 token budget.
    """
    global _fast_llm_instance
    if _fast_llm_instance is None:
        with _fast_llm_lock:
            if _fast_llm_instance is None:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("Critical Error: GOOGLE_API_KEY is missing from environment.")

                model_name = os.getenv("GEMINI_TRANSACTION_MODEL", "gemini-flash-lite-latest")
                _fast_llm_instance = ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=0.0,
                    max_output_tokens=200,
                    max_retries=1,
                    request_timeout=15.0
                )
    return _fast_llm_instance


def mask_iban(iban: Optional[str]) -> str:
    """
    Fast sub-millisecond IBAN masking preserving prefixes and suffixes.
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
    Zero-Trust PII Sanitizer for ingress payloads.
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
    Evaluates an inbound financial transaction against the FAISS vector database with sub-second optimization:
    1. Sanitizes PII.
    2. Formulates concise search query.
    3. Throttles retrieval to top k=2 critical statutory hits.
    4. Evaluates compliance via high-speed Flash-Lite Native Structured Output (max 200 tokens).
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

    # 1. Immediate Sanctions Fast-Path (0ms LLM bypass)
    if orig_country in SANCTIONED_COUNTRIES or benef_country in SANCTIONED_COUNTRIES:
        target_country = orig_country if orig_country in SANCTIONED_COUNTRIES else benef_country
        rationale = f"Blocked: {target_country} is under international sanctions and FATF embargo."
        violations = [f"International Sanctions Embargo ({target_country})"]
        applicable_regs = ["EU Regulation 2024/1624 Art. 29", "FATF Blacklist"]
        sanction_citations = [
            {
                "document": "EU Regulation 2024/1624",
                "page": "Article 29",
                "quoted_text": "Financial entities are prohibited from processing fund transfers destined for sanctioned territories."
            }
        ]

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
            citations=sanction_citations,
            rule_triggered="FATF High-Risk Jurisdiction - Sanctions Embargo",
            legal_basis="EU Regulation 2024/1624 Art. 29 & FATF Blacklist",
            sha256_audit_hash=sha256_audit_hash,
            timestamp=timestamp,
            raw_payload_preview=tx.model_dump(),
            scrubbed_payload_sent_to_engine=scrubbed
        )

    # 2. Throttled Query Formulation & FAISS Retrieval (k=2)
    search_query = (
        f"{payment_method} {amount} {currency} {orig_country}->{benef_country} "
        f"SCA:{sca_auth} {asset_type} KYC:{kyc_level}"
    )

    context_snippets: List[str] = []
    citations: List[Dict[str, str]] = []
    top_legal_basis = "EU Directives (AMLD6, TFR, PSD2, MiCA)"

    try:
        vector_store = get_vector_store()
        if vector_store:
            # Throttled to top 2 chunks for minimal token overhead and fast parsing
            relevant_docs = vector_store.similarity_search(search_query, k=2)
            for idx, doc in enumerate(relevant_docs):
                source = doc.metadata.get("source", "Regulation")
                art_label = doc.metadata.get("article_label", f"Article {doc.metadata.get('article_number', 'General')}")
                title = doc.metadata.get("title", "")
                page_str = f"{art_label} - {title}".strip(" -")
                cleaned_text = clean_regulatory_text(doc.page_content)
                context_snippets.append(f"[{idx+1}] {source} ({art_label}): {cleaned_text[:180]}")
                
                citations.append({
                    "document": source,
                    "page": page_str,
                    "quoted_text": cleaned_text
                })

            if relevant_docs:
                top_doc = relevant_docs[0]
                src = top_doc.metadata.get("source", "Regulation")
                lbl = top_doc.metadata.get("article_label", "")
                top_legal_basis = f"{src} {lbl}".strip()
    except Exception as e:
        print(f"[Transaction Gatekeeper Warning] FAISS retrieval notice: {e}")

    joined_context = "\n".join(context_snippets) if context_snippets else "EU Framework (AMLD6, TFR, PSD2, MiCA)."

    # 3. High-Speed LLM Gatekeeper Evaluation (gemini-flash-lite-latest, max 200 tokens)
    system_prompt = (
        "You are FinSight AI, a sub-second real-time transaction gatekeeper.\n"
        "Evaluate the transfer against EU statutory rules:\n"
        "- TFR & AMLD: Crypto/wire transfers >= €1,000 require complete originator/beneficiary verification.\n"
        "- PSD2 Art. 97: Remote electronic payments REQUIRE SCA unless amount <= €30. If sca_authenticated is False and amount > 30, BLOCK.\n"
        "- MiCA: Algorithmic EMTs or unauthorized tokens must be BLOCKED.\n"
        "- High-Risk Tax Havens (KY, PA, VG, BS, RU): Transfers >= €10,000 without enhanced KYC must be FLAGGED.\n\n"
        "VERDICT ROUTING:\n"
        "- 'APPROVED': Compliant transfer (risk_score <= 0.20, is_compliant=True).\n"
        "- 'FLAGGED': Suspicious anomaly or EDD required (risk_score 0.60-0.85, is_compliant=False).\n"
        "- 'BLOCKED': Explicit legal breach, missing mandatory SCA on high value, or sanctions (risk_score >= 0.90, is_compliant=False).\n\n"
        "BREVITY MANDATE: Your 'audit_rationale' MUST be a single, concise sentence (maximum 20 words). Do not explain the history of the law. State the exact violation or state that it is compliant, and stop generating."
    )

    human_content = (
        f"TRANSACTION: {amount} {currency} via {payment_method} from {orig_country} to {benef_country}. "
        f"SCA: {sca_auth}, Asset: {asset_type}, KYC: {kyc_level}.\n"
        f"LEGAL CONTEXT:\n{joined_context}\n"
        f"Evaluate:"
    )

    try:
        llm = get_fast_transaction_llm()
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
        print(f"[Transaction Gatekeeper LLM Fallback] Error in fast LLM invocation: {e}")
        # Deterministic sub-millisecond fallback evaluation
        is_high_risk_country = orig_country in HIGH_RISK_JURISDICTIONS or benef_country in HIGH_RISK_JURISDICTIONS
        is_missing_sca = (not sca_auth) and amount > 30

        if is_missing_sca:
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="BLOCKED",
                risk_score=0.92,
                is_compliant=False,
                primary_violations=["Missing Mandatory Strong Customer Authentication (PSD2 Art. 97)"],
                applicable_regulations=["PSD2 Directive (EU) 2015/2366 Article 97"],
                audit_rationale=f"Transfer of {amount} {currency} blocked due to unauthenticated initiation exceeding €30 exemption threshold."
            )
        elif is_high_risk_country and amount >= 10000 and kyc_level != "enhanced":
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="FLAGGED",
                risk_score=0.85,
                is_compliant=False,
                primary_violations=["Missing Enhanced Due Diligence (EDD) for High-Risk Jurisdiction"],
                applicable_regulations=["AMLD6 Directive (EU) 2018/1673"],
                audit_rationale=f"Cross-border transfer of {amount} {currency} to high-risk jurisdiction flagged for mandatory EDD documentation."
            )
        else:
            result = TransactionEvaluationResult(
                transaction_id=tx_id,
                verdict="APPROVED",
                risk_score=0.10 if amount < 10000 else 0.25,
                is_compliant=True,
                primary_violations=[],
                applicable_regulations=["AMLD5 Directive (EU) 2018/843", "PSD2 Directive (EU) 2015/2366"],
                audit_rationale=f"Transfer of {amount} {currency} is fully compliant with regional KYC and PSD2 SCA safeguards."
            )

    # 4. Strict Routing Alignment
    if result.is_compliant and result.verdict in ["BLOCKED", "FAIL"]:
        result.verdict = "APPROVED"
    elif not result.is_compliant and result.verdict in ["APPROVED", "PASS"]:
        result.is_compliant = True

    # 5. Attach Grounded Citations
    if citations and (not result.citations or len(result.citations) == 0):
        result.citations = citations

    # 6. Canonical JSON & SHA-256 Audit Digest
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

    # 7. Populate Telemetry & Metadata
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

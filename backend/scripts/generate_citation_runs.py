"""
FinSight RegTech - 20-Sample Citation Grounding Generation Harness
===================================================================
Generates 20 fresh real-pipeline outputs:
- 10 Architecture Evaluations (5 compliant, 5 non-compliant across AI Act, PSD2, GDPR, MiCA, DORA)
- 10 Transaction Evaluations (3 sanctions fast-path, 7 FAISS + LLM gatekeeper path)

Saves all raw outputs as JSON in backend/data/citation_runs/ (git-excluded).
"""

import json
import os
import sys
import time
from datetime import UTC, datetime

# Setup paths and environment
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(BACKEND_DIR, "data", "citation_runs")

sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Use gemini-flash-lite-latest to avoid free-tier quota exhaustion on older models
os.environ["GEMINI_MODEL"] = "gemini-flash-lite-latest"

from src.core.rag import query_compliance_engine
from src.schemas.transaction import TransactionPayload
from src.services.transactions import evaluate_transaction

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 10 Architecture Prompts (5 Compliant / Minimal Risk, 5 Non-Compliant / High-Risk / Prohibited)
# ---------------------------------------------------------------------------
ARCH_PROMPTS = [
    {
        "id": "ARCH-01",
        "act": "EU AI Act",
        "expected": "Prohibited / Non-Compliant",
        "query": (
            "We are designing a real-time biometric identification system deployed in publicly accessible spaces "
            "for law enforcement and automated social profiling, which assigns credit and social risk scores to citizens "
            "without prior judicial authorization."
        ),
    },
    {
        "id": "ARCH-02",
        "act": "EU AI Act",
        "expected": "High-Risk / Compliant with Controls",
        "query": (
            "We are deploying a machine learning credit scoring model to evaluate retail loan applications. "
            "The architecture incorporates technical human-in-the-loop oversight dashboards, automatic anomaly detection, "
            "data governance quality validation on training datasets, and detailed audit logging of all automated decisions."
        ),
    },
    {
        "id": "ARCH-03",
        "act": "PSD2",
        "expected": "Compliant / Minimal Risk",
        "query": (
            "Our Open Banking Payment Initiation Service (PISP) connects to European ASPSPs via standardized REST APIs. "
            "Every remote electronic payment strictly enforces Strong Customer Authentication (SCA) using two-factor "
            "biometric tokens and dynamic linking of the transaction amount and beneficiary IBAN."
        ),
    },
    {
        "id": "ARCH-04",
        "act": "PSD2",
        "expected": "Non-Compliant / High-Risk",
        "query": (
            "We are implementing a one-click e-commerce checkout gateway that bypasses Strong Customer Authentication (SCA) "
            "for all remote credit card payments under €500 based solely on internal merchant trust scores, without applying "
            "formal Transaction Risk Analysis (TRA) or EBA regulatory technical standards exemptions."
        ),
    },
    {
        "id": "ARCH-05",
        "act": "GDPR",
        "expected": "Compliant / Minimal Risk",
        "query": (
            "Our financial data processing pipeline implements Data Protection by Design and by Default (Article 25). "
            "All customer identifiers are pseudonymized with salted SHA-256 hashes before entering analytics pipelines, "
            "PII is encrypted at rest with AES-256 GCM, and customer consent is tracked per processing purpose."
        ),
    },
    {
        "id": "ARCH-06",
        "act": "GDPR",
        "expected": "Non-Compliant / High-Risk",
        "query": (
            "Our customer onboarding service transfers unencrypted personal banking records and identity documents "
            "directly to an external third-party cloud analytics provider in a non-EU country that lacks an EU adequacy "
            "decision, without executing Standard Contractual Clauses (SCCs) or binding corporate rules."
        ),
    },
    {
        "id": "ARCH-07",
        "act": "MiCA",
        "expected": "Compliant / Minimal Risk",
        "query": (
            "We operate a Crypto-Asset Service Provider (CASP) offering custody and administration of crypto-assets. "
            "Clients' crypto-assets are held in segregated multi-signature cold storage wallets legally isolated from the "
            "firm's proprietary assets, with published white papers and full regulatory authorization."
        ),
    },
    {
        "id": "ARCH-08",
        "act": "MiCA",
        "expected": "Non-Compliant / Prohibited",
        "query": (
            "We are launching an algorithmic electronic money token (EMT) pegged to the Euro on a public blockchain. "
            "The token offers automatic 8% staking yields generated through algorithmic supply adjustments without holding "
            "a banking credit institution license or maintaining 1:1 liquid fiat reserves."
        ),
    },
    {
        "id": "ARCH-09",
        "act": "DORA",
        "expected": "Compliant / Minimal Risk",
        "query": (
            "Our core banking infrastructure implements an ICT risk management framework under DORA Article 5. "
            "It features active-active dual-region cloud redundancy within the EU, automated failover under 30 seconds, "
            "annual threat-led penetration testing (TLPT), and continuous monitoring with automated incident response playbooks."
        ),
    },
    {
        "id": "ARCH-10",
        "act": "DORA",
        "expected": "Non-Compliant / High-Risk",
        "query": (
            "Our payment processing ledger is hosted entirely on a single uncertified third-party cloud provider without "
            "geographic redundancy, without contractual audit inspection rights, and without any documented exit strategy or "
            "business continuity disaster recovery plan."
        ),
    },
]

# ---------------------------------------------------------------------------
# 10 Transaction Scenarios (3 Sanctions Fast-Path, 7 FAISS + LLM Path)
# ---------------------------------------------------------------------------
TX_SCENARIOS = [
    {
        "id": "TX-01",
        "type": "Sanctions Fast-Path",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-01",
            "amount": 5000.0,
            "currency": "EUR",
            "originator_country": "FR",
            "beneficiary_country": "KP",
            "payment_method": "FIAT_WIRE",
            "sca_authenticated": True,
            "sender_iban": "FR7630006000011234567890189",
            "receiver_iban": "KP991234567890123456",
        },
    },
    {
        "id": "TX-02",
        "type": "Sanctions Fast-Path",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-02",
            "amount": 12000.0,
            "currency": "EUR",
            "originator_country": "IR",
            "beneficiary_country": "DE",
            "payment_method": "SEPA_INSTANT",
            "sca_authenticated": True,
            "sender_iban": "IR8801234567890123456789",
            "receiver_iban": "DE89370400440532013000",
        },
    },
    {
        "id": "TX-03",
        "type": "Sanctions Fast-Path",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-03",
            "amount": 2500.0,
            "currency": "EUR",
            "originator_country": "SY",
            "beneficiary_country": "FR",
            "payment_method": "CARD",
            "sca_authenticated": True,
            "sender_iban": "SY55000123456789012345",
            "receiver_iban": "FR7630006000011234567890189",
        },
    },
    {
        "id": "TX-04",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "APPROVED",
        "payload": {
            "transaction_id": "TX-RUN-04",
            "amount": 450.0,
            "currency": "EUR",
            "originator_country": "FR",
            "beneficiary_country": "DE",
            "payment_method": "SEPA_INSTANT",
            "sca_authenticated": True,
            "sender_kyc_level": "standard",
            "sender_iban": "FR7630006000011234567890189",
            "receiver_iban": "DE89370400440532013000",
        },
    },
    {
        "id": "TX-05",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-05",
            "amount": 280.0,
            "currency": "EUR",
            "originator_country": "ES",
            "beneficiary_country": "IT",
            "payment_method": "OPEN_BANKING_PIS",
            "sca_authenticated": False,
            "sender_kyc_level": "standard",
            "sender_iban": "ES9121000418450200051332",
            "receiver_iban": "IT60X0542811101000000123456",
        },
    },
    {
        "id": "TX-06",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "FLAGGED",
        "payload": {
            "transaction_id": "TX-RUN-06",
            "amount": 75000.0,
            "currency": "EUR",
            "originator_country": "DE",
            "beneficiary_country": "KY",
            "payment_method": "FIAT_WIRE",
            "sca_authenticated": True,
            "sender_kyc_level": "standard",
            "sender_iban": "DE89370400440532013000",
            "receiver_iban": "KY55000123456789012345",
        },
    },
    {
        "id": "TX-07",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-07",
            "amount": 15000.0,
            "currency": "EUR",
            "originator_country": "FR",
            "beneficiary_country": "NL",
            "payment_method": "CRYPTO_TRANSFER",
            "asset_type": "CRYPTO",
            "sca_authenticated": False,
            "sender_kyc_level": "none",
            "metadata": {"travel_rule_compliant": False},
        },
    },
    {
        "id": "TX-08",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "APPROVED",
        "payload": {
            "transaction_id": "TX-RUN-08",
            "amount": 125000.0,
            "currency": "EUR",
            "originator_country": "DE",
            "beneficiary_country": "FR",
            "payment_method": "SEPA_CREDIT_TRANSFER",
            "sca_authenticated": True,
            "sender_kyc_level": "enhanced",
            "sender_iban": "DE89370400440532013000",
            "receiver_iban": "FR7630006000011234567890189",
        },
    },
    {
        "id": "TX-09",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "APPROVED",
        "payload": {
            "transaction_id": "TX-RUN-09",
            "amount": 14.50,
            "currency": "EUR",
            "originator_country": "FR",
            "beneficiary_country": "FR",
            "payment_method": "CARD_CONTACTLESS",
            "sca_authenticated": False,
            "sender_kyc_level": "standard",
            "sender_iban": "FR7630006000011234567890189",
            "receiver_iban": "FR7630006000011234567890999",
        },
    },
    {
        "id": "TX-10",
        "type": "FAISS + LLM Gatekeeper",
        "expected": "BLOCKED",
        "payload": {
            "transaction_id": "TX-RUN-10",
            "amount": 8000.0,
            "currency": "EUR",
            "originator_country": "NL",
            "beneficiary_country": "DE",
            "payment_method": "CRYPTO_TRANSFER",
            "asset_type": "ALGORITHMIC_TOKEN",
            "sca_authenticated": True,
            "sender_kyc_level": "standard",
            "metadata": {"token_type": "ALGORITHMIC_EMT", "licensed_issuer": False},
        },
    },
]


def run_all():
    print(f"[{datetime.now(UTC).isoformat()}] Starting 20-Sample Citation Evaluation Run...", flush=True)
    all_runs = []

    # 1. Run 10 Architecture Evaluations
    print("\n--- PHASE 1: 10 ARCHITECTURE EVALUATIONS ---", flush=True)
    for i, item in enumerate(ARCH_PROMPTS, 1):
        print(f"  [{i}/10] Evaluating Architecture {item['id']} ({item['act']})...", end=" ", flush=True)
        t0 = time.time()
        try:
            res = query_compliance_engine(item["query"], mode="strict")
            elapsed = round(time.time() - t0, 2)
            cits = res.get("citations", [])
            print(f"DONE in {elapsed}s (Risk: {res.get('risk_category')}, Citations: {len(cits)})", flush=True)

            run_record = {
                "id": item["id"],
                "run_type": "architecture_evaluation",
                "act": item["act"],
                "expected": item["expected"],
                "query": item["query"],
                "risk_category": res.get("risk_category"),
                "is_compliant": res.get("is_compliant"),
                "citations": cits,
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"FAILED in {elapsed}s: {e}", flush=True)
            run_record = {
                "id": item["id"],
                "run_type": "architecture_evaluation",
                "act": item["act"],
                "expected": item["expected"],
                "query": item["query"],
                "error": str(e),
                "citations": [],
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # Save individual run file
        filepath = os.path.join(OUTPUT_DIR, f"{item['id'].lower().replace('-', '_')}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(run_record, f, indent=2)
        all_runs.append(run_record)

    # 2. Run 10 Transaction Evaluations
    print("\n--- PHASE 2: 10 TRANSACTION EVALUATIONS ---", flush=True)
    for i, item in enumerate(TX_SCENARIOS, 1):
        print(f"  [{i}/10] Evaluating Transaction {item['id']} ({item['type']})...", end=" ", flush=True)
        t0 = time.time()
        try:
            tx_payload = TransactionPayload(**item["payload"])
            res = evaluate_transaction(tx_payload)
            elapsed = round(time.time() - t0, 2)
            cits = res.citations or []
            print(f"DONE in {elapsed}s (Verdict: {res.verdict}, Citations: {len(cits)})", flush=True)

            run_record = {
                "id": item["id"],
                "run_type": "transaction_evaluation",
                "type": item["type"],
                "expected": item["expected"],
                "payload": item["payload"],
                "verdict": res.verdict,
                "risk_score": res.risk_score,
                "is_compliant": res.is_compliant,
                "rule_triggered": res.rule_triggered,
                "legal_basis": res.legal_basis,
                "citations": [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in cits],
                "sha256_audit_hash": res.sha256_audit_hash,
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"FAILED in {elapsed}s: {e}", flush=True)
            run_record = {
                "id": item["id"],
                "run_type": "transaction_evaluation",
                "type": item["type"],
                "expected": item["expected"],
                "payload": item["payload"],
                "error": str(e),
                "citations": [],
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        # Save individual run file
        filepath = os.path.join(OUTPUT_DIR, f"{item['id'].lower().replace('-', '_')}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(run_record, f, indent=2)
        all_runs.append(run_record)

    # Save consolidated manifest
    manifest_path = os.path.join(OUTPUT_DIR, "manifest_20_runs.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_runs, f, indent=2)

    print(f"\nAll 20 fresh outputs successfully saved to: {OUTPUT_DIR}", flush=True)


if __name__ == "__main__":
    run_all()

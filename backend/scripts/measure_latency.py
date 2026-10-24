"""
FinSight RegTech - Latency Measurement Benchmark
Measures latency over at least 100 iterations with p50, p95, and p99 metrics.
Strictly separates:
1. Local Zero-Trust PII Scrubbing
2. Local Instant Sanctions Fast-Path (in-memory rule + hash digest)
3. Cloud LLM Transaction Gatekeeper (only if GOOGLE_API_KEY is available and active)
"""

import os
import statistics
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

# Path setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from src.schemas.transaction import TransactionPayload
from src.services.transactions import evaluate_transaction, scrub_transaction_pii


def calculate_percentiles(latencies_ms: list[float]) -> dict[str, float]:
    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)
    p50_idx = int(0.50 * (n - 1))
    p95_idx = int(0.95 * (n - 1))
    p99_idx = int(0.99 * (n - 1))

    return {
        "count": n,
        "min_ms": min(sorted_lats),
        "mean_ms": statistics.mean(sorted_lats),
        "p50_ms": sorted_lats[p50_idx],
        "p95_ms": sorted_lats[p95_idx],
        "p99_ms": sorted_lats[p99_idx],
        "max_ms": max(sorted_lats),
    }


def benchmark_pii_scrubbing(iterations: int = 100) -> dict[str, float]:
    tx = TransactionPayload(
        transaction_id="TX-BENCH-PII-001",
        amount=18450.00,
        currency="EUR",
        originator_name="Zain Ul Abidin",
        originator_country="FR",
        beneficiary_name="European Banking Corp",
        beneficiary_country="DE",
        payment_method="SEPA_INSTANT",
        sca_authenticated=True,
        asset_type="FIAT",
        sender_iban="FR7630006000011234567890189",
        receiver_iban="DE89370400440532013000",
    )

    # Warmup
    for _ in range(10):
        scrub_transaction_pii(tx)

    latencies_ms = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = scrub_transaction_pii(tx)
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    return calculate_percentiles(latencies_ms)


def benchmark_sanctions_fastpath(iterations: int = 100) -> dict[str, float]:
    tx = TransactionPayload(
        transaction_id="TX-BENCH-SANCTION-001",
        amount=50000.00,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="KP",  # Sanctioned
        payment_method="FIAT_WIRE",
        sca_authenticated=True,
        asset_type="FIAT",
    )

    # Warmup
    for _ in range(10):
        evaluate_transaction(tx)

    latencies_ms = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = evaluate_transaction(tx)
        t1 = time.perf_counter()
        assert res.verdict == "BLOCKED"
        latencies_ms.append((t1 - t0) * 1000.0)

    return calculate_percentiles(latencies_ms)


def benchmark_cloud_llm(iterations: int = 10) -> dict[str, float] | None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or "your_" in api_key.lower():
        print("ℹ️ GOOGLE_API_KEY not configured or placeholder. Skipping Cloud LLM benchmark.", flush=True)
        return None

    from src.schemas.transaction import TransactionEvaluationResult
    from src.services.transactions import get_fast_transaction_llm

    llm = get_fast_transaction_llm()
    structured_llm = llm.with_structured_output(TransactionEvaluationResult)

    system_prompt = (
        "You are FinSight AI, a deterministic real-time transaction gatekeeper.\n"
        "Evaluate the inbound transfer strictly according to statutory EU rules:\n\n"
        "STATUTORY DECISION MATRIX:\n"
        "1. APPROVED: The transfer is standard SEPA/fiat within the EU, or amounts < €1,000, or complies with all KYC and Strong Customer Authentication (SCA) rules. Set risk_score <= 0.20, is_compliant=True.\n"
        "2. BLOCKED: The transfer involves sanctioned jurisdictions (e.g., Syria, North Korea), unauthorized algorithmic EMT tokens (MiCA), unauthenticated remote electronic payments > €30 (PSD2 Art. 97), or non-custodial crypto transfers >= €1,000 lacking required identity data (TFR). Set risk_score >= 0.90, is_compliant=False.\n"
        "3. FLAGGED: High-value offshore transfers (e.g., Cayman Islands, Panama, Bahamas) or transfers >= €10,000 requiring Enhanced Due Diligence (EDD) without explicit sanctions. Set risk_score 0.60-0.85, is_compliant=False.\n\n"
        "BREVITY: Keep 'audit_rationale' to a concise single sentence (maximum 25 words). State the exact compliance status or violation directly."
    )
    human_content = (
        "INBOUND TRANSACTION:\n"
        "- Transaction ID: TX-BENCH-LLM-001\n"
        "- Amount: 750.00 EUR\n"
        "- Asset Type: FIAT\n"
        "- Payment Method: SEPA_INSTANT\n"
        "- Originator: FR (KYC: standard)\n"
        "- Beneficiary: DE\n"
        "- SCA Authenticated: True\n\n"
        "RETRIEVED STATUTORY CONTEXT:\nEU Financial Regulatory Framework (PSD2, AMLD6, MiCA).\n\n"
        "Output structured evaluation:"
    )

    latencies_ms = []
    print(f"Executing {iterations} requests against Cloud Gemini Flash Gatekeeper...", flush=True)
    for i in range(iterations):
        try:
            t0 = time.perf_counter()
            res = structured_llm.invoke([("system", system_prompt), ("human", human_content)])
            t1 = time.perf_counter()
            dur = (t1 - t0) * 1000.0
            latencies_ms.append(dur)
            verdict = getattr(res, "verdict", "UNKNOWN")
            print(f"  Iteration {i + 1}/{iterations}: {dur:.2f} ms (verdict={verdict})", flush=True)
            # Short pause to prevent burst rate limit / 503 errors on external API
            if i < iterations - 1:
                time.sleep(1.0)
        except Exception as e:
            print(f"  Benchmark stopped at iteration {i + 1} due to API limit: {e}", flush=True)
            break

    if not latencies_ms:
        return None
    return calculate_percentiles(latencies_ms)


if __name__ == "__main__":
    print("=" * 70, flush=True)
    print(" FINSIGHT REGTECH: REPRODUCIBLE LATENCY MEASUREMENT ", flush=True)
    print("=" * 70, flush=True)

    print("\n1. Measuring Zero-Trust PII Scrubbing (100 iterations)...", flush=True)
    pii_metrics = benchmark_pii_scrubbing(100)
    print(
        f"   p50: {pii_metrics['p50_ms']:.4f} ms | p95: {pii_metrics['p95_ms']:.4f} ms | p99: {pii_metrics['p99_ms']:.4f} ms",
        flush=True,
    )
    print(
        f"   min: {pii_metrics['min_ms']:.4f} ms | mean: {pii_metrics['mean_ms']:.4f} ms | max: {pii_metrics['max_ms']:.4f} ms",
        flush=True,
    )

    print("\n2. Measuring Instant Sanctions Fast-Path (100 iterations)...", flush=True)
    sanctions_metrics = benchmark_sanctions_fastpath(100)
    print(
        f"   p50: {sanctions_metrics['p50_ms']:.4f} ms | p95: {sanctions_metrics['p95_ms']:.4f} ms | p99: {sanctions_metrics['p99_ms']:.4f} ms",
        flush=True,
    )
    print(
        f"   min: {sanctions_metrics['min_ms']:.4f} ms | mean: {sanctions_metrics['mean_ms']:.4f} ms | max: {sanctions_metrics['max_ms']:.4f} ms",
        flush=True,
    )

    print("\n3. Measuring Cloud LLM Path (Gemini Flash)...", flush=True)
    llm_metrics = benchmark_cloud_llm(5)

    print("\n" + "=" * 70)
    print(" SUMMARY TABLE (Markdown)")
    print("=" * 70)
    print("| Operation | Scope | Iterations | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    print(
        f"| **Zero-Trust PII Scrubbing** | Local In-Memory | 100 | {pii_metrics['p50_ms']:.3f} | {pii_metrics['p95_ms']:.3f} | {pii_metrics['p99_ms']:.3f} | {pii_metrics['mean_ms']:.3f} |"
    )
    print(
        f"| **Instant Sanctions Fast-Path** | Local In-Memory + SHA-256 | 100 | {sanctions_metrics['p50_ms']:.3f} | {sanctions_metrics['p95_ms']:.3f} | {sanctions_metrics['p99_ms']:.3f} | {sanctions_metrics['mean_ms']:.3f} |"
    )
    if llm_metrics:
        print(
            f"| **Cloud LLM Gatekeeper** | Google Cloud Gemini Flash | {llm_metrics['count']} | {llm_metrics['p50_ms']:.2f} | {llm_metrics['p95_ms']:.2f} | {llm_metrics['p99_ms']:.2f} | {llm_metrics['mean_ms']:.2f} |"
        )
    else:
        print("| **Cloud LLM Gatekeeper** | Google Cloud Gemini Flash | N/A (Offline) | N/A | N/A | N/A | N/A |")
    print("=" * 70)

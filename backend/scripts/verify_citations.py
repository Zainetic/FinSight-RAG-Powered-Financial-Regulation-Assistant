"""
FinSight RegTech - Statutory Citation Verification Engine
==========================================================
Verifies that statutory citations and quoted excerpts produced by the RAG engine
or stored in the PostgreSQL ledger match verbatim text in official EU statutes
(located in backend/data/raw_statutes/*.txt).

Features:
- Deterministic text normalization (whitespace, unicode quotes, hyphens).
- Verbatim substring containment check against official statutory corpora.
- Verification of ledger records from PostgreSQL database.
- Reproducible CLI report with precision percentages and failure forensics.
"""

import argparse
import json
import os
import re
import sys
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(BACKEND_DIR)
STATUTES_DIR = os.path.join(BACKEND_DIR, "data", "raw_statutes")

sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Framework mapping to raw files
STATUTE_FILES = {
    "AMLD5": "amld5_raw.txt",
    "AMLD6": "amld6_raw.txt",
    "DORA": "dora_raw.txt",
    "EU_AI_ACT": "eu_ai_act_raw.txt",
    "EU AI ACT": "eu_ai_act_raw.txt",
    "GDPR": "gdpr_raw.txt",
    "MICA": "mica_raw.txt",
    "PSD2": "psd2_raw.txt",
    "TFR": "tfr_raw.txt",
}

# Alias mapping for document titles appearing in citations
DOCUMENT_ALIASES = {
    "2015/2366": "PSD2",
    "PSD2": "PSD2",
    "2016/679": "GDPR",
    "GDPR": "GDPR",
    "2023/1114": "MICA",
    "MICA": "MICA",
    "2022/2554": "DORA",
    "DORA": "DORA",
    "2024/1689": "EU_AI_ACT",
    "AI ACT": "EU_AI_ACT",
    "EU AI ACT": "EU_AI_ACT",
    "2023/1113": "TFR",
    "TFR": "TFR",
    "2018/843": "AMLD5",
    "AMLD5": "AMLD5",
    "2018/1673": "AMLD6",
    "AMLD6": "AMLD6",
    "2024/1624": "AMLD6",  # Anti-Money Laundering Regulation
}

_raw_corpora_cache: dict[str, str] = {}
_normalized_corpora_cache: dict[str, str] = {}


def normalize_legal_text(text: str) -> str:
    """Normalizes whitespace, unicode punctuation, and casing for legal quote matching."""
    if not text:
        return ""
    # Replace non-breaking spaces and special unicode spaces
    t = text.replace("\xa0", " ").replace("\u200b", "")
    # Normalize curly quotes and hyphens
    t = t.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-")
    # Collapse multiple whitespaces/newlines into single space
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def load_statute_corpus(act_key: str) -> str | None:
    """Loads and caches the raw statute text from backend/data/raw_statutes/."""
    canonical_act = act_key.upper().strip()
    filename = STATUTE_FILES.get(canonical_act)
    if not filename:
        for alias, mapped in DOCUMENT_ALIASES.items():
            if alias in canonical_act:
                filename = STATUTE_FILES.get(mapped)
                break

    if not filename:
        return None

    if filename in _raw_corpora_cache:
        return _raw_corpora_cache[filename]

    filepath = os.path.join(STATUTES_DIR, filename)
    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    _raw_corpora_cache[filename] = content
    _normalized_corpora_cache[filename] = normalize_legal_text(content)
    return _raw_corpora_cache[filename]


def verify_single_citation(citation: dict[str, Any]) -> dict[str, Any]:
    """
    Verifies a citation dictionary against the official statute corpus.
    Expected keys:
    - document: Act name or CELEX/filename
    - page: Article label or section
    - quoted_text: Quoted excerpt
    """
    doc_name = str(citation.get("document", ""))
    page = str(citation.get("page", ""))
    raw_quote = str(citation.get("quoted_text", "")).strip()

    if not raw_quote:
        return {
            "document": doc_name,
            "page": page,
            "status": "EMPTY_QUOTE",
            "is_verbatim": False,
            "character_length": 0,
            "match_snippet": None,
        }

    # Resolve corpus
    corpus = None
    target_filename = None
    for act_name, filename in STATUTE_FILES.items():
        if act_name in doc_name.upper():
            corpus = load_statute_corpus(act_name)
            target_filename = filename
            break

    if not corpus:
        for alias, mapped in DOCUMENT_ALIASES.items():
            if alias in doc_name:
                corpus = load_statute_corpus(mapped)
                target_filename = STATUTE_FILES.get(mapped)
                break

    # Fallback: search across all 8 corpora if specific act not identified
    if not corpus:
        corpora_to_search = list(STATUTE_FILES.keys())
    else:
        corpora_to_search = [k for k, v in STATUTE_FILES.items() if v == target_filename]

    norm_quote = normalize_legal_text(raw_quote)

    for act_key in corpora_to_search:
        load_statute_corpus(act_key)
        filename = STATUTE_FILES[act_key]
        norm_corpus = _normalized_corpora_cache.get(filename, "")

        # 1. Exact normalized substring match
        if norm_quote in norm_corpus:
            idx = norm_corpus.find(norm_quote)
            snippet_start = max(0, idx - 40)
            snippet_end = min(len(norm_corpus), idx + len(norm_quote) + 40)
            return {
                "document": doc_name,
                "act_matched": act_key,
                "source_file": filename,
                "page": page,
                "status": "VERBATIM_CONFIRMED",
                "is_verbatim": True,
                "character_length": len(norm_quote),
                "context_snippet": f"...{norm_corpus[snippet_start:snippet_end]}...",
            }

        # 2. Sub-chunk match (first 80 characters for truncated quotes)
        short_quote = norm_quote[:80] if len(norm_quote) > 80 else norm_quote
        if len(short_quote) >= 30 and short_quote in norm_corpus:
            return {
                "document": doc_name,
                "act_matched": act_key,
                "source_file": filename,
                "page": page,
                "status": "PARTIAL_MATCH",
                "is_verbatim": False,
                "character_length": len(norm_quote),
                "context_snippet": f"Partial match found in {filename}.",
            }

    return {
        "document": doc_name,
        "page": page,
        "status": "UNGROUNDED_OR_HALLUCINATED",
        "is_verbatim": False,
        "character_length": len(norm_quote),
        "context_snippet": None,
    }


def run_self_test() -> list[dict[str, Any]]:
    """Runs a self-test with known statutory excerpts from all 8 frameworks."""
    fixtures = [
        {
            "document": "PSD2 Directive (EU) 2015/2366",
            "page": "Recital (7)",
            "quoted_text": "In recent years, the security risks relating to electronic payments have increased. This is due to the growing technical complexity of electronic payments, the continuously growing volumes of electronic payments worldwide and emerging types of payment services.",
        },
        {
            "document": "GDPR Regulation (EU) 2016/679",
            "page": "Article 25",
            "quoted_text": "Taking into account the state of the art, the cost of implementation and the nature, scope, context and purposes of processing",
        },
        {
            "document": "MiCA Regulation (EU) 2023/1114",
            "page": "Recital (2)",
            "quoted_text": "Crypto-assets are one of the main applications of distributed ledger technology. Crypto-assets are digital representations of value or of rights that have the potential to bring significant benefits to market participants, including retail holders of crypto-assets.",
        },
        {
            "document": "DORA Regulation (EU) 2022/2554",
            "page": "Article 5",
            "quoted_text": "Financial entities shall have in place an internal governance and control framework that ensures an effective and prudent management of ICT risk",
        },
        {
            "document": "EU AI Act Regulation (EU) 2024/1689",
            "page": "Article 14",
            "quoted_text": "High-risk AI systems shall be designed and developed in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons",
        },
        {
            "document": "TFR Regulation (EU) 2023/1113",
            "page": "Article 14",
            "quoted_text": "The crypto-asset service provider of the originator shall ensure that transfers of crypto-assets are accompanied by the following information on the originator",
        },
        {
            "document": "AMLD5 Directive (EU) 2018/843",
            "page": "Article 30",
            "quoted_text": "Member States shall ensure that corporate and other legal entities incorporated within their territory are required to obtain and hold adequate, accurate and current information on their beneficial ownership",
        },
        {
            "document": "AMLD6 Directive (EU) 2018/1673",
            "page": "Recital (1)",
            "quoted_text": "Money laundering and the related financing of terrorism and organised crime remain significant problems at Union level, thus damaging the integrity, stability and reputation of the financial sector and threatening the internal market and the internal security of the Union.",
        },
        {
            "document": "Synthetic Hallucination Test",
            "page": "Article 999",
            "quoted_text": "Financial algorithms must always use quantum computers to verify blockchain transactions according to interplanetary standards.",
        },
    ]

    results = []
    for fixture in fixtures:
        res = verify_single_citation(fixture)
        results.append(res)
    return results


def run_database_audit() -> list[dict[str, Any]]:
    """Fetches real citations recorded in the PostgreSQL audit ledger and verifies them."""
    from src.core.database import get_db_connection, init_db

    init_db()
    results = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT audit_id, timestamp, user_query, payload, prev_hash, tx_hash
                FROM compliance_ledger
                WHERE payload IS NOT NULL
                ORDER BY timestamp ASC
                LIMIT 50;
            """)
            rows = cur.fetchall()

        print(f"Loaded {len(rows)} ledger blocks from PostgreSQL for citation audit.", flush=True)
        for row in rows:
            audit_id = row[0]
            payload = row[3]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    continue

            citations = payload.get("citations", [])
            for cit in citations:
                if isinstance(cit, dict):
                    v = verify_single_citation(cit)
                    v["audit_id"] = str(audit_id)
                    results.append(v)

    return results


def print_report_table(results: list[dict[str, Any]], title: str):
    """Prints a structured Markdown summary table of verification results."""
    total = len(results)
    verbatim_count = sum(1 for r in results if r.get("status") == "VERBATIM_CONFIRMED")
    partial_count = sum(1 for r in results if r.get("status") == "PARTIAL_MATCH")
    ungrounded_count = sum(1 for r in results if r.get("status") in ("UNGROUNDED_OR_HALLUCINATED", "EMPTY_QUOTE"))

    precision = (verbatim_count / total * 100.0) if total > 0 else 0.0

    print("\n" + "=" * 80)
    print(f" STATUTORY CITATION VERIFICATION REPORT: {title} ")
    print("=" * 80)
    print(f"Total Citations Inspected: {total}")
    print(f"Verbatim Matches:          {verbatim_count} ({precision:.1f}%)")
    print(f"Partial / Sub-chunk:       {partial_count}")
    print(f"Ungrounded / Hallucinated: {ungrounded_count}")
    print("=" * 80)

    print("\n| # | Document / Act | Page / Article | Status | Match Length | Source Corpus |")
    print("| :--- | :--- | :--- | :---: | :---: | :--- |")
    for i, r in enumerate(results, 1):
        doc = r.get("document", "N/A")[:28]
        pg = r.get("page", "N/A")[:18]
        st = r.get("status", "N/A")
        ln = r.get("character_length", 0)
        src = r.get("source_file", "N/A")
        print(f"| {i} | {doc} | {pg} | `{st}` | {ln} chars | `{src}` |")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinSight RegTech Citation Verifier")
    parser.add_argument("--self-test", action="store_true", help="Run self-test on known statutory excerpts")
    parser.add_argument("--db", action="store_true", help="Audit citations stored in PostgreSQL audit ledger")
    args = parser.parse_args()

    if args.db:
        print("Auditing citations from PostgreSQL audit ledger...", flush=True)
        db_results = run_database_audit()
        if db_results:
            print_report_table(db_results, "PostgreSQL Ledger Records")
        else:
            print(
                "No citations found in recent database ledger blocks. Run transactions or evaluate to populate.",
                flush=True,
            )
    else:
        print("Running statutory citation self-test across all 8 European frameworks...", flush=True)
        self_results = run_self_test()
        print_report_table(self_results, "Statutory Grounding Self-Test (8 Frameworks)")

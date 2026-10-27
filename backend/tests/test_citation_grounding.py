"""
FinSight RegTech - Statutory Citation Grounding & Verbatim Verification Test Suite
==================================================================================
Tests that citations generated across the pipeline:
1. Sanctions Fast-Path bypass: Produces verbatim grounded citation against TFR Regulation (EU) 2023/1113.
2. FAISS Document Slicing: Slices exact text from retrieved chunks without LLM hallucination.
3. Citation Verifier: Validates that quotes match raw statutory corpora in backend/data/raw_statutes/*.txt.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BACKEND_DIR)

from unittest.mock import MagicMock, patch

from scripts.verify_citations import verify_single_citation
from src.schemas.transaction import TransactionPayload
from src.services.transactions import evaluate_transaction


def test_sanctions_fastpath_citation_is_verbatim_confirmed():
    """Confirms that sanctions fast path citation strictly matches raw EU statute text."""
    tx = TransactionPayload(
        transaction_id="TX-TEST-SANCTION-KP",
        amount=5000.0,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="KP",  # Sanctioned country (North Korea)
        payment_method="SEPA",
        sca_authenticated=True,
    )
    result = evaluate_transaction(tx)
    assert result.verdict == "BLOCKED"
    assert result.citations is not None and len(result.citations) > 0

    first_cit = result.citations[0]
    verification = verify_single_citation(first_cit)
    assert verification["status"] == "VERBATIM_CONFIRMED", (
        f"Sanctions citation was not verbatim confirmed: {verification}"
    )
    assert verification["is_verbatim"] is True
    assert verification["source_file"] == "tfr_raw.txt"


def test_iran_sanctions_fastpath_citation_verbatim():
    """Confirms IR sanctions bypass produces verbatim verified citation."""
    tx = TransactionPayload(
        transaction_id="TX-TEST-SANCTION-IR",
        amount=1000.0,
        currency="EUR",
        originator_country="IR",
        beneficiary_country="FR",
        payment_method="FIAT_WIRE",
        sca_authenticated=True,
    )
    result = evaluate_transaction(tx)
    assert result.verdict == "BLOCKED"
    assert result.citations is not None and len(result.citations) > 0
    verification = verify_single_citation(result.citations[0])
    assert verification["status"] == "VERBATIM_CONFIRMED"


def test_faiss_transaction_citations_grounded():
    """Confirms non-sanctioned transaction citations sliced from FAISS are verbatim confirmed."""
    tx = TransactionPayload(
        transaction_id="TX-TEST-SEPA-COMPLIANT",
        amount=450.0,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="DE",
        payment_method="SEPA_INSTANT",
        sca_authenticated=True,
    )

    mock_doc = MagicMock()
    mock_doc.page_content = (
        "In recent years, the security risks relating to electronic payments have increased. "
        "This is due to the growing technical complexity of electronic payments, the continuously "
        "growing volumes of electronic payments worldwide and emerging types of payment services."
    )
    mock_doc.metadata = {
        "source": "PSD2 Directive (EU) 2015/2366",
        "article_label": "Recital (7)",
        "title": "PSD2 - Recital (7)",
    }

    mock_vector_store = MagicMock()
    mock_vector_store.similarity_search.return_value = [mock_doc]

    with patch("src.services.transactions.get_vector_store", return_value=mock_vector_store):
        result = evaluate_transaction(tx)

    assert result.citations is not None and len(result.citations) > 0
    for cit in result.citations:
        verification = verify_single_citation(cit)
        assert verification["status"] == "VERBATIM_CONFIRMED", f"Citation failed grounding: {cit} -> {verification}"
        assert verification["is_verbatim"] is True
        assert verification["source_file"] == "psd2_raw.txt"

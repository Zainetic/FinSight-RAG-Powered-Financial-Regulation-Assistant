"""
Mocked LLM & Sanctions Fast-Path Tests
Tests the zero-latency sanctions bypass, deterministic fallback logic,
and mocked LLM structured outputs without hitting external cloud APIs.
"""

from unittest.mock import MagicMock, patch
from src.schemas.transaction import TransactionPayload, TransactionEvaluationResult
from src.services.transactions import evaluate_transaction
from src.core.auth import create_access_token, UserRole


def test_instant_sanctions_fastpath_kp():
    tx = TransactionPayload(
        transaction_id="TX-SANCTION-001",
        amount=500.0,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="KP",  # North Korea (Sanctioned)
        payment_method="SEPA",
        sca_authenticated=True
    )

    result = evaluate_transaction(tx)
    assert result.verdict == "BLOCKED"
    assert result.is_compliant is False
    assert result.risk_score >= 0.95
    assert any("Sanctions" in v for v in result.primary_violations)
    assert result.citations is not None and len(result.citations) > 0
    assert "2024/1624" in result.citations[0]["document"]
    assert len(result.sha256_audit_hash) == 64


def test_instant_sanctions_fastpath_ir():
    tx = TransactionPayload(
        transaction_id="TX-SANCTION-002",
        amount=12000.0,
        currency="EUR",
        originator_country="IR",  # Iran (Sanctioned)
        beneficiary_country="DE",
        payment_method="FIAT_WIRE",
        sca_authenticated=True
    )

    result = evaluate_transaction(tx)
    assert result.verdict == "BLOCKED"
    assert result.is_compliant is False
    assert "IR" in result.audit_rationale


def test_unauthenticated_high_value_sca_fallback():
    # Transaction lacking SCA with amount > 30 EUR
    tx = TransactionPayload(
        transaction_id="TX-NOSCA-001",
        amount=450.0,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="DE",
        payment_method="OPEN_BANKING_PIS",
        sca_authenticated=False  # Violation of PSD2 Art 97
    )

    with patch("src.services.transactions.get_vector_store", return_value=None):
        result = evaluate_transaction(tx)
        assert result.verdict == "BLOCKED"
        assert result.is_compliant is False
        assert any("PSD2" in reg for reg in result.applicable_regulations)


def test_mocked_llm_approved_transaction():
    tx = TransactionPayload(
        transaction_id="TX-OK-001",
        amount=250.0,
        currency="EUR",
        originator_country="FR",
        beneficiary_country="IT",
        payment_method="SEPA_INSTANT",
        sca_authenticated=True,
        asset_type="FIAT"
    )

    mock_llm_result = TransactionEvaluationResult(
        transaction_id="TX-OK-001",
        verdict="APPROVED",
        risk_score=0.05,
        is_compliant=True,
        primary_violations=[],
        applicable_regulations=["PSD2 Directive (EU) 2015/2366 Article 97"],
        audit_rationale="Transfer complies with SEPA Instant standards and Strong Customer Authentication mandates.",
        citations=[{
            "document": "PSD2 Directive (EU) 2015/2366",
            "page": "Article 97",
            "quoted_text": "Payment service providers shall apply strong customer authentication where the payer initiates an electronic payment transaction."
        }]
    )

    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = mock_llm_result

    mock_base_llm = MagicMock()
    mock_base_llm.with_structured_output.return_value = mock_structured_llm

    with patch("src.services.transactions.get_vector_store", return_value=None), \
         patch("src.services.transactions.get_fast_transaction_llm", return_value=mock_base_llm):
        result = evaluate_transaction(tx)
        assert result.verdict == "APPROVED"
        assert result.is_compliant is True
        assert result.risk_score == 0.05
        assert len(result.sha256_audit_hash) == 64


def test_mocked_streaming_evaluate_route(client, test_organization):
    org_id = test_organization["id"]
    token = create_access_token({
        "id": "test-user-id",
        "sub": "tester@test.org",
        "email": "tester@test.org",
        "org_id": org_id,
        "role": UserRole.DEVELOPER.value,
        "org_name": test_organization["name"]
    })

    async def mock_stream_generator(*args, **kwargs):
        yield {"type": "start", "citations": [{"document": "GDPR", "page": "Article 25", "quoted_text": "Data protection by design."}]}
        yield {"type": "token", "content": "Compliant architecture: "}
        yield {"type": "token", "content": "All applicable EU statutory requirements satisfied."}

    with patch("src.api.routes.astream_compliance_engine", side_effect=mock_stream_generator):
        response = client.post(
            "/api/v1/evaluate",
            json={
                "query": "Evaluating our data architecture for privacy by design under GDPR Art 25.",
                "jurisdictions": ["EU (AI Act, GDPR, PSD2)"],
                "history": [],
                "mode": "strict"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = response.text
        assert 'data: {"type": "start"' in body
        assert 'data: {"type": "token"' in body
        assert 'data: {"type": "done"' in body

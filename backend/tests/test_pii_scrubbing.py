"""
Unit Tests for Zero-Trust PII Scrubbing and IBAN Masking
Verifies that names and IBANs are redacted while routing, amounts, and jurisdictions are preserved.
"""

from src.schemas.transaction import TransactionPayload
from src.services.transactions import mask_iban, scrub_transaction_pii


def test_mask_iban_standard_formats():
    # German IBAN (22 chars)
    de_iban = "DE89370400440532013000"
    masked_de = mask_iban(de_iban)
    assert masked_de.startswith("DE89")
    assert masked_de.endswith("3000")
    assert len(masked_de) == len(de_iban)
    assert "*" * 14 in masked_de

    # French IBAN (27 chars)
    fr_iban = "FR7630006000011234567890189"
    masked_fr = mask_iban(fr_iban)
    assert masked_fr.startswith("FR76")
    assert masked_fr.endswith("0189")
    assert len(masked_fr) == len(fr_iban)
    assert "*" * (len(fr_iban) - 8) in masked_fr


def test_mask_iban_edge_cases():
    assert mask_iban(None) == "[N/A]"
    assert mask_iban("") == "[N/A]"
    assert mask_iban("SHORT") == "[REDACTED_IBAN]"
    assert mask_iban("12345678") == "[REDACTED_IBAN]"
    # With spaces
    spaced_iban = "DE89 3704 0044 0532 0130 00"
    masked_spaced = mask_iban(spaced_iban)
    assert masked_spaced.startswith("DE89")
    assert masked_spaced.endswith("3000")


def test_scrub_transaction_pii_preserves_technical_parameters():
    tx = TransactionPayload(
        transaction_id="TX-TEST-778899",
        amount=42500.75,
        currency="EUR",
        originator_name="Jean-Luc Picard",
        originator_country="FR",
        beneficiary_name="Beverly Crusher",
        beneficiary_country="DE",
        payment_method="SEPA_INSTANT",
        sca_authenticated=True,
        asset_type="FIAT",
        sender_iban="FR7630006000011234567890189",
        receiver_iban="DE89370400440532013000",
    )

    scrubbed = scrub_transaction_pii(tx)

    # 1. Redaction of direct identifiers
    assert scrubbed["originator_name"] == "[REDACTED_ORIGINATOR]"
    assert scrubbed["beneficiary_name"] == "[REDACTED_BENEFICIARY]"
    assert "Jean-Luc" not in str(scrubbed)
    assert "Beverly" not in str(scrubbed)

    # 2. Masking of account numbers
    assert scrubbed["originator_iban"] == "FR76*******************0189"
    assert scrubbed["beneficiary_iban"] == "DE89**************3000"
    assert "11234567890" not in str(scrubbed)

    # 3. Strict preservation of financial, routing, and regulatory telemetry
    assert scrubbed["transaction_id"] == "TX-TEST-778899"
    assert scrubbed["amount"] == 42500.75
    assert scrubbed["currency"] == "EUR"
    assert scrubbed["originator_country"] == "FR"
    assert scrubbed["beneficiary_country"] == "DE"
    assert scrubbed["payment_method"] == "SEPA_INSTANT"
    assert scrubbed["sca_authenticated"] is True
    assert scrubbed["asset_type"] == "FIAT"

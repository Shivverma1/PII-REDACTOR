"""Unit tests: one detection case per PII type (positive and negative),
plus pipeline-level tests for consistency and overlap handling.

The document under redaction contains no SSNs, credit cards, IPs or DOBs,
so these synthetic fixtures are the evidence that those detectors work.
"""

import pytest

from pii_redactor.engine import detect, redact
from pii_redactor.types import PIIType


def spans_of(text: str, pii_type: PIIType, use_ner: bool = False):
    return [s for s in detect(text, use_ner=use_ner) if s.type == pii_type]


# --------------------------------------------------------------------------
# Positive cases: every PII type must be found.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pii_type,sample", [
    (PIIType.EMAIL, "contact rashi.patil@gmail.com today"),
    (PIIType.EMAIL, "split cherag.gyara \n@icicibank.co \nm here"),  # PDF artefact
    (PIIType.PHONE, "call +91 98765 43210 now"),
    (PIIType.PHONE, "Telephone: 020 4505 3237"),
    (PIIType.PHONE, "reach me at 9876543210"),
    (PIIType.SSN, "SSN 123-45-6789 on file"),
    (PIIType.CREDIT_CARD, "card 4111 1111 1111 1111 charged"),
    (PIIType.IP_ADDRESS, "login from 203.0.113.7 detected"),
    (PIIType.DATE_OF_BIRTH, "Date of Birth: 12 March 1985"),
    (PIIType.DATE_OF_BIRTH, "born on 03/07/1990"),
    (PIIType.CIN, "CIN U28129PN1979PLC141032 registered"),
    (PIIType.PAN, "PAN ABCPE1234F quoted"),
    (PIIType.URL, "see www.kshinternational.com for details"),
    (PIIType.ADDRESS,
     "Registered Office: 11/3 Village Birdewadi, Pune - 410 501, Maharashtra, India"),
])
def test_detects(pii_type, sample):
    assert spans_of(sample, pii_type), f"{pii_type} not found in {sample!r}"


# --------------------------------------------------------------------------
# Negative cases: things that look like PII but are not.
# --------------------------------------------------------------------------

def test_share_count_is_not_a_credit_card():
    # 16 digits but fails the Luhn checksum
    assert not spans_of("holding 1234 5678 9012 3456 shares", PIIType.CREDIT_CARD)


def test_financial_figure_is_not_a_phone():
    assert not spans_of("aggregating up to 4,200.00 million", PIIType.PHONE)


def test_bare_pin_number_is_not_an_address():
    assert not spans_of("a fee of 410 501 rupees was paid", PIIType.ADDRESS)


def test_public_regulator_domain_is_kept():
    assert not spans_of("filed at www.sebi.gov.in yesterday", PIIType.URL)


def test_invalid_ip_octet_rejected():
    assert not spans_of("version 999.1.2.3 released", PIIType.IP_ADDRESS)


def test_plain_document_date_is_not_a_dob():
    assert not spans_of("certificate dated December 10, 2025", PIIType.DATE_OF_BIRTH)


def test_statute_and_regulator_names_survive_redaction():
    text = (
        "Pursuant to the Companies Act, 2013 and SEBI ICDR Regulations, "
        "KSH International Limited filed with the Reserve Bank of India."
    )
    result = redact(text, use_ner=True)
    assert "Companies Act" in result.text
    assert "SEBI" in result.text
    assert "Reserve Bank of India" in result.text
    assert "KSH International Limited" not in result.text


# --------------------------------------------------------------------------
# Pipeline behaviour.
# --------------------------------------------------------------------------

def test_replacement_is_consistent():
    text = "mail a@b.com and later a@b.com again"
    result = redact(text, use_ner=False)
    fakes = [w for w in result.text.split() if "@example.com" in w]
    assert len(fakes) == 2 and fakes[0] == fakes[1]


def test_replacement_is_deterministic_across_runs():
    text = "mail someone@company.com now"
    assert redact(text, use_ner=False).text == redact(text, use_ner=False).text


def test_phone_format_is_preserved():
    original = "+ 91 20 4505 3237"
    result = redact(f"call {original} now", use_ner=False)
    fake = result.text[len("call "):-len(" now")]
    # same shape: "+ 91" country code and every space in the same position
    assert fake.startswith("+ 91 ")
    assert [i for i, c in enumerate(fake) if not c.isdigit()] == \
           [i for i, c in enumerate(original) if not c.isdigit()]
    assert "4505 3237" not in result.text  # local digits replaced


def test_no_original_email_survives():
    text = "x@y.com, sarthak.malvadkar@kshinternational.com"
    result = redact(text, use_ner=False)
    assert "y.com" not in result.text
    assert "kshinternational" not in result.text


def test_overlapping_spans_produce_valid_output():
    # email inside a URL-ish context plus a phone right after
    text = "www.acme.com support@acme.com +91 9876543210"
    result = redact(text, use_ner=False)
    assert "acme" not in result.text
    assert "9876543210" not in result.text

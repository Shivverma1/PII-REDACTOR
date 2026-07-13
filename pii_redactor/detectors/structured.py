"""Regex-based detectors for structured PII.

These patterns are deliberately tolerant of PDF-extraction artefacts:
text pulled out of table cells often carries stray line breaks inside an
e-mail address or phone number ("cherag.gyara \\n@icicibank.co \\nm",
"+ 91 20 \\n45053237"), so the patterns allow bounded whitespace where
those breaks occur.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..config import PUBLIC_DOMAINS
from ..types import PIIType, Span
from .base import Detector, register


class EmailDetector(Detector):
    """E-mail addresses, tolerating whitespace around "@" and a line break
    splitting the final TLD characters."""

    pii_type = PIIType.EMAIL
    _PATTERN = re.compile(
        r"[A-Za-z0-9._%+-]+\s{0,3}@\s{0,3}[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        r"(?:\s*\n\s*[a-z]{1,2}\b)?"
    )

    def detect(self, text: str) -> Iterable[Span]:
        return self._from_regex(text, self._PATTERN, self.pii_type)


class PhoneDetector(Detector):
    """Phone numbers in the three shapes that occur in Indian documents:

    * ``+91``-prefixed, with optional STD-code parentheses and up to three
      whitespace/hyphen characters between digits (line-break tolerant);
    * numbers following an explicit Telephone/Tel/Phone/Mobile/Fax label;
    * bare 10-digit mobiles starting 6-9, guarded against being part of a
      longer number or a decimal amount.

    Plain financial figures never match: they are comma-grouped and carry
    no label or country-code anchor.
    """

    pii_type = PIIType.PHONE
    _PLUS91 = re.compile(
        r"\+\s?91[\s\-]*(?:\(\d{2,4}\)[\s\-]*)?\d(?:[\s\-]{0,3}\d){7,11}"
    )
    _LABELLED = re.compile(
        r"(?i)(?:tel(?:ephone)?|phone|mobile|fax)\s*(?:no\.?|number)?\s*[:.]?\s*"
        r"(\+?\d(?:[\s\-\n()]?\d){7,13})"
    )
    _BARE_MOBILE = re.compile(r"(?<![\d.,])[6-9]\d{9}(?![\d.,])")

    def detect(self, text: str) -> Iterable[Span]:
        yield from self._from_regex(text, self._PLUS91, self.pii_type)
        for match in self._LABELLED.finditer(text):
            yield Span(match.start(1), match.end(1), self.pii_type, match.group(1))
        yield from self._from_regex(text, self._BARE_MOBILE, self.pii_type)


class SSNDetector(Detector):
    """US Social Security Numbers (AAA-GG-SSSS)."""

    pii_type = PIIType.SSN
    _PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    def detect(self, text: str) -> Iterable[Span]:
        return self._from_regex(text, self._PATTERN, self.pii_type)


class CreditCardDetector(Detector):
    """13-19 digit card numbers, optionally grouped by space or hyphen.

    Candidates must pass the Luhn checksum, so long share counts or
    reference numbers are not flagged.
    """

    pii_type = PIIType.CREDIT_CARD
    _PATTERN = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

    def detect(self, text: str) -> Iterable[Span]:
        for match in self._PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            if 13 <= len(digits) <= 19 and self._luhn_ok(digits):
                yield Span(match.start(), match.end(), self.pii_type, match.group())

    @staticmethod
    def _luhn_ok(digits: str) -> bool:
        total, double = 0, False
        for digit in reversed(digits):
            value = int(digit)
            if double:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
            double = not double
        return total % 10 == 0


class IPAddressDetector(Detector):
    """IPv4 addresses with octet-range validation (0-255)."""

    pii_type = PIIType.IP_ADDRESS
    _PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def detect(self, text: str) -> Iterable[Span]:
        for match in self._PATTERN.finditer(text):
            if all(int(octet) <= 255 for octet in match.group().split(".")):
                yield Span(match.start(), match.end(), self.pii_type, match.group())


class DateOfBirthDetector(Detector):
    """Dates appearing in an explicit birth context only.

    Policy: ordinary document dates (board resolutions, certificates,
    filing dates) are KEPT -- redacting every date would destroy the
    document. Only "Date of Birth: ...", "born on ..." and "DOB ..." are
    treated as PII.
    """

    pii_type = PIIType.DATE_OF_BIRTH
    _PATTERN = re.compile(
        r"(?i)(?:date\s+of\s+birth|born\s+on|d\.?o\.?b\.?)\s*[:\-]?\s*"
        r"(\d{1,2}[\s/\-.]\w{3,9}[\s/\-.,]+\d{2,4}"
        r"|\w{3,9}\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
    )

    def detect(self, text: str) -> Iterable[Span]:
        for match in self._PATTERN.finditer(text):
            yield Span(match.start(1), match.end(1), self.pii_type, match.group(1))


class CINDetector(Detector):
    """Indian Corporate Identity Numbers (e.g. U28129PN1979PLC141032)."""

    pii_type = PIIType.CIN
    _PATTERN = re.compile(r"\b[UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")

    def detect(self, text: str) -> Iterable[Span]:
        return self._from_regex(text, self._PATTERN, self.pii_type)


class PANDetector(Detector):
    """Indian Permanent Account Numbers (e.g. ABCPE1234F)."""

    pii_type = PIIType.PAN
    _PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

    def detect(self, text: str) -> Iterable[Span]:
        return self._from_regex(text, self._PATTERN, self.pii_type)


class URLDetector(Detector):
    """Websites and URLs, excluding public-institution domains.

    Policy: a company's own website identifies the company, so private
    domains are redacted; regulator / exchange / reference domains
    (see ``config.PUBLIC_DOMAINS``) are kept.
    """

    pii_type = PIIType.URL
    _PATTERN = re.compile(r"(?:https?://|www\.)[A-Za-z0-9.\-/_%?=&#]+")

    def detect(self, text: str) -> Iterable[Span]:
        for match in self._PATTERN.finditer(text):
            url = match.group().rstrip(".,)")
            if any(domain in url.lower() for domain in PUBLIC_DOMAINS):
                continue
            yield Span(match.start(), match.start() + len(url), self.pii_type, url)


def register_all() -> None:
    """Instantiate and register every structured detector."""
    for cls in (
        EmailDetector, PhoneDetector, SSNDetector, CreditCardDetector,
        IPAddressDetector, DateOfBirthDetector, CINDetector, PANDetector,
        URLDetector,
    ):
        register(cls())

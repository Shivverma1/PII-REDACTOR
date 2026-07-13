"""Core data types shared across the package."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PIIType(str, Enum):
    """Every PII category the tool can detect and replace.

    To support a new category: add a member here, implement a `Detector`
    (see ``detectors/base.py``) and a generator method on ``FakeFactory``
    (see ``anonymizer.py``). Nothing else needs to change.
    """

    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    IP_ADDRESS = "IP_ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    CIN = "CIN"                      # Indian Corporate Identity Number
    PAN = "PAN"                      # Indian Permanent Account Number
    URL = "URL"
    ADDRESS = "ADDRESS"
    COMPANY = "COMPANY"
    PERSON = "PERSON"

    def __str__(self) -> str:  # cleaner log / report output
        return self.value


@dataclass(frozen=True, order=True)
class Span:
    """A detected PII occurrence: a half-open range [start, end) in the text."""

    start: int
    end: int
    type: PIIType
    text: str

    def __len__(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

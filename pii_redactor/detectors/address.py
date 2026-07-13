"""Physical / mailing address detection.

Indian addresses in formal documents reliably end in a 6-digit PIN code,
so detection is anchored on the PIN and the span is expanded:

* backwards, up to a sentence stop (colon, semicolon, full stop that is
  not part of an abbreviation like "S. no.", or a blank line), and only
  kept when the window contains address vocabulary (street/office/village
  words) -- this keeps bare 6-digit figures out;
* forwards, through the trailing ", State, India".

Additionally, village-level locality names harvested from Village/Taluka/
Mauje phrases are redacted wherever else they appear (a plant table naming
just the village would otherwise leak the site).
"""

from __future__ import annotations

import re
from typing import Iterable

from ..types import PIIType, Span
from .base import Detector, register

PIN_RE = re.compile(r"\b\d{3}\s?\d{3}\b")

# Sentence stops that bound an address phrase; "." only counts when it is
# not part of an abbreviation like "S. no." or "No.".
ADDR_STOP = re.compile(r"[:;]|(?<![A-Z])(?<!No)(?<!no)\.\s|\n\s*\n")

ADDR_TAIL = re.compile(r"^(?:\s*,?\s*\(?[A-Z][a-z]+\)?){0,2}(?:\s*,\s*India)?")

ADDR_CONTEXT = re.compile(
    r"(?i)office|address|village|taluka|road|street|floor|tower|complex|"
    r"branch|situated|located|building|plot|nagar|marg|park|lane|society|"
    r"apartment|bungalow|bunglow|survey|s\.\s?no"
)

# Locality names directly attached to a Village/Taluka/Mauje keyword.
VILLAGE_RE = re.compile(
    r"\b(?:Village|Mauje)\s*[-–]?\s*([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?)"
    r"|\b([A-Z][a-z]{3,})\s+Taluka\b"
    r"|\bTaluka\s*[-–]?\s*([A-Z][a-z]{3,})"
)

#: How far back from a PIN code an address may start.
_WINDOW = 220


class AddressDetector(Detector):
    """PIN-code anchored address spans plus stand-alone locality names."""

    pii_type = PIIType.ADDRESS

    def detect(self, text: str) -> Iterable[Span]:
        yield from self._pin_anchored(text)
        yield from self._localities(text)

    def _pin_anchored(self, text: str) -> Iterable[Span]:
        for pin in PIN_RE.finditer(text):
            window_start = max(0, pin.start() - _WINDOW)
            window = text[window_start:pin.start()]

            cut = 0
            for stop in ADDR_STOP.finditer(window):
                cut = stop.end()
            window = window[cut:]
            if not ADDR_CONTEXT.search(window):
                continue  # a bare 6-digit number, not an address

            start = window_start + cut
            while start < pin.start() and not text[start].isalnum():
                start += 1
            tail = ADDR_TAIL.match(text[pin.end():pin.end() + 60])
            end = pin.end() + (tail.end() if tail else 0)
            yield Span(start, end, self.pii_type, text[start:end])

    def _localities(self, text: str) -> Iterable[Span]:
        names = {
            group
            for match in VILLAGE_RE.finditer(text)
            for group in match.groups()
            if group
        }
        for name in names:
            pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(text):
                yield Span(match.start(), match.end(), self.pii_type, match.group())


def register_all() -> None:
    register(AddressDetector())

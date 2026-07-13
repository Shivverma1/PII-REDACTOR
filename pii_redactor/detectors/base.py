"""Detector interface and registry.

A detector is any object with a ``detect(text) -> Iterable[Span]`` method.
Concrete detectors register themselves with :func:`register`, and the
engine simply iterates over :func:`all_detectors` -- so adding a new PII
type never requires touching the pipeline.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterable, Iterator

from ..types import PIIType, Span

_REGISTRY: list["Detector"] = []


class Detector(ABC):
    """Base class for all PII detectors."""

    #: The PII type this detector produces (informational; a detector may
    #: emit spans of other types too, e.g. the name detector emits both
    #: PERSON and COMPANY).
    pii_type: PIIType

    @abstractmethod
    def detect(self, text: str) -> Iterable[Span]:
        """Yield every occurrence of this detector's PII type in *text*."""

    def _from_regex(
        self, text: str, pattern: re.Pattern, pii_type: PIIType
    ) -> Iterator[Span]:
        for match in pattern.finditer(text):
            yield Span(match.start(), match.end(), pii_type, match.group())


def register(detector: Detector) -> Detector:
    """Add a detector instance to the global registry."""
    _REGISTRY.append(detector)
    return detector


def all_detectors(include_ner: bool = True) -> list[Detector]:
    """Return registered detectors, optionally excluding the (slow) NER one."""
    from .names import NameAndCompanyDetector  # local import: avoid cycle

    return [
        d for d in _REGISTRY
        if include_ner or not isinstance(d, NameAndCompanyDetector)
    ]

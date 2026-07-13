"""The redaction pipeline: detect -> resolve overlaps -> replace."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .anonymizer import FakeFactory
from .config import PRIORITY
from .detectors import all_detectors
from .types import Span

logger = logging.getLogger(__name__)


@dataclass
class RedactionResult:
    """Everything a caller needs after one redaction run."""

    text: str
    spans: list[Span] = field(default_factory=list)
    factory: FakeFactory = field(default_factory=FakeFactory)

    @property
    def mapping(self) -> dict[str, str]:
        return self.factory.mapping


def detect(text: str, use_ner: bool = True) -> list[Span]:
    """Run every registered detector and resolve overlapping spans."""
    spans: list[Span] = []
    for det in all_detectors(include_ner=use_ner):
        found = list(det.detect(text))
        logger.debug("%s found %d spans", type(det).__name__, len(found))
        spans.extend(found)
    return _resolve_overlaps(spans)


def redact(text: str, use_ner: bool = True) -> RedactionResult:
    """Produce the redacted text plus the span list and value mapping."""
    spans = detect(text, use_ner=use_ner)
    factory = FakeFactory()

    pieces: list[str] = []
    cursor = 0
    for span in spans:
        pieces.append(text[cursor:span.start])
        pieces.append(factory.fake(span.type, span.text))
        cursor = span.end
    pieces.append(text[cursor:])

    logger.info("replaced %d spans (%d unique values)", len(spans), len(factory.mapping))
    return RedactionResult(text="".join(pieces), spans=spans, factory=factory)


def _resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Keep the longest span at each position (ties: higher-priority type).

    A span that overlaps an already-kept span is trimmed to its
    non-overlapping tail rather than dropped, so an address that begins
    inside a previously matched company name is still redacted.
    """
    spans.sort(key=lambda s: (s.start, -len(s), PRIORITY.get(s.type, 99)))
    kept: list[Span] = []
    for span in spans:
        if kept and span.start < kept[-1].end:
            tail_start = kept[-1].end
            if span.end - tail_start > 3:
                offset = tail_start - span.start
                kept.append(Span(tail_start, span.end, span.type, span.text[offset:]))
            continue
        kept.append(span)
    return kept

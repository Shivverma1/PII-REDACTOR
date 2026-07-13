"""Evaluation helpers: detection report and residual scan.

The residual scan is the recall safety net: it re-runs the structured
detectors over the REDACTED output. Anything they find that the tool did
not generate itself is a potential leak and is reported loudly.
"""

from __future__ import annotations

from collections import Counter

from .detectors import all_detectors
from .engine import RedactionResult
from .types import PIIType, Span


def build_report(spans: list[Span]) -> str:
    """Human-readable per-type summary of what was redacted."""
    counts = Counter(span.type for span in spans)
    uniques: dict[PIIType, set[str]] = {}
    for span in spans:
        uniques.setdefault(span.type, set()).add(" ".join(span.text.split()).lower())

    lines = [
        f"{'PII type':<15}{'occurrences':>12}{'unique values':>15}",
        "-" * 42,
    ]
    for pii_type in sorted(counts, key=lambda t: -counts[t]):
        lines.append(f"{pii_type!s:<15}{counts[pii_type]:>12}{len(uniques[pii_type]):>15}")
    lines.append("-" * 42)
    lines.append(f"{'TOTAL':<15}{sum(counts.values()):>12}")
    return "\n".join(lines)


def residual_scan(result: RedactionResult) -> list[Span]:
    """Return structured-PII spans still present in the redacted output,
    excluding values the tool generated itself (fakes legitimately look
    like real e-mails, phone numbers and addresses)."""
    fakes = result.factory.generated_values()
    leftovers: list[Span] = []
    for detector in all_detectors(include_ner=False):
        for span in detector.detect(result.text):
            normalized = " ".join(span.text.split()).lower()
            if normalized in fakes:
                continue
            if any(fake in normalized for fake in fakes if len(fake) > 12):
                continue  # a fake with extra surrounding characters
            leftovers.append(span)
    return leftovers

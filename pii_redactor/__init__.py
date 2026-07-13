"""PII redaction tool: replaces personal data with realistic fakes."""

from .engine import RedactionResult, detect, redact
from .types import PIIType, Span

__version__ = "1.0.0"
__all__ = ["redact", "detect", "RedactionResult", "PIIType", "Span"]

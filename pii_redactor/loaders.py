"""Input loading: plain text or PDF (via PyMuPDF)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_text(path: str | Path) -> str:
    """Return the full text of *path*; PDFs are extracted page by page."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".pdf":
        import fitz  # PyMuPDF

        with fitz.open(path) as document:
            text = "\n".join(page.get_text() for page in document)
            logger.info("extracted %d pages, %d characters from %s",
                        len(document), len(text), path.name)
            return text

    text = path.read_text(encoding="utf-8")
    logger.info("read %d characters from %s", len(text), path.name)
    return text

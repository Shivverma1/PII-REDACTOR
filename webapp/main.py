"""Web front-end for the PII redaction tool.

Stateless by design: the uploaded document is processed in memory and the
redacted text + mapping are returned in the response -- nothing is written
to disk, so the service holds no PII at rest.

Run locally:   uvicorn webapp.main:app --reload
"""

from __future__ import annotations

import logging
import tempfile
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pii_redactor.engine import redact
from pii_redactor.evaluation import residual_scan

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("webapp")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".txt"}
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="PII Redaction Tool", version="1.0.0")

# Hashed JS/CSS bundles produced by `vite build` (webapp/frontend -> static/).
if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.on_event("startup")
def warm_up() -> None:
    """Load the spaCy model before the first request."""
    from pii_redactor.detectors.names import _load_nlp

    _load_nlp()
    logger.info("spaCy model loaded; ready to serve")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/redact")
async def redact_document(file: UploadFile = File(...), use_ner: bool = True):
    suffix = Path(file.filename or "upload.txt").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"unsupported file type {suffix!r}; use .pdf or .txt")

    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file exceeds the 20 MB limit")

    text = _extract_text(payload, suffix)
    logger.info("redacting %s (%d characters, ner=%s)", file.filename, len(text), use_ner)

    result = redact(text, use_ner=use_ner)
    leftovers = residual_scan(result)
    counts = Counter(str(span.type) for span in result.spans)

    return JSONResponse({
        "filename": file.filename,
        "characters": len(text),
        "redactions": sum(counts.values()),
        "unique_values": len(result.mapping),
        "by_type": dict(counts.most_common()),
        "residual_leftovers": len(leftovers),
        "redacted_text": result.text,
        "mapping": result.mapping,
    })


def _extract_text(payload: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        import fitz  # PyMuPDF

        # PyMuPDF requires a path or stream; use a NamedTemporaryFile that
        # is deleted immediately after extraction.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(payload)
            temp_path = handle.name
        try:
            with fitz.open(temp_path) as document:
                return "\n".join(page.get_text() for page in document)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "text file is not valid UTF-8") from exc

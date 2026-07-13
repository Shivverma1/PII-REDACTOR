"""Command-line interface.

Examples::

    python redact.py "Red Herring Prospectus.pdf"
    python redact.py input.txt -o out.txt --mapping map.json -v
    python redact.py input.pdf --no-ner        # structured PII only (fast)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .engine import redact
from .evaluation import build_report, residual_scan
from .loaders import load_text

logger = logging.getLogger("pii_redactor")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redact",
        description="Replace PII in a document with realistic fake values.",
    )
    parser.add_argument("input", help="input document (.pdf or .txt)")
    parser.add_argument(
        "-o", "--output",
        help="redacted output file (default: <input>.redacted.txt)",
    )
    parser.add_argument(
        "--mapping",
        help="write the original->fake mapping to this JSON file (audit trail)",
    )
    parser.add_argument(
        "--no-ner", action="store_true",
        help="skip spaCy NER; detect structured PII only (much faster)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        text = load_text(args.input)
    except FileNotFoundError:
        logger.error("input file not found: %s", args.input)
        return 2

    result = redact(text, use_ner=not args.no_ner)
    print(build_report(result.spans))

    leftovers = residual_scan(result)
    print(f"\nResidual scan of output: {len(leftovers)} potential leftovers")
    for span in leftovers[:10]:
        print(f"  !! {span.type}: {' '.join(span.text.split())[:100]!r}")

    output_path = Path(args.output) if args.output else (
        Path(args.input).with_suffix("").with_suffix(".redacted.txt")
    )
    output_path.write_text(result.text, encoding="utf-8")
    print(f"\nRedacted output written to {output_path}")

    if args.mapping:
        Path(args.mapping).write_text(
            json.dumps(result.mapping, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Original->fake mapping written to {args.mapping}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

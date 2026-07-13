#!/usr/bin/env python
"""Entry point: ``python redact.py <input> [options]``."""

import sys

from pii_redactor.cli import main

if __name__ == "__main__":
    sys.exit(main())

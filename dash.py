#!/usr/bin/env python3
"""Compatibility launcher routed to the canonical dashboard package in python/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from pogls_dashboard.launcher import run  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run())

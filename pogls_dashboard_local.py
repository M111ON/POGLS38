#!/usr/bin/env python3
"""Root launcher for the POGLS control room.

Keeps all dashboard runtime assets discoverable from repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from pogls_dashboard.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

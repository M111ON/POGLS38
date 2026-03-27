"""Canonical launcher entrypoint for the POGLS dashboard package."""

from __future__ import annotations

from typing import List, Optional

from .app import main


def run(argv: Optional[List[str]] = None) -> int:
    """Run dashboard using canonical app entrypoint."""
    return main(argv)

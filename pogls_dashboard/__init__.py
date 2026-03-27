"""Compatibility package that delegates to canonical `python/pogls_dashboard`."""

from __future__ import annotations

from pathlib import Path

_CANONICAL_DIR = (Path(__file__).resolve().parent.parent / "python" / "pogls_dashboard").resolve()

# Route all `pogls_dashboard.*` imports to the canonical package tree.
__path__ = [str(_CANONICAL_DIR)]

from .app import main  # type: ignore  # noqa: E402
from .launcher import run  # type: ignore  # noqa: E402

__all__ = ["main", "run"]

#!/usr/bin/env python3
"""Thin launcher that routes to the canonical dashboard entrypoint."""

from pogls_dashboard.launcher import run


if __name__ == "__main__":
    raise SystemExit(run())

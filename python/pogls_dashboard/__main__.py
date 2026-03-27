"""Module entrypoint for `python -m pogls_dashboard`."""

from .launcher import run


if __name__ == "__main__":
    raise SystemExit(run())

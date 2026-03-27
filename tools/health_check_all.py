#!/usr/bin/env python3
"""Read-only repository health checks.

Checks:
1) missing links in markdown
2) duplicate drift between mirrored folders
3) artifact noise tracked in git
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "ci" / "health_check_all.json"
MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


@dataclass
class Finding:
    kind: str
    path: str
    detail: str


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_excluded(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def iter_repo_files() -> list[Path]:
    return [p for p in ROOT.rglob("*") if p.is_file()]


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_missing_links(cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    includes = cfg.get("include", ["**/*.md"])
    excludes = cfg.get("exclude", [])

    for path in iter_repo_files():
        r = rel(path)
        if not any(fnmatch.fnmatch(r, pat) for pat in includes):
            continue
        if is_excluded(r, excludes):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        for link in MD_LINK_RE.findall(text):
            raw = link.strip().split()[0].strip("<>")
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if not target:
                continue

            target_path = (path.parent / target).resolve()
            if not target_path.exists():
                findings.append(Finding("missing_link", r, f"{raw} not found"))

    return findings


def check_duplicate_drift(cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    for pair in cfg.get("pairs", []):
        left = ROOT / pair["left"]
        right = ROOT / pair["right"]
        patterns = pair.get("include", ["**/*"])

        if not left.exists() or not right.exists():
            findings.append(
                Finding(
                    "duplicate_drift",
                    f"{pair['left']} <-> {pair['right']}",
                    "pair path missing",
                )
            )
            continue

        left_files = {
            p.relative_to(left).as_posix(): p
            for p in left.rglob("*")
            if p.is_file()
            and any(fnmatch.fnmatch(p.relative_to(left).as_posix(), pat) for pat in patterns)
        }
        right_files = {
            p.relative_to(right).as_posix(): p
            for p in right.rglob("*")
            if p.is_file()
            and any(fnmatch.fnmatch(p.relative_to(right).as_posix(), pat) for pat in patterns)
        }

        common = sorted(set(left_files.keys()) & set(right_files.keys()))
        for rp in common:
            if hash_file(left_files[rp]) != hash_file(right_files[rp]):
                findings.append(
                    Finding(
                        "duplicate_drift",
                        f"{pair['left']}/{rp}",
                        f"differs from {pair['right']}/{rp}",
                    )
                )

    return findings


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_artifact_noise(cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    forbidden = cfg.get("forbid_globs", [])
    for tracked in git_ls_files():
        if any(fnmatch.fnmatch(tracked, pat) for pat in forbidden):
            findings.append(Finding("artifact_noise", tracked, "forbidden artifact pattern"))
    return findings


def main() -> int:
    cfg = load_config()
    findings: list[Finding] = []

    if cfg.get("missing_links", {}).get("enabled", True):
        findings.extend(check_missing_links(cfg["missing_links"]))
    if cfg.get("duplicate_drift", {}).get("enabled", True):
        findings.extend(check_duplicate_drift(cfg["duplicate_drift"]))
    if cfg.get("artifact_noise", {}).get("enabled", True):
        findings.extend(check_artifact_noise(cfg["artifact_noise"]))

    if not findings:
        print("health_check_all: OK")
        return 0

    print("health_check_all: FAIL")
    for f in findings:
        print(f"- [{f.kind}] {f.path}: {f.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

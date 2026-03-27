from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from .mini_yaml import loads as mini_yaml_loads
from .models import ManifestLink, RepoConfig

DEFAULT_MANIFEST = """version: 1
repos:
  - name: POGLS38
    path: ..
    role: live
    track: true
    exclude_globs:
      - zip/**
      - *.zip
  - name: POGLS4
    path: ../../POGLS4
    role: durable
    track: true
    exclude_globs:
      - zip/**
      - *.zip
modules:
  temporal:
    tracked_paths:
      - pogls_38_temporal.h
      - test/test_38_temporal.c
  hydra:
    tracked_paths:
      - pogls_38_hydra.h
      - test/test_38_hydra.c
  wiring:
    tracked_paths:
      - pogls_38_wiring.h
      - test/test_38_wiring.c
  fabric:
    tracked_paths:
      - python/pogls_memory_fabric.py
  federation:
    tracked_paths:
      - federation_design.md
      - core_c/pogls_snapshot.c
links:
  - source: POGLS38:federation_design.md
    target: POGLS4:README.md
    kind: cross_repo
    label: federation design anchor
exports:
  formats:
    - json
    - markdown
"""


def _yaml_load(text: str):
    try:
        import yaml  # type: ignore
    except Exception:
        return mini_yaml_loads(text)
    return yaml.safe_load(text)


def load_manifest(path: Path) -> dict:
    if path.exists():
        return _yaml_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
    return _yaml_load(DEFAULT_MANIFEST) or {}


def resolve_manifest(base_dir: Path, manifest: dict, cli_repos: List[Tuple[str, Path]]) -> dict:
    repos: List[RepoConfig] = []
    manifest_repos = manifest.get("repos") or []
    seen = set()
    for item in manifest_repos:
        if not item or not item.get("track", True):
            continue
        name = item["name"]
        path = (base_dir / item.get("path", ".")).resolve()
        repos.append(
            RepoConfig(
                name=name,
                path=str(path),
                role=item.get("role", "project"),
                track=True,
                exclude_globs=list(item.get("exclude_globs") or []),
            )
        )
        seen.add(name)
    for name, path in cli_repos:
        if name not in seen:
            repos.append(RepoConfig(name=name, path=str(path.resolve()), role="project", track=True))
    links = [ManifestLink(**item) for item in (manifest.get("links") or []) if item]
    module_tracking: Dict[str, List[str]] = {}
    for module, cfg in (manifest.get("modules") or {}).items():
        module_tracking[module] = list((cfg or {}).get("tracked_paths") or [])
    export_formats = list(((manifest.get("exports") or {}).get("formats") or ["json", "markdown"]))
    return {
        "repos": repos,
        "links": links,
        "module_tracking": module_tracking,
        "export_formats": export_formats,
        "raw": manifest,
    }

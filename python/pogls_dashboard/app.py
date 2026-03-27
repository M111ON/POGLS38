from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .exporters import export_json, export_markdown
from .manifest import load_manifest, resolve_manifest
from .scanner import DashboardScanner
from .system_info import collect_system_info
from .views import HTML


class DashboardState:
    def __init__(self, manifest_path: Path, cli_repos: List[Tuple[str, Path]]):
        self.manifest_path = manifest_path
        self.cli_repos = cli_repos
        self.lock = threading.Lock()
        self.snapshot_data = {}
        self.scan()

    def scan(self) -> None:
        raw_manifest = load_manifest(self.manifest_path)
        resolved = resolve_manifest(self.manifest_path.parent, raw_manifest, self.cli_repos)
        scanner = DashboardScanner(resolved["repos"], resolved["module_tracking"], resolved["links"])
        data = scanner.scan()
        repos = {}
        for name, summary in data["repos"].items():
            repos[name] = {
                "summary": summary,
                "modules": {k: v for k, v in data["modules"].items() if any(fid.startswith(f"{name}:") for fid in v["files"]) or v["tracked_paths"]},
                "roadmap": data["roadmaps"].get(name, []),
                "runtime_checks": data["runtime_checks"].get(name, []),
                "files": {fid: file for fid, file in data["files"].items() if file["repo"] == name},
            }
        with self.lock:
            self.snapshot_data = {
                "generated_at": time.time(),
                "manifest_path": str(self.manifest_path),
                "export_formats": resolved["export_formats"],
                "system": collect_system_info(),
                "files": data["files"],
                "repos": repos,
                "archives": data.get("archives", {}),
                "duplicates": data.get("duplicates", []),
                "overview": {
                    "repo_count": len(repos),
                    "file_count": len(data["files"]),
                    "module_count": len(data["modules"]),
                    "roadmap_total": sum(len(r["roadmap"]) for r in repos.values()),
                    "roadmap_done": sum(sum(item["done"] for item in r["roadmap"]) for r in repos.values()),
                },
            }

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.snapshot_data))


class Handler(BaseHTTPRequestHandler):
    state: DashboardState = None  # type: ignore

    def _write(self, data: bytes, ctype: str, code: int = 200, filename: Optional[str] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/scan":
            self._write(json.dumps(self.state.snapshot(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/api/export":
            fmt = (parse_qs(parsed.query).get("format") or ["json"])[0]
            snap = self.state.snapshot()
            if fmt == "markdown":
                self._write(export_markdown(snap), "text/markdown; charset=utf-8", filename="pogls_dashboard_export.md")
            else:
                self._write(export_json(snap), "application/json; charset=utf-8", filename="pogls_dashboard_export.json")
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/rescan":
            self.state.scan()
            self._write(json.dumps({"ok": True, "generated_at": self.state.snapshot()["generated_at"]}).encode("utf-8"), "application/json; charset=utf-8")
            return
        self.send_error(404, "Not Found")

    def log_message(self, fmt: str, *args):
        sys.stdout.write("[dashboard] " + fmt % args + "\n")


def parse_repo_arg(raw: str) -> Tuple[str, Path]:
    if "=" in raw:
        name, path = raw.split("=", 1)
        return name.strip() or Path(path).name, Path(path).expanduser()
    path = Path(raw).expanduser()
    return path.name or "repo", path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="POGLS control room")
    ap.add_argument("--manifest", default="pogls_dashboard_manifest.yaml")
    ap.add_argument("--repo", action="append", default=[], help="Optional extra repo path or NAME=PATH")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args(argv)

    cli_repos = [parse_repo_arg(item) for item in args.repo]
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.exists() and args.manifest == "pogls_dashboard_manifest.yaml":
        legacy = Path("python/pogls_dashboard_manifest.yaml")
        if legacy.exists():
            manifest_path = legacy
    state = DashboardState(manifest_path.resolve(), cli_repos)
    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"POGLS Control Room listening on http://{args.host}:{args.port}")
    print(f"Manifest: {manifest_path.resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        server.server_close()
    return 0

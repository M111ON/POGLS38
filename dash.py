#!/usr/bin/env python3
"""
pogls_dashboard_local.py — Local multi-repo dashboard for POGLS projects
=======================================================================

Goal:
  * Standalone local Python dashboard (standard library only)
  * Track project progress / module completeness / runtime endpoints
  * Show file-to-file dependency links (includes/imports/tests/docs)
  * Support scanning one or more repos, e.g. POGLS38 + POGLS4

Usage:
  python3 python/pogls_dashboard_local.py
  python3 python/pogls_dashboard_local.py --repo /workspace/POGLS38
  python3 python/pogls_dashboard_local.py --repo /workspace/POGLS38 --repo /workspace/POGLS4
  python3 python/pogls_dashboard_local.py --repo POGLS38=/workspace/POGLS38 --repo POGLS4=/workspace/POGLS4

Open:
  http://127.0.0.1:8787/
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import posixpath
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

TEXT_EXTS = {
    ".c", ".cc", ".cpp", ".cu", ".h", ".hpp", ".hh", ".py", ".pyw",
    ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml",
}
IGNORE_DIRS = {
    ".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules",
    "dist", "build", ".venv", "venv", ".idea", ".vscode",
}
MODULE_PATTERNS = [
    ("hydra", ["hydra", "steal", "spawn"]),
    ("temporal", ["temporal", "bridge", "shadow", "timeline"]),
    ("repair", ["repair", "detach", "entangle", "fold", "recycle"]),
    ("wiring", ["wiring", "observer", "tentacle"]),
    ("gui", ["gui", "visualfeed", "controller"]),
    ("fabric", ["fabric", "ingest", "memory", "delta_bridge"]),
    ("benchmark", ["bench", "benchmark"]),
    ("federation", ["federation", "world_b", "snapshot", "merkle"]),
    ("tests", ["test_"]),
    ("docs", ["roadmap", "handoff", ".md"]),
]
PUBLIC_ENDPOINT_HINTS = ["/remember", "/recall", "/status", "/snapshot"]
CHECKBOX_RE = re.compile(r"^\s*- \[(?P<done>[ xX])\] (?P<label>.+?)\s*$")
BACKTICK_FILE_RE = re.compile(r"`([^`]+)`")
INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"')
IMPORT_RE = re.compile(r"^(?:from\s+([\w\.]+)\s+import|import\s+([\w\.,\s]+))")


def _safe_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


@dataclass
class FileNode:
    repo: str
    path: str
    abs_path: str
    ext: str
    size: int
    module: str
    outgoing: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    incoming: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    test_links: Set[str] = field(default_factory=set)
    doc_links: Set[str] = field(default_factory=set)
    roadmap_links: Set[str] = field(default_factory=set)
    exports: List[str] = field(default_factory=list)

    @property
    def file_id(self) -> str:
        return f"{self.repo}:{self.path}"


@dataclass
class ModuleStatus:
    name: str
    files: Set[str] = field(default_factory=set)
    tests: Set[str] = field(default_factory=set)
    docs: Set[str] = field(default_factory=set)
    roadmap_done: int = 0
    roadmap_total: int = 0
    runtime_endpoints: Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        score_parts = [
            25 if self.files else 0,
            min(25, len(self.tests) * 5),
            min(20, len(self.docs) * 5),
            min(15, len(self.runtime_endpoints) * 5),
            int(15 * (self.roadmap_done / self.roadmap_total)) if self.roadmap_total else 0,
        ]
        score = min(100, sum(score_parts))
        if score >= 80:
            state = "strong"
        elif score >= 50:
            state = "partial"
        else:
            state = "early"
        return {
            "name": self.name,
            "files": sorted(self.files),
            "tests": sorted(self.tests),
            "docs": sorted(self.docs),
            "roadmap_done": self.roadmap_done,
            "roadmap_total": self.roadmap_total,
            "runtime_endpoints": sorted(self.runtime_endpoints),
            "score": score,
            "state": state,
        }


class RepoScanner:
    def __init__(self, name: str, root: Path):
        self.name = name
        self.root = root.resolve()
        self.files: Dict[str, FileNode] = {}
        self._abs_to_id: Dict[str, str] = {}
        self._basename_to_ids: Dict[str, List[str]] = defaultdict(list)
        self._py_module_to_ids: Dict[str, List[str]] = defaultdict(list)
        self.module_status: Dict[str, ModuleStatus] = defaultdict(lambda: ModuleStatus(""))
        self.roadmap: List[dict] = []
        self.runtime_checks: List[dict] = []
        self.summary: Dict[str, object] = {}

    def scan(self) -> dict:
        self._index_files()
        self._parse_file_links()
        self._link_tests_and_docs()
        self._parse_roadmap()
        self._collect_runtime_hints()
        self._finalize_modules()
        self._build_summary()
        return self.to_dict()

    def _module_for(self, rel: str) -> str:
        lower = rel.lower()
        for name, tokens in MODULE_PATTERNS:
            if any(token in lower for token in tokens):
                return name
        top = rel.split("/", 1)[0]
        return top.replace(".", "_")

    def _module_from_label(self, label: str, refs: List[str]) -> str:
        if refs:
            counts = Counter(self.files[ref].module for ref in refs if ref in self.files)
            if counts:
                return counts.most_common(1)[0][0]
        lower = label.lower()
        for name, tokens in MODULE_PATTERNS:
            if any(token in lower for token in tokens):
                return name
        return "roadmap"

    def _index_files(self) -> None:
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            ext = path.suffix.lower()
            if ext and ext not in TEXT_EXTS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            rel = _safe_rel(path, self.root)
            module = self._module_for(rel)
            node = FileNode(
                repo=self.name,
                path=rel,
                abs_path=str(path),
                ext=ext,
                size=size,
                module=module,
            )
            file_id = node.file_id
            self.files[file_id] = node
            self._abs_to_id[str(path.resolve())] = file_id
            self._basename_to_ids[path.name].append(file_id)
            if ext in {".py", ".pyw"}:
                mod_name = rel[:-3] if ext == ".py" else rel[:-4]
                mod_name = mod_name.replace("/", ".")
                self._py_module_to_ids[mod_name].append(file_id)
                self._py_module_to_ids[Path(rel).stem].append(file_id)

    def _read_text(self, abs_path: str) -> str:
        try:
            return Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _add_edge(self, src_id: str, dst_id: str, edge_type: str) -> None:
        if src_id == dst_id:
            return
        self.files[src_id].outgoing[edge_type].add(dst_id)
        self.files[dst_id].incoming[edge_type].add(src_id)

    def _resolve_include(self, src_file: Path, target: str) -> Optional[str]:
        direct = (src_file.parent / target).resolve()
        if str(direct) in self._abs_to_id:
            return self._abs_to_id[str(direct)]
        name = Path(target).name
        matches = self._basename_to_ids.get(name, [])
        return matches[0] if matches else None

    def _resolve_python_import(self, src_rel: str, module_name: str) -> List[str]:
        results = []
        for name in (module_name, module_name.split(".")[0]):
            results.extend(self._py_module_to_ids.get(name, []))
        if not results and "." in module_name:
            tail = module_name.split(".")[-1]
            results.extend(self._py_module_to_ids.get(tail, []))
        # prefer same package depth
        return sorted(set(results))

    def _extract_exports(self, text: str, ext: str) -> List[str]:
        out: List[str] = []
        if ext in {".c", ".cc", ".cpp", ".cu", ".h", ".hpp", ".hh"}:
            for pat in [r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", r"typedef\s+struct\s+([A-Za-z_][A-Za-z0-9_]*)"]:
                for m in re.finditer(pat, text):
                    name = m.group(1)
                    if len(name) > 2 and name not in {"if", "for", "while", "switch", "return", "sizeof"}:
                        out.append(name)
        elif ext in {".py", ".pyw"}:
            try:
                tree = ast.parse(text)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        out.append(node.name)
            except SyntaxError:
                pass
        return sorted(set(out))[:60]

    def _parse_file_links(self) -> None:
        for file_id, node in self.files.items():
            text = self._read_text(node.abs_path)
            node.exports = self._extract_exports(text, node.ext)
            if node.ext in {".c", ".cc", ".cpp", ".cu", ".h", ".hpp", ".hh"}:
                src = Path(node.abs_path)
                for line in text.splitlines():
                    m = INCLUDE_RE.match(line)
                    if not m:
                        continue
                    target_id = self._resolve_include(src, m.group(1))
                    if target_id:
                        self._add_edge(file_id, target_id, "include")
            elif node.ext in {".py", ".pyw"}:
                try:
                    tree = ast.parse(text)
                except SyntaxError:
                    tree = None
                if tree is not None:
                    for item in ast.walk(tree):
                        if isinstance(item, ast.Import):
                            for alias in item.names:
                                for target_id in self._resolve_python_import(node.path, alias.name):
                                    self._add_edge(file_id, target_id, "import")
                        elif isinstance(item, ast.ImportFrom) and item.module:
                            for target_id in self._resolve_python_import(node.path, item.module):
                                self._add_edge(file_id, target_id, "import")

    def _link_tests_and_docs(self) -> None:
        for file_id, node in self.files.items():
            p = Path(node.path)
            if p.parts and p.parts[0] == "test":
                stem = p.stem.replace("test_", "")
                candidates = []
                for other_id, other in self.files.items():
                    if other_id == file_id or other.ext not in {".h", ".c", ".cpp", ".cu", ".py", ".pyw"}:
                        continue
                    other_stem = Path(other.path).stem
                    if stem == other_stem or stem in other_stem or other_stem in stem:
                        candidates.append(other_id)
                for target_id in sorted(set(candidates))[:8]:
                    self._add_edge(file_id, target_id, "tests")
                    self.files[target_id].test_links.add(file_id)
            if node.ext == ".md":
                text = self._read_text(node.abs_path)
                for match in BACKTICK_FILE_RE.finditer(text):
                    raw = match.group(1).strip()
                    name = Path(raw).name
                    for target_id in self._basename_to_ids.get(name, []):
                        self._add_edge(file_id, target_id, "doc")
                        self.files[target_id].doc_links.add(file_id)

    def _parse_roadmap(self) -> None:
        roadmap_path = self.root / "POGLS38_ROADMAP.md"
        if not roadmap_path.exists():
            return
        current_section = "root"
        for line in roadmap_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("## ") or line.startswith("### "):
                current_section = line.lstrip("# ").strip()
            m = CHECKBOX_RE.match(line)
            if not m:
                continue
            done = m.group("done").lower() == "x"
            label = m.group("label")
            refs = []
            for fmatch in BACKTICK_FILE_RE.finditer(label):
                raw = fmatch.group(1)
                name = Path(raw).name
                refs.extend(self._basename_to_ids.get(name, []))
            item = {
                "section": current_section,
                "done": done,
                "label": label,
                "refs": sorted(set(refs)),
            }
            self.roadmap.append(item)
            module = self._module_from_label(label, item["refs"])
            ms = self.module_status.setdefault(module, ModuleStatus(module))
            ms.roadmap_total += 1
            ms.roadmap_done += int(done)
            for ref in item["refs"]:
                self.files[ref].roadmap_links.add(f"{current_section}: {label}")
                self.files[ref].doc_links.add(f"{self.name}:POGLS38_ROADMAP.md")

    def _collect_runtime_hints(self) -> None:
        runtime_targets = [
            self.root / "python" / "pogls_memory_fabric.py",
            self.root / "gui" / "pogls_gui.pyw",
        ]
        for path in runtime_targets:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel = _safe_rel(path, self.root)
            hints = [endpoint for endpoint in PUBLIC_ENDPOINT_HINTS if endpoint in text]
            if hints:
                self.runtime_checks.append({
                    "file": rel,
                    "kind": "endpoints",
                    "items": hints,
                })
                module = self._module_for(rel)
                ms = self.module_status.setdefault(module, ModuleStatus(module))
                ms.runtime_endpoints.update(hints)

    def _finalize_modules(self) -> None:
        for file_id, node in self.files.items():
            ms = self.module_status.setdefault(node.module, ModuleStatus(node.module))
            ms.files.add(file_id)
            if node.path.startswith("test/"):
                ms.tests.add(file_id)
            if node.ext == ".md":
                ms.docs.add(file_id)
            for linked_test in node.test_links:
                ms.tests.add(linked_test)
            for linked_doc in node.doc_links:
                ms.docs.add(linked_doc)
        # ensure names filled
        for key, val in list(self.module_status.items()):
            if not val.name:
                val.name = key

    def _build_summary(self) -> None:
        edge_counts = Counter()
        for node in self.files.values():
            for edge_type, dsts in node.outgoing.items():
                edge_counts[edge_type] += len(dsts)
        total_done = sum(item["done"] for item in self.roadmap)
        self.summary = {
            "repo": self.name,
            "root": str(self.root),
            "file_count": len(self.files),
            "module_count": len(self.module_status),
            "roadmap_total": len(self.roadmap),
            "roadmap_done": total_done,
            "edge_counts": dict(edge_counts),
            "test_files": sum(1 for f in self.files.values() if f.path.startswith("test/")),
            "doc_files": sum(1 for f in self.files.values() if f.ext == ".md"),
            "runtime_checks": len(self.runtime_checks),
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "modules": {name: status.to_dict() for name, status in sorted(self.module_status.items())},
            "files": {
                file_id: {
                    "id": file_id,
                    "repo": node.repo,
                    "path": node.path,
                    "ext": node.ext,
                    "size": node.size,
                    "module": node.module,
                    "outgoing": {k: sorted(v) for k, v in sorted(node.outgoing.items())},
                    "incoming": {k: sorted(v) for k, v in sorted(node.incoming.items())},
                    "tests": sorted(node.test_links),
                    "docs": sorted(node.doc_links),
                    "roadmap": sorted(node.roadmap_links),
                    "exports": node.exports,
                }
                for file_id, node in sorted(self.files.items())
            },
            "roadmap": self.roadmap,
            "runtime_checks": self.runtime_checks,
        }


class DashboardState:
    def __init__(self, repos: List[Tuple[str, Path]]):
        self.repos = repos
        self.lock = threading.Lock()
        self.data: Dict[str, dict] = {}
        self.last_scan_at = 0.0
        self.scan()

    def scan(self) -> None:
        fresh = {}
        for name, root in self.repos:
            if root.exists():
                fresh[name] = RepoScanner(name, root).scan()
        with self.lock:
            self.data = fresh
            self.last_scan_at = time.time()

    def snapshot(self) -> dict:
        with self.lock:
            repos = self.data.copy()
            last_scan_at = self.last_scan_at
        summaries = [repo["summary"] for repo in repos.values()]
        return {
            "generated_at": last_scan_at,
            "repos": repos,
            "overview": {
                "repo_count": len(repos),
                "file_count": sum(item["file_count"] for item in summaries),
                "module_count": sum(item["module_count"] for item in summaries),
                "roadmap_total": sum(item["roadmap_total"] for item in summaries),
                "roadmap_done": sum(item["roadmap_done"] for item in summaries),
            },
        }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>POGLS Local Dashboard</title>
<style>
:root {
  --bg:#0b0d11; --panel:#121722; --card:#171d2b; --ink:#dfe7f5; --muted:#8ea0be;
  --accent:#50b7ff; --ok:#38d996; --warn:#f6c85f; --bad:#ff6b81; --border:#25304a;
}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--border);position:sticky;top:0;background:rgba(11,13,17,.96);backdrop-filter:blur(8px);z-index:5}
header h1{margin:0 0 6px;font-size:22px} header p{margin:0;color:var(--muted)}
main{padding:20px;display:grid;gap:18px}
.row{display:grid;gap:18px}.row.two{grid-template-columns:1.1fr .9fr}.row.three{grid-template-columns:repeat(3,1fr)}
.card{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:16px;box-shadow:0 12px 30px rgba(0,0,0,.18)}
.card h2,.card h3{margin:0 0 10px}.muted{color:var(--muted)} .small{font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.kpi{padding:12px;border-radius:12px;background:var(--card);border:1px solid var(--border)}
.kpi .v{font-size:26px;font-weight:700}.kpi .l{color:var(--muted)}
.list{display:grid;gap:10px}.pill{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid var(--border);background:var(--card);color:var(--muted);margin:2px 4px 0 0}
.state-strong{color:var(--ok)} .state-partial{color:var(--warn)} .state-early{color:var(--bad)}
.table-wrap{max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:12px}
table{width:100%;border-collapse:collapse} th,td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top} th{position:sticky;top:0;background:#121722;text-align:left}
tr:hover td{background:rgba(255,255,255,.02)}
input,select,button{background:#0e1420;color:var(--ink);border:1px solid var(--border);border-radius:10px;padding:8px 10px}
button{cursor:pointer} button:hover{border-color:var(--accent)}
.flex{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.file-link{color:var(--accent);cursor:pointer;text-decoration:none}.file-link:hover{text-decoration:underline}
pre{white-space:pre-wrap;word-break:break-word;background:#0e1420;border:1px solid var(--border);border-radius:12px;padding:12px;max-height:260px;overflow:auto}
@media (max-width:1100px){.row.two,.row.three,.kpis,.columns{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>POGLS Local Dashboard</h1>
  <p>Single local control room for roadmap progress, module completeness, runtime hints, and file dependency tracing across one or more repos.</p>
</header>
<main>
  <section class="card">
    <div class="flex" style="justify-content:space-between">
      <div>
        <h2>Overview</h2>
        <div class="small muted">Track POGLS38 now, add POGLS4 later by starting this app with another <code>--repo</code> path.</div>
      </div>
      <div class="flex">
        <label class="small muted">Repo</label>
        <select id="repoSelect"></select>
        <input id="fileSearch" placeholder="Filter files/modules…" />
        <button id="refreshBtn">Refresh scan</button>
      </div>
    </div>
    <div class="kpis" id="kpis"></div>
  </section>

  <section class="row two">
    <article class="card">
      <h2>Modules</h2>
      <div class="small muted">Completeness score = files + tests + docs + runtime hooks + roadmap state.</div>
      <div class="table-wrap"><table><thead><tr><th>Module</th><th>Score</th><th>State</th><th>Files</th><th>Tests</th><th>Roadmap</th><th>Runtime</th></tr></thead><tbody id="modulesBody"></tbody></table></div>
    </article>
    <article class="card">
      <h2>Runtime Hints</h2>
      <div class="list" id="runtimeList"></div>
      <h3 style="margin-top:18px">Roadmap Snapshot</h3>
      <div class="table-wrap" style="max-height:220px"><table><thead><tr><th>Status</th><th>Task</th></tr></thead><tbody id="roadmapBody"></tbody></table></div>
    </article>
  </section>

  <section class="row two">
    <article class="card">
      <h2>Files</h2>
      <div class="small muted">Auto-links come from include/import parsing, test heuristics, and docs/roadmap mentions.</div>
      <div class="table-wrap"><table><thead><tr><th>File</th><th>Module</th><th>Out</th><th>In</th><th>Tests</th><th>Docs/Roadmap</th></tr></thead><tbody id="filesBody"></tbody></table></div>
    </article>
    <article class="card">
      <h2>Dependency Inspector</h2>
      <div id="inspector" class="muted">Click a file to inspect incoming/outgoing links.</div>
    </article>
  </section>
</main>
<script>
let SNAP = null;
let repoName = null;
let selectedFile = null;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts || {});
  return await res.json();
}

function fmtTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function edgeCount(obj) {
  return Object.values(obj || {}).reduce((n, arr) => n + arr.length, 0);
}

function pickRepo() {
  const names = Object.keys(SNAP.repos || {});
  if (!repoName || !SNAP.repos[repoName]) repoName = names[0] || null;
  return repoName ? SNAP.repos[repoName] : null;
}

function renderRepoSelect() {
  const sel = document.getElementById('repoSelect');
  sel.innerHTML = '';
  Object.keys(SNAP.repos || {}).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    if (name === repoName) opt.selected = true;
    sel.appendChild(opt);
  });
}

function renderKPIs(repo) {
  const kpis = [
    ['Repos', SNAP.overview.repo_count],
    ['Files', repo.summary.file_count],
    ['Modules', repo.summary.module_count],
    ['Roadmap', `${repo.summary.roadmap_done}/${repo.summary.roadmap_total}`],
    ['Last scan', fmtTime(SNAP.generated_at)],
  ];
  document.getElementById('kpis').innerHTML = kpis.map(([l,v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
}

function renderModules(repo) {
  const q = document.getElementById('fileSearch').value.toLowerCase();
  const rows = Object.values(repo.modules)
    .filter(m => !q || m.name.toLowerCase().includes(q))
    .sort((a,b) => b.score - a.score)
    .map(m => `<tr>
      <td><strong>${m.name}</strong></td>
      <td>${m.score}</td>
      <td class="state-${m.state}">${m.state}</td>
      <td>${m.files.length}</td>
      <td>${m.tests.length}</td>
      <td>${m.roadmap_done}/${m.roadmap_total}</td>
      <td>${m.runtime_endpoints.map(x=>`<span class="pill">${x}</span>`).join('')}</td>
    </tr>`).join('');
  document.getElementById('modulesBody').innerHTML = rows || `<tr><td colspan="7" class="muted">No modules match filter.</td></tr>`;
}

function renderRuntime(repo) {
  document.getElementById('runtimeList').innerHTML = (repo.runtime_checks || []).map(item => `
    <div class="card" style="padding:12px;background:var(--card)">
      <div><strong>${item.file}</strong></div>
      <div class="small muted">${item.kind}</div>
      <div>${item.items.map(x => `<span class="pill">${x}</span>`).join('')}</div>
    </div>
  `).join('') || `<div class="muted">No runtime hints detected.</div>`;

  document.getElementById('roadmapBody').innerHTML = (repo.roadmap || []).slice(0, 40).map(item => `
    <tr><td>${item.done ? '✅' : '⬜'}</td><td>${item.label}</td></tr>
  `).join('') || `<tr><td colspan="2" class="muted">No roadmap found.</td></tr>`;
}

function renderFiles(repo) {
  const q = document.getElementById('fileSearch').value.toLowerCase();
  const rows = Object.values(repo.files)
    .filter(f => !q || f.path.toLowerCase().includes(q) || f.module.toLowerCase().includes(q))
    .sort((a,b) => edgeCount(b.outgoing) + edgeCount(b.incoming) - edgeCount(a.outgoing) - edgeCount(a.incoming))
    .slice(0, 250)
    .map(f => `
      <tr>
        <td><a class="file-link" data-file="${f.id}">${f.path}</a></td>
        <td>${f.module}</td>
        <td>${edgeCount(f.outgoing)}</td>
        <td>${edgeCount(f.incoming)}</td>
        <td>${f.tests.length}</td>
        <td>${f.docs.length + f.roadmap.length}</td>
      </tr>
    `).join('');
  document.getElementById('filesBody').innerHTML = rows || `<tr><td colspan="6" class="muted">No files match filter.</td></tr>`;
  document.querySelectorAll('[data-file]').forEach(el => el.onclick = () => { selectedFile = el.dataset.file; renderInspector(repo); });
}

function linkList(repo, ids) {
  if (!ids || !ids.length) return `<span class="muted">none</span>`;
  return ids.map(id => {
    const file = repo.files[id];
    if (!file) return `<span class="pill">${id}</span>`;
    return `<a class="file-link" data-file="${id}">${file.path}</a>`;
  }).join('<br/>');
}

function renderInspector(repo) {
  const box = document.getElementById('inspector');
  const file = selectedFile ? repo.files[selectedFile] : null;
  if (!file) {
    box.innerHTML = `<div class="muted">Click a file to inspect incoming/outgoing links, exports, tests, docs, and roadmap references.</div>`;
    return;
  }
  const edgeSections = Object.entries(file.outgoing || {}).map(([kind, ids]) => `<h3>Outgoing · ${kind}</h3><div>${linkList(repo, ids)}</div>`).join('');
  const incomingSections = Object.entries(file.incoming || {}).map(([kind, ids]) => `<h3>Incoming · ${kind}</h3><div>${linkList(repo, ids)}</div>`).join('');
  box.innerHTML = `
    <div class="small muted">${file.id}</div>
    <h3>${file.path}</h3>
    <div class="pill">module: ${file.module}</div><div class="pill">ext: ${file.ext}</div><div class="pill">size: ${file.size}</div>
    <div class="columns" style="margin-top:12px">
      <div>
        <h3>Exports</h3>
        <pre>${(file.exports || []).join('\n') || 'none'}</pre>
        <h3>Tests</h3>
        <div>${linkList(repo, file.tests)}</div>
      </div>
      <div>
        <h3>Docs</h3>
        <pre>${(file.docs || []).join('\n') || 'none'}</pre>
        <h3>Roadmap</h3>
        <pre>${(file.roadmap || []).join('\n') || 'none'}</pre>
      </div>
    </div>
    ${edgeSections}
    ${incomingSections}
  `;
  document.querySelectorAll('#inspector [data-file]').forEach(el => el.onclick = () => { selectedFile = el.dataset.file; renderInspector(repo); });
}

function renderAll() {
  const repo = pickRepo();
  renderRepoSelect();
  if (!repo) return;
  renderKPIs(repo);
  renderModules(repo);
  renderRuntime(repo);
  renderFiles(repo);
  renderInspector(repo);
}

async function loadData() {
  SNAP = await fetchJSON('/api/scan');
  renderAll();
}

document.getElementById('repoSelect').addEventListener('change', (e) => { repoName = e.target.value; selectedFile = null; renderAll(); });
document.getElementById('fileSearch').addEventListener('input', () => renderAll());
document.getElementById('refreshBtn').addEventListener('click', async () => { await fetchJSON('/api/rescan', {method:'POST'}); await loadData(); });
loadData();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    state: DashboardState = None  # type: ignore

    def _send_json(self, payload: dict, code: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML)
            return
        if parsed.path == "/api/scan":
            self._send_json(self.state.snapshot())
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/rescan":
            self.state.scan()
            self._send_json({"ok": True, "generated_at": self.state.last_scan_at})
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
    ap = argparse.ArgumentParser(description="Local POGLS dashboard")
    ap.add_argument("--repo", action="append", default=[], help="Repo path or NAME=PATH; may be repeated")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args(argv)

    repos: List[Tuple[str, Path]] = []
    if args.repo:
        repos.extend(parse_repo_arg(item) for item in args.repo)
    else:
        cwd = Path.cwd()
        repos.append((cwd.name, cwd))
    # auto-discover nearby POGLS4 if present and not already provided
    known = {str(path.resolve()) for _, path in repos if path.exists()}
    sibling = Path.cwd().parent / "POGLS4"
    if sibling.exists() and str(sibling.resolve()) not in known:
        repos.append((sibling.name, sibling))

    state = DashboardState(repos)
    Handler.state = state
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"POGLS Local Dashboard listening on http://{args.host}:{args.port}")
    for name, path in repos:
        print(f"  - {name}: {path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

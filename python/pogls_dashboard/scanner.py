from __future__ import annotations

import ast
import fnmatch
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .models import FileNode, ManifestLink, ModuleStatus, RepoConfig

TEXT_EXTS = {".c", ".cc", ".cpp", ".cu", ".h", ".hpp", ".hh", ".py", ".pyw", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml"}
ARCHIVE_EXTS = {".zip"}
IGNORE_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build", ".venv", "venv", ".idea", ".vscode"}
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
VERSION_RE = re.compile(r"[vV](\d+(?:[._-]\d+)?)")


def _safe_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_excluded(rel: str, globs: List[str]) -> bool:
    rel_posix = rel.replace("\\", "/")
    base = Path(rel_posix).name
    for pattern in globs:
        pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(base, pat):
            return True
    return False


def _extract_version(name: str) -> str:
    m = VERSION_RE.search(name)
    return m.group(1) if m else ""


class DashboardScanner:
    def __init__(self, repos: List[RepoConfig], module_tracking: Dict[str, List[str]], links: List[ManifestLink]):
        self.repos = repos
        self.module_tracking = module_tracking
        self.links = links
        self.files: Dict[str, FileNode] = {}
        self.modules: Dict[str, ModuleStatus] = defaultdict(lambda: ModuleStatus(""))
        self.repo_summaries: Dict[str, dict] = {}
        self.roadmaps: Dict[str, List[dict]] = defaultdict(list)
        self.runtime_checks: Dict[str, List[dict]] = defaultdict(list)
        self.archives: Dict[str, List[dict]] = defaultdict(list)
        self.duplicates: List[dict] = []
        self._abs_to_id: Dict[str, str] = {}
        self._basename_to_ids: Dict[str, List[str]] = defaultdict(list)
        self._py_module_to_ids: Dict[str, List[str]] = defaultdict(list)

    def scan(self) -> dict:
        self._index_files()
        self._parse_links()
        self._link_tests_docs_roadmap()
        self._apply_manifest_tracking()
        self._apply_manifest_links()
        self._build_runtime_hints()
        self._build_duplicates()
        self._summaries()
        return self.to_dict()

    def _module_for(self, rel: str) -> str:
        lower = rel.lower()
        for name, tokens in MODULE_PATTERNS:
            if any(token in lower for token in tokens):
                return name
        return rel.split("/", 1)[0].replace(".", "_")

    def _read_text(self, path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _add_edge(self, src_id: str, dst_id: str, kind: str) -> None:
        if src_id == dst_id or src_id not in self.files or dst_id not in self.files:
            return
        self.files[src_id].outgoing[kind].add(dst_id)
        self.files[dst_id].incoming[kind].add(src_id)
        if self.files[src_id].repo != self.files[dst_id].repo:
            for file_id in (src_id, dst_id):
                mod = self.files[file_id].module
                self.modules[mod].cross_repo_links.add(kind)

    def _index_files(self) -> None:
        for repo in self.repos:
            root = Path(repo.path)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
                    continue
                rel = _safe_rel(path, root)
                ext = path.suffix.lower()
                if ext in ARCHIVE_EXTS:
                    self.archives[repo.name].append({
                        "repo": repo.name,
                        "path": rel,
                        "size": path.stat().st_size,
                        "version": _extract_version(path.name),
                        "excluded": _is_excluded(rel, repo.exclude_globs),
                    })
                if _is_excluded(rel, repo.exclude_globs):
                    continue
                if ext and ext not in TEXT_EXTS:
                    continue
                node = FileNode(repo=repo.name, path=rel, abs_path=str(path.resolve()), ext=ext, size=path.stat().st_size, module=self._module_for(rel))
                file_id = node.file_id
                self.files[file_id] = node
                self._abs_to_id[node.abs_path] = file_id
                self._basename_to_ids[path.name].append(file_id)
                if ext in {".py", ".pyw"}:
                    mod = rel[:-3] if ext == ".py" else rel[:-4]
                    mod = mod.replace("/", ".")
                    self._py_module_to_ids[mod].append(file_id)
                    self._py_module_to_ids[Path(rel).stem].append(file_id)
                self.modules[node.module].name = node.module
                self.modules[node.module].files.add(file_id)

    def _resolve_include(self, src_file: Path, target: str) -> Optional[str]:
        direct = (src_file.parent / target).resolve()
        if str(direct) in self._abs_to_id:
            return self._abs_to_id[str(direct)]
        matches = self._basename_to_ids.get(Path(target).name, [])
        return matches[0] if matches else None

    def _resolve_python(self, module_name: str) -> List[str]:
        results = []
        for name in (module_name, module_name.split(".")[0]):
            results.extend(self._py_module_to_ids.get(name, []))
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
            except SyntaxError:
                tree = None
            if tree is not None:
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        out.append(node.name)
        return sorted(set(out))[:60]

    def _parse_links(self) -> None:
        for file_id, node in self.files.items():
            text = self._read_text(node.abs_path)
            node.exports = self._extract_exports(text, node.ext)
            if node.ext in {".c", ".cc", ".cpp", ".cu", ".h", ".hpp", ".hh"}:
                for line in text.splitlines():
                    m = INCLUDE_RE.match(line)
                    if m:
                        target = self._resolve_include(Path(node.abs_path), m.group(1))
                        if target:
                            self._add_edge(file_id, target, "include")
            elif node.ext in {".py", ".pyw"}:
                try:
                    tree = ast.parse(text)
                except SyntaxError:
                    tree = None
                if tree is not None:
                    for item in ast.walk(tree):
                        if isinstance(item, ast.Import):
                            for alias in item.names:
                                for target in self._resolve_python(alias.name):
                                    self._add_edge(file_id, target, "import")
                        elif isinstance(item, ast.ImportFrom) and item.module:
                            for target in self._resolve_python(item.module):
                                self._add_edge(file_id, target, "import")

    def _link_tests_docs_roadmap(self) -> None:
        for file_id, node in self.files.items():
            p = Path(node.path)
            if p.parts and p.parts[0] == "test":
                stem = p.stem.replace("test_", "")
                for other_id, other in self.files.items():
                    if other_id == file_id:
                        continue
                    other_stem = Path(other.path).stem
                    if stem == other_stem or stem in other_stem or other_stem in stem:
                        self._add_edge(file_id, other_id, "tests")
                        self.files[other_id].tests.add(file_id)
                        self.modules[self.files[other_id].module].tests.add(file_id)
            if node.ext == ".md":
                text = self._read_text(node.abs_path)
                for match in BACKTICK_FILE_RE.finditer(text):
                    name = Path(match.group(1)).name
                    for target_id in self._basename_to_ids.get(name, []):
                        self._add_edge(file_id, target_id, "doc")
                        self.files[target_id].docs.add(file_id)
                        self.modules[self.files[target_id].module].docs.add(file_id)

        for repo in self.repos:
            roadmap_path = Path(repo.path) / "POGLS38_ROADMAP.md"
            if not roadmap_path.exists():
                continue
            current_section = "root"
            text = roadmap_path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.startswith("## ") or line.startswith("### "):
                    current_section = line.lstrip("# ").strip()
                m = CHECKBOX_RE.match(line)
                if not m:
                    continue
                done = m.group("done").lower() == "x"
                label = m.group("label")
                refs = []
                for hit in BACKTICK_FILE_RE.finditer(label):
                    refs.extend(self._basename_to_ids.get(Path(hit.group(1)).name, []))
                self.roadmaps[repo.name].append({"section": current_section, "done": done, "label": label, "refs": sorted(set(refs))})
                module = self._module_for(label.replace("`", "").replace(" ", "_"))
                self.modules[module].name = module
                self.modules[module].roadmap_total += 1
                self.modules[module].roadmap_done += int(done)
                for ref in refs:
                    self.files[ref].roadmap.add(f"{current_section}: {label}")
                    self.modules[self.files[ref].module].docs.add(f"{repo.name}:POGLS38_ROADMAP.md")

    def _apply_manifest_tracking(self) -> None:
        for module, paths in self.module_tracking.items():
            self.modules[module].name = module
            for rel in paths:
                for repo in self.repos:
                    file_id = f"{repo.name}:{rel}"
                    if file_id in self.files:
                        self.modules[module].tracked_paths.add(file_id)
                        self.modules[module].files.add(file_id)

    def _apply_manifest_links(self) -> None:
        for link in self.links:
            if link.source in self.files and link.target in self.files:
                self._add_edge(link.source, link.target, link.kind)
                if link.label:
                    self.files[link.source].roadmap.add(f"link: {link.label}")
                    self.files[link.target].roadmap.add(f"link: {link.label}")

    def _build_runtime_hints(self) -> None:
        for node in self.files.values():
            if not node.path.endswith(("pogls_memory_fabric.py", "pogls_gui.pyw")):
                continue
            text = self._read_text(node.abs_path)
            hints = [ep for ep in PUBLIC_ENDPOINT_HINTS if ep in text]
            if hints:
                self.runtime_checks[node.repo].append({"file": node.path, "kind": "endpoints", "items": hints})
                self.modules[node.module].runtime_endpoints.update(hints)

    def _build_duplicates(self) -> None:
        by_basename: Dict[str, List[str]] = defaultdict(list)
        for file_id, node in self.files.items():
            by_basename[Path(node.path).name].append(file_id)
        for name, ids in by_basename.items():
            if len(ids) > 1:
                self.duplicates.append({"basename": name, "count": len(ids), "files": sorted(ids)})
        self.duplicates.sort(key=lambda item: (-item["count"], item["basename"]))

    def _summaries(self) -> None:
        for repo in self.repos:
            if not Path(repo.path).exists():
                continue
            repo_files = [f for f in self.files.values() if f.repo == repo.name]
            edge_counts = Counter()
            for f in repo_files:
                for kind, dsts in f.outgoing.items():
                    edge_counts[kind] += len(dsts)
            self.repo_summaries[repo.name] = {
                "repo": repo.name,
                "role": repo.role,
                "root": repo.path,
                "file_count": len(repo_files),
                "module_count": len({f.module for f in repo_files}),
                "roadmap_total": len(self.roadmaps.get(repo.name, [])),
                "roadmap_done": sum(item["done"] for item in self.roadmaps.get(repo.name, [])),
                "edge_counts": dict(edge_counts),
                "runtime_checks": len(self.runtime_checks.get(repo.name, [])),
                "archive_count": len(self.archives.get(repo.name, [])),
                "excluded_globs": repo.exclude_globs,
            }

    def to_dict(self) -> dict:
        return {
            "files": {
                file_id: {
                    "id": file_id,
                    "repo": node.repo,
                    "path": node.path,
                    "ext": node.ext,
                    "size": node.size,
                    "module": node.module,
                    "outgoing": {k: sorted(v) for k, v in node.outgoing.items()},
                    "incoming": {k: sorted(v) for k, v in node.incoming.items()},
                    "tests": sorted(node.tests),
                    "docs": sorted(node.docs),
                    "roadmap": sorted(node.roadmap),
                    "exports": node.exports,
                }
                for file_id, node in sorted(self.files.items())
            },
            "modules": {name: status.to_dict() for name, status in sorted(self.modules.items())},
            "repos": self.repo_summaries,
            "roadmaps": self.roadmaps,
            "runtime_checks": self.runtime_checks,
            "archives": self.archives,
            "duplicates": self.duplicates,
        }

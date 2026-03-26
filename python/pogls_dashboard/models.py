from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class RepoConfig:
    name: str
    path: str
    role: str = "project"
    track: bool = True
    exclude_globs: List[str] = field(default_factory=list)


@dataclass
class ManifestLink:
    source: str
    target: str
    kind: str = "manifest"
    label: str = ""


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
    tests: Set[str] = field(default_factory=set)
    docs: Set[str] = field(default_factory=set)
    roadmap: Set[str] = field(default_factory=set)
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
    cross_repo_links: Set[str] = field(default_factory=set)
    tracked_paths: Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        score_parts = [
            25 if self.files else 0,
            min(25, len(self.tests) * 5),
            min(15, len(self.docs) * 5),
            min(15, len(self.runtime_endpoints) * 5),
            min(10, len(self.cross_repo_links) * 3),
            int(10 * (self.roadmap_done / self.roadmap_total)) if self.roadmap_total else 0,
        ]
        score = min(100, sum(score_parts))
        if score >= 75:
            state = "strong"
        elif score >= 45:
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
            "cross_repo_links": sorted(self.cross_repo_links),
            "tracked_paths": sorted(self.tracked_paths),
            "score": score,
            "state": state,
        }

from __future__ import annotations

import json
from datetime import datetime, timezone


def export_json(snapshot: dict) -> bytes:
    return json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")


def export_markdown(snapshot: dict) -> bytes:
    lines = ["# POGLS Dashboard Export", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    overview = snapshot.get("overview", {})
    lines += [
        "## Overview",
        f"- Repos: {overview.get('repo_count', 0)}",
        f"- Files: {overview.get('file_count', 0)}",
        f"- Modules: {overview.get('module_count', 0)}",
        f"- Roadmap: {overview.get('roadmap_done', 0)}/{overview.get('roadmap_total', 0)}",
        "",
        "## Repos",
    ]
    for repo_name, repo in snapshot.get("repos", {}).items():
        summary = repo.get("summary", {})
        lines.append(f"- **{repo_name}** ({summary.get('role', 'project')}): {summary.get('roadmap_done', 0)}/{summary.get('roadmap_total', 0)} roadmap, {summary.get('file_count', 0)} files")
    lines.append("")
    lines.append("## Modules")
    for repo_name, repo in snapshot.get("repos", {}).items():
        lines.append(f"### {repo_name}")
        modules = repo.get("modules", {})
        for mod_name, mod in sorted(modules.items(), key=lambda item: (-item[1].get('score', 0), item[0]))[:12]:
            lines.append(f"- **{mod_name}** — score {mod.get('score', 0)}, tests {len(mod.get('tests', []))}, tracked {len(mod.get('tracked_paths', []))}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")

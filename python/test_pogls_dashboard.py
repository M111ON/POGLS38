import tempfile
import unittest
from pathlib import Path

from pogls_dashboard.manifest import load_manifest, resolve_manifest
from pogls_dashboard.models import ManifestLink, RepoConfig
from pogls_dashboard.scanner import DashboardScanner
from pogls_dashboard.system_info import collect_system_info


class DashboardManifestTests(unittest.TestCase):
    def test_manifest_defaults_and_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "dash.yaml"
            manifest_path.write_text(
                """
version: 1
repos:
  - name: A
    path: ./repo_a
    role: live
    exclude_globs:
      - '*.zip'
modules:
  temporal:
    tracked_paths:
      - x.h
links:
  - source: A:x.h
    target: A:y.h
    kind: manifest
exports:
  formats:
    - json
""",
                encoding="utf-8",
            )
            data = load_manifest(manifest_path)
            resolved = resolve_manifest(manifest_path.parent, data, [])
            self.assertEqual(resolved["repos"][0].name, "A")
            self.assertEqual(resolved["repos"][0].exclude_globs, ["*.zip"])
            self.assertEqual(resolved["module_tracking"]["temporal"], ["x.h"])
            self.assertEqual(resolved["links"][0].source, "A:x.h")
            self.assertEqual(resolved["export_formats"], ["json"])

    def test_cross_repo_manifest_link_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo_a = root / "repo_a"
            repo_b = root / "repo_b"
            repo_a.mkdir(); repo_b.mkdir()
            (repo_a / "a.h").write_text('#include "b.h"\n', encoding='utf-8')
            (repo_b / "b.h").write_text('typedef struct B { int x; } B;\n', encoding='utf-8')
            scanner = DashboardScanner(
                repos=[RepoConfig("A", str(repo_a), "live"), RepoConfig("B", str(repo_b), "durable")],
                module_tracking={"federation": ["a.h"]},
                links=[ManifestLink("A:a.h", "B:b.h", "cross_repo", "bridge")],
            )
            snap = scanner.scan()
            self.assertIn("A:a.h", snap["files"])
            self.assertIn("B:b.h", snap["files"])
            self.assertIn("cross_repo", snap["files"]["A:a.h"]["outgoing"])
            self.assertIn("B:b.h", snap["files"]["A:a.h"]["outgoing"]["cross_repo"])


    def test_system_info_shape(self):
        info = collect_system_info()
        for key in ["hostname", "os", "machine", "cpu", "cpu_cores", "memory", "python", "gpu"]:
            self.assertIn(key, info)

    def test_archive_inventory_and_exclude_glob(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo_a"
            repo.mkdir()
            (repo / "keep.h").write_text('int x;\n', encoding='utf-8')
            (repo / "pogls2_v377.zip").write_text('fakezip', encoding='utf-8')
            scanner = DashboardScanner(
                repos=[RepoConfig("A", str(repo), "live", exclude_globs=["*.zip"])],
                module_tracking={},
                links=[],
            )
            snap = scanner.scan()
            self.assertIn("A:keep.h", snap["files"])
            self.assertNotIn("A:pogls2_v377.zip", snap["files"])
            self.assertEqual(snap["archives"]["A"][0]["version"], "377")
            self.assertTrue(snap["archives"]["A"][0]["excluded"])


if __name__ == '__main__':
    unittest.main()

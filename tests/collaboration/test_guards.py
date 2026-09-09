import copy
import importlib.util
from pathlib import Path
import unittest
import subprocess
import tempfile


def load(name):
    path = Path(__file__).resolve().parents[2] / "scripts/collaboration" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scope = load("verify_patch_scope")
snapshot = load("check_repository")
watcher = load("watch_cloud_task")


class ScopeTests(unittest.TestCase):
    def test_reporting_and_notes_allowed(self):
        for path in ("scripts/reporting/summary.py", "tests/reporting/test_summary.py", "docs/collaboration/notes/issue-1.md"):
            scope.validate_entry(path, "100644", "A", 100)

    def test_privileged_and_traversal_paths_rejected(self):
        for path in (".github/workflows/ci.yml", "AGENTS.md", "results/summary.json", "core/agents/attacker.py", "scripts/reporting/../../run.py", "/tmp/test.py", "scripts/reporting/nested/test.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                scope.validate_entry(path, "100644", "M", 100)

    def test_symlinks_deletion_and_executables_rejected(self):
        for mode, status in (("120000", "A"), ("100755", "A"), ("160000", "A"), ("100644", "D")):
            with self.subTest(mode=mode, status=status), self.assertRaises(ValueError):
                scope.validate_entry("scripts/reporting/report.py", mode, status, 100)

    def test_oversized_file_rejected(self):
        with self.assertRaises(ValueError):
            scope.validate_entry("scripts/reporting/report.py", "100644", "A", 100001)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = {"schema_version": 1, "local": {"head_sha": "a" * 40}, "public_base": {"head_sha": "b" * 40}, "files": [
            {"path": "docs/a.md", "local_sha256": "c" * 64, "public_sha256": None, "comparison": "local_only"}]}

    def test_valid_local_only_record(self):
        snapshot.validate_snapshot(self.data)

    def test_false_identity_rejected(self):
        self.data["files"][0]["comparison"] = "identical"
        with self.assertRaises(ValueError):
            snapshot.validate_snapshot(self.data)


    def test_short_commit_rejected(self):
        self.data["local"]["head_sha"] = "d708b3e"
        with self.assertRaises(ValueError):
            snapshot.validate_snapshot(self.data)

    def test_duplicate_path_rejected(self):
        self.data["files"].append(copy.deepcopy(self.data["files"][0]))
        with self.assertRaises(ValueError):
            snapshot.validate_snapshot(self.data)

    def test_malformed_hash_rejected(self):
        self.data["files"][0]["local_sha256"] = "reported in chat"
        with self.assertRaises(ValueError):
            snapshot.validate_snapshot(self.data)


class PatchIntegrationTests(unittest.TestCase):
    def test_staged_patch_scope_enforced_in_real_git_index(self):
        verifier = Path(scope.__file__)
        for filename, accepted in (("scripts/reporting/report.py", True), (".github/workflows/injected.yml", False)):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(["git", "init", "-q", directory], check=True)
                subprocess.run(["git", "-C", directory, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "base"], check=True)
                target = root / filename
                target.parent.mkdir(parents=True)
                target.write_text("# fixture\n")
                subprocess.run(["git", "-C", directory, "add", "--", filename], check=True)
                checked = subprocess.run(["python3", str(verifier)], cwd=root, capture_output=True)
                self.assertEqual(checked.returncode == 0, accepted, checked.stderr.decode())

    def test_cloud_snapshot_reports_paths_without_applying(self):
        patch = b"diff --git a/docs/a.md b/docs/a.md\n--- a/docs/a.md\n+++ b/docs/a.md\n"
        result = watcher.summarize_diff(patch)
        self.assertEqual(result["paths"], ["docs/a.md"])
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(len(result["sha256"]), 64)



if __name__ == "__main__":
    unittest.main()

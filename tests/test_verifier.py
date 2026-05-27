from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import hashlib
from pathlib import Path

from verifier.core import _diff_hunks, _diff_text, verify_claim


class ReviewCoverageVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="review-verifier-"))
        self.repo = self.temp_dir / "repo"
        self.repo.mkdir()
        self._git("init")
        self._git("config", "user.email", "tests@example.com")
        self._git("config", "user.name", "Verifier Tests")
        self._write("README.md", "# fixture\n")
        self._git("add", ".")
        self._git("commit", "-m", "base")
        self.base_ref = self._git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._rmtree(self.temp_dir)

    def test_accepts_review_covering_all_changed_files(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._write("docs.md", "docs\n")
        self._commit("head")

        result = verify_claim(self._claim(["app.py", "docs.md"]))

        self.assertEqual(result.status, "ACCEPT")
        self.assertEqual(result.missing_files, [])
        self.assertEqual(result.missing_hunks, [])
        self.assertTrue(result.diff_sha256_matches)
        self.assertEqual(result.invalid_findings, [])

    def test_rejects_missing_changed_file(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._write("config.yml", "mode: test\n")
        self._commit("head")

        result = verify_claim(self._claim(["app.py"]))

        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.missing_files, ["config.yml"])
        self.assertTrue(result.missing_hunks)
        self.assertIn("review did not cover every changed file", result.reasons)

    def test_rejects_finding_on_unchanged_file(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._commit("head")
        claim = self._claim(["app.py"])
        claim["findings"].append({"file": "README.md", "summary": "Unchanged file note"})

        result = verify_claim(claim)

        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.invalid_findings[0]["file"], "README.md")

    def test_rejects_unexpected_reviewed_file(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._commit("head")
        claim = self._claim(["app.py"])
        claim["reviewed_files"].append("README.md")

        result = verify_claim(claim)

        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.unexpected_files, ["README.md"])
        self.assertIn("reviewed_files contains files outside the diff", result.reasons)

    def test_rejects_tampered_diff_hash(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._commit("head")
        claim = self._claim(["app.py"])
        claim["diff_sha256"] = "0" * 64

        result = verify_claim(claim)

        self.assertEqual(result.status, "REJECT")
        self.assertFalse(result.diff_sha256_matches)
        self.assertIn("claimed diff_sha256 does not match the current git diff", result.reasons)

    def test_rejects_review_without_findings(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._commit("head")
        claim = self._claim(["app.py"])
        claim["findings"] = []

        result = verify_claim(claim)

        self.assertEqual(result.status, "REJECT")
        self.assertIn("review contains no findings", result.reasons)

    def test_result_is_json_serializable(self) -> None:
        self._write("app.py", "print('ok')\n")
        self._commit("head")
        result = verify_claim(self._claim(["app.py"]))

        encoded = json.dumps(result.to_dict(), sort_keys=True)

        self.assertIn('"status": "ACCEPT"', encoded)

    def _claim(self, reviewed_files: list[str]) -> dict[str, object]:
        head_ref = self._git("rev-parse", "HEAD")
        diff_text = _diff_text(self.repo, self.base_ref, head_ref)
        hunk_ids = _diff_hunks(diff_text)
        reviewed_hunks = [hunk for hunk in hunk_ids if hunk.split(":", 1)[0] in reviewed_files]
        return {
            "repo_path": str(self.repo),
            "base_ref": self.base_ref,
            "head_ref": head_ref,
            "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
            "reviewed_files": reviewed_files,
            "reviewed_hunks": reviewed_hunks,
            "findings": [
                {"file": path, "summary": f"Reviewed {path}", "severity": "low"}
                for path in reviewed_files
            ],
        }

    def _commit(self, message: str) -> None:
        self._git("add", ".")
        self._git("commit", "-m", message)

    def _write(self, relative: str, content: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def _rmtree(self, path: Path) -> None:
        def make_writable(function, target, exc_info):  # type: ignore[no-untyped-def]
            os.chmod(target, 0o700)
            function(target)

        shutil.rmtree(path, onerror=make_writable)


if __name__ == "__main__":
    unittest.main()

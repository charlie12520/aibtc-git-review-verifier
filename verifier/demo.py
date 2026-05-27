from __future__ import annotations

import json
import os
import shutil
import subprocess
import hashlib
from pathlib import Path

from .core import _diff_hunks, _diff_text, verify_claim


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "samples" / "generated"


def main() -> int:
    if GENERATED.exists():
        _rmtree(GENERATED)
    GENERATED.mkdir(parents=True)

    samples = [
        _build_sample("accept_basic", {"app.py": "print('hello')\n"}, ["app.py"]),
        _build_sample(
            "accept_multifile",
            {"app.py": "print('hello')\n", "README.md": "# Demo\n"},
            ["app.py", "README.md"],
        ),
        _build_sample(
            "accept_docs_and_code",
            {"src/parser.py": "def parse(x):\n    return x.strip()\n", "docs/parser.md": "Parser docs\n"},
            ["src/parser.py", "docs/parser.md"],
        ),
        _build_sample(
            "reject_missing_file",
            {"service.py": "def ok():\n    return True\n", "config.example": "MODE=demo\n"},
            ["service.py"],
        ),
    ]

    exit_code = 0
    for name, claim_path, expected in samples:
        result = verify_claim(json.loads(claim_path.read_text(encoding="utf-8")))
        print(f"{name}: {result.status}")
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        if result.status != expected:
            exit_code = 1

    return exit_code


def _build_sample(name: str, changes: dict[str, str], reviewed_files: list[str]) -> tuple[str, Path, str]:
    repo = GENERATED / name / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "demo@example.com")
    _git(repo, "config", "user.name", "Verifier Demo")

    _write(repo / "README.md", "# Sample Repo\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_ref = _git(repo, "rev-parse", "HEAD")

    for relative, content in changes.items():
        _write(repo / relative, content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"{name} change")
    head_ref = _git(repo, "rev-parse", "HEAD")
    diff_text = _diff_text(repo, base_ref, head_ref)
    hunk_ids = _diff_hunks(diff_text)

    claim = {
        "repo_path": str(repo),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "reviewed_files": reviewed_files,
        "reviewed_hunks": [hunk for hunk in hunk_ids if hunk.split(":", 1)[0] in reviewed_files],
        "findings": [
            {
                "file": path,
                "severity": "low",
                "summary": f"Reviewed {path} for the changed-surface demo.",
            }
            for path in reviewed_files
        ],
    }

    claim_path = GENERATED / f"{name}.json"
    claim_path.write_text(json.dumps(claim, indent=2, sort_keys=True), encoding="utf-8")
    expected = "REJECT" if name.startswith("reject") else "ACCEPT"
    return name, claim_path, expected


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _rmtree(path: Path) -> None:
    def make_writable(function, target, exc_info):  # type: ignore[no-untyped-def]
        os.chmod(target, 0o700)
        function(target)

    shutil.rmtree(path, onerror=make_writable)


if __name__ == "__main__":
    raise SystemExit(main())

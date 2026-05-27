from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    status: str
    changed_files: list[str]
    reviewed_files: list[str]
    missing_files: list[str]
    unexpected_files: list[str]
    invalid_findings: list[dict[str, str]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "changed_files": self.changed_files,
            "reviewed_files": self.reviewed_files,
            "missing_files": self.missing_files,
            "unexpected_files": self.unexpected_files,
            "invalid_findings": self.invalid_findings,
            "reasons": self.reasons,
        }


def verify_claim(claim: dict[str, Any]) -> VerificationResult:
    repo_path = Path(_require_str(claim, "repo_path")).expanduser().resolve()
    base_ref = _require_str(claim, "base_ref")
    head_ref = _require_str(claim, "head_ref")
    reviewed_files = sorted(set(_require_str_list(claim, "reviewed_files")))
    findings = claim.get("findings", [])

    if not isinstance(findings, list):
        raise ValueError("findings must be a list")

    changed_files = _changed_files(repo_path, base_ref, head_ref)
    changed_set = set(changed_files)
    reviewed_set = set(reviewed_files)

    missing_files = sorted(changed_set - reviewed_set)
    unexpected_files = sorted(reviewed_set - changed_set)
    invalid_findings = _invalid_findings(findings, changed_set)

    reasons: list[str] = []
    if missing_files:
        reasons.append("review did not cover every changed file")
    if invalid_findings:
        reasons.append("one or more findings reference files outside the diff")
    if not findings:
        reasons.append("review contains no findings")

    status = "REJECT" if reasons else "ACCEPT"
    if status == "ACCEPT":
        reasons.append("reviewed_files covers the full git diff and every finding references a changed file")

    return VerificationResult(
        status=status,
        changed_files=changed_files,
        reviewed_files=reviewed_files,
        missing_files=missing_files,
        unexpected_files=unexpected_files,
        invalid_findings=invalid_findings,
        reasons=reasons,
    )


def load_claim(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _changed_files(repo_path: Path, base_ref: str, head_ref: str) -> list[str]:
    if not (repo_path / ".git").exists():
        raise ValueError(f"repo_path is not a git repository: {repo_path}")

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", f"{base_ref}..{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip())


def _invalid_findings(findings: list[Any], changed_files: set[str]) -> list[dict[str, str]]:
    invalid: list[dict[str, str]] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            invalid.append({"index": str(index), "reason": "finding is not an object"})
            continue

        file_path = finding.get("file")
        summary = finding.get("summary")
        if not isinstance(file_path, str) or not file_path:
            invalid.append({"index": str(index), "reason": "missing file"})
            continue
        if file_path not in changed_files:
            invalid.append({"index": str(index), "file": file_path, "reason": "file not changed"})
            continue
        if not isinstance(summary, str) or not summary.strip():
            invalid.append({"index": str(index), "file": file_path, "reason": "missing summary"})
    return invalid


def _require_str(claim: dict[str, Any], key: str) -> str:
    value = claim.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_str_list(claim: dict[str, Any], key: str) -> list[str]:
    value = claim.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain only non-empty strings")
        result.append(item.replace("\\", "/"))
    return result

from __future__ import annotations

import json
import re
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    status: str
    changed_files: list[str]
    reviewed_files: list[str]
    diff_sha256: str
    diff_sha256_matches: bool | None
    hunk_ids: list[str]
    reviewed_hunks: list[str]
    missing_files: list[str]
    unexpected_files: list[str]
    missing_hunks: list[str]
    unexpected_hunks: list[str]
    invalid_findings: list[dict[str, str]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "changed_files": self.changed_files,
            "reviewed_files": self.reviewed_files,
            "diff_sha256": self.diff_sha256,
            "diff_sha256_matches": self.diff_sha256_matches,
            "hunk_ids": self.hunk_ids,
            "reviewed_hunks": self.reviewed_hunks,
            "missing_files": self.missing_files,
            "unexpected_files": self.unexpected_files,
            "missing_hunks": self.missing_hunks,
            "unexpected_hunks": self.unexpected_hunks,
            "invalid_findings": self.invalid_findings,
            "reasons": self.reasons,
        }


def verify_claim(claim: dict[str, Any]) -> VerificationResult:
    repo_path = Path(_require_str(claim, "repo_path")).expanduser().resolve()
    base_ref = _require_str(claim, "base_ref")
    head_ref = _require_str(claim, "head_ref")
    reviewed_files = sorted(set(_require_str_list(claim, "reviewed_files")))
    reviewed_hunks = sorted(set(_optional_str_list(claim, "reviewed_hunks")))
    findings = claim.get("findings", [])

    if not isinstance(findings, list):
        raise ValueError("findings must be a list")

    diff_text = _diff_text(repo_path, base_ref, head_ref)
    # Bind the claim to the exact diff text so a stale review cannot pass silently.
    actual_diff_sha256 = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    claimed_diff_sha256 = claim.get("diff_sha256")
    diff_sha256_matches: bool | None = None
    if claimed_diff_sha256 is not None:
        if not isinstance(claimed_diff_sha256, str) or not claimed_diff_sha256:
            raise ValueError("diff_sha256 must be a non-empty string when supplied")
        diff_sha256_matches = claimed_diff_sha256 == actual_diff_sha256

    changed_files = _changed_files(repo_path, base_ref, head_ref)
    hunk_ids = _diff_hunks(diff_text)
    changed_set = set(changed_files)
    reviewed_set = set(reviewed_files)
    hunk_set = set(hunk_ids)
    reviewed_hunk_set = set(reviewed_hunks)

    missing_files = sorted(changed_set - reviewed_set)
    unexpected_files = sorted(reviewed_set - changed_set)
    missing_hunks = sorted(hunk_set - reviewed_hunk_set)
    unexpected_hunks = sorted(reviewed_hunk_set - hunk_set)
    invalid_findings = _invalid_findings(findings, changed_set)

    reasons: list[str] = []
    if diff_sha256_matches is False:
        reasons.append("claimed diff_sha256 does not match the current git diff")
    if missing_files:
        reasons.append("review did not cover every changed file")
    if unexpected_files:
        reasons.append("reviewed_files contains files outside the diff")
    if missing_hunks:
        reasons.append("review did not cover every changed hunk")
    if unexpected_hunks:
        reasons.append("reviewed_hunks contains hunks outside the diff")
    if invalid_findings:
        reasons.append("one or more findings reference files outside the diff")
    if not findings:
        reasons.append("review contains no findings")

    status = "REJECT" if reasons else "ACCEPT"
    if status == "ACCEPT":
        reasons.append("reviewed_files and reviewed_hunks cover the full git diff")

    return VerificationResult(
        status=status,
        changed_files=changed_files,
        reviewed_files=reviewed_files,
        diff_sha256=actual_diff_sha256,
        diff_sha256_matches=diff_sha256_matches,
        hunk_ids=hunk_ids,
        reviewed_hunks=reviewed_hunks,
        missing_files=missing_files,
        unexpected_files=unexpected_files,
        missing_hunks=missing_hunks,
        unexpected_hunks=unexpected_hunks,
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


def _diff_text(repo_path: Path, base_ref: str, head_ref: str) -> str:
    if not (repo_path / ".git").exists():
        raise ValueError(f"repo_path is not a git repository: {repo_path}")

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--no-ext-diff", "--unified=0", f"{base_ref}..{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.replace("\r\n", "\n")


def _diff_hunks(diff_text: str) -> list[str]:
    current_file: str | None = None
    hunk_ids: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            current_file = parts[1].replace("\\", "/") if len(parts) == 2 else None
            continue

        match = re.match(r"^@@ (?P<range>[^@]+) @@", line)
        if match and current_file:
            # Keep hunk IDs compact but stable enough for JSON claims and test fixtures.
            hunk_ids.append(f"{current_file}:{match.group('range').strip()}")
    return sorted(hunk_ids)


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


def _optional_str_list(claim: dict[str, Any], key: str) -> list[str]:
    value = claim.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list when supplied")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain only non-empty strings")
        result.append(item.replace("\\", "/"))
    return result

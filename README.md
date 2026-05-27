# Git Review Coverage Verifier

This is a narrow trustless verifier for one agent task class:

> Claim: "This code review covered every file changed between git commit A and commit B."

The verifier deterministically re-runs `git diff --name-only A..B`, compares the changed files with the files the review claims to cover, and returns `ACCEPT` or `REJECT` with structured reasons.

## Why This Fits Agent Work

Agent marketplaces often pay for PR reviews, bug triage, or patch audits. A human reviewer can still judge whether the comments are smart, but this verifier answers a cheaper prerequisite question:

> Did the review artifact even cover the full changed surface?

That catches a common failure mode: an agent leaves a plausible review while skipping changed files.

## Trust Model

Mechanism: deterministic re-execution.

Trust assumptions:

- The verifier trusts the local git repository and commit objects it is given.
- It trusts `git diff --name-only` to compute the changed-file set.
- It does not trust the review claim. The claim is checked against the commit diff.
- It does not prove semantic review quality. It proves changed-file coverage and finding references.

No private data, oracle, TEE, or model provider is required.

## Cost

Expected verification cost per task:

- Network: 0 sats if the repo is already cloned.
- Compute: one `git diff --name-only` call plus JSON parsing.
- Typical wall-clock time on the included samples: under 1 second.

This is well below 100 sats per verification.

## Claim Format

```json
{
  "repo_path": "path/to/git/repo",
  "base_ref": "BASE_COMMIT_OR_REF",
  "head_ref": "HEAD_COMMIT_OR_REF",
  "reviewed_files": ["app.py", "README.md"],
  "findings": [
    {
      "file": "app.py",
      "summary": "Input validation edge case",
      "severity": "medium"
    }
  ]
}
```

## Usage

Run the reproducible demo:

```bash
python -m verifier.demo
```

Verify one claim:

```bash
python -m verifier.cli samples/generated/accept_basic.json
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Demo Coverage

The demo creates local git repositories and verifies four samples:

- `accept_basic`: one-file change, review covers that file.
- `accept_multifile`: two-file change, review covers both files.
- `accept_docs_and_code`: code plus docs change, review covers both.
- `reject_missing_file`: two-file change, review covers only one file, so it rejects.


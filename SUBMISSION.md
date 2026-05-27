# AIBTC Trustless Verifier Submission

Bounty: `mplaqamf42051ff40a2d`

Public repo: https://github.com/charlie12520/aibtc-git-review-verifier

## Task Class

This verifier handles the narrow task class:

> "A code-review agent claims it reviewed every file and changed hunk between git commit A and commit B."

The verifier checks whether the review claim covers the complete changed-file and changed-hunk sets.

## Mechanism

Deterministic re-execution:

1. Run `git diff --no-ext-diff --unified=0 base..head`.
2. Compute the SHA-256 of that exact diff.
3. Compare the changed-file set to the review artifact's `reviewed_files`.
4. Compare the changed-hunk set to the review artifact's `reviewed_hunks`.
5. Confirm every finding references a changed file and has a summary.
6. Emit structured `ACCEPT` or `REJECT` output.

## Reproducible Live Demo

Command:

```bash
python -m verifier.demo
```

Expected results:

- `accept_basic`: `ACCEPT`
- `accept_multifile`: `ACCEPT`
- `accept_docs_and_code`: `ACCEPT`
- `reject_missing_file`: `REJECT`

## Validation Run

Local validation on Windows:

```bash
python -m unittest discover -s tests -v
python -m verifier.demo
```

Result:

- Unit tests: 7 passed.
- Demo: 3 accepted samples and 1 rejected fake/incomplete review.
- Extra integrity check: tampered `diff_sha256` rejects.

## Trust Assumptions

- Trust git's local object database and `git diff`.
- Trust the SHA-256 digest to bind the claim to the exact diff text.
- Trust the published verifier code and reproducible sample generation.
- Do not trust the review claim.
- Do not claim semantic code-review quality; this proves changed-surface coverage.

## Cost

- No network call if the repo is already cloned.
- One local `git diff --name-only` call, one local `git diff --no-ext-diff --unified=0` call, hunk extraction, and JSON parsing.
- Expected per-task cost: effectively 0 sats, well below the 100-sat limit.

## License

MIT.

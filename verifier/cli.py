from __future__ import annotations

import json
import sys

from .core import load_claim, verify_claim


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m verifier.cli CLAIM.json", file=sys.stderr)
        return 2

    result = verify_claim(load_claim(args[0]))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "ACCEPT" else 1


if __name__ == "__main__":
    raise SystemExit(main())

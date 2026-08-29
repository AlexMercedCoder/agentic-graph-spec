#!/usr/bin/env python3
"""Verify checked-in AGS conformance claims and their claimed level surfaces."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "conformance" / "result.schema.json").read_text(encoding="utf-8"))
BASE = {"all-valid-fixtures", "all-invalid-diagnostics", "rfc8785-digests"}
BY_LEVEL = {
    0: set(),
    1: {"level-1-execution"},
    2: {"level-1-execution", "level-2-decisions-and-joins"},
    3: {
        "level-1-execution",
        "level-2-decisions-and-joins",
        "level-3-loop-map-subgraph",
        "run-record-schema",
    },
}


def main() -> int:
    failures: list[str] = []
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    paths = sorted((ROOT / "conformance" / "results").glob("*.json"))
    if not paths:
        failures.append("no conformance results found")
    for path in paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        for error in validator.iter_errors(result):
            failures.append(f"{path.name}: schema: {error.message}")
        if result.get("failed"):
            failures.append(f"{path.name}: failed checks are not empty")
        revision = result.get("fixture_revision", "")
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            failures.append(f"{path.name}: fixture_revision is not a full Git commit")
        level = result.get("level")
        if level in BY_LEVEL:
            missing = (BASE | BY_LEVEL[level]) - set(result.get("passed", []))
            if missing:
                failures.append(f"{path.name}: missing Level {level} evidence: {sorted(missing)}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Verified {len(paths)} AGS conformance result(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

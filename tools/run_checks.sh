#!/usr/bin/env bash
# Repository self-check for the Agentic Graph Specification.
#
#   1. Every document in examples/ must validate with zero errors AND zero warnings.
#   2. Every fixture in conformance/invalid/ must produce the diagnostic code named in
#      its "# EXPECT: AGnnn" header comment.
#   3. The JSON and YAML forms of the canonical example must parse to identical data.
#
# Usage: tools/run_checks.sh

set -uo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
failures=0

echo "== 0. schema behavior =="
if "$PY" tools/test_schema.py | tail -2; then
  echo "   PASS"
else
  echo "   FAIL: schema does not behave as SPEC.md describes"
  failures=$((failures + 1))
fi

echo
echo "== 0b. checked-in conformance claims =="
if "$PY" tools/verify_conformance_results.py; then
  echo "   PASS"
else
  echo "   FAIL: a conformance result is malformed or incomplete for its claimed level"
  failures=$((failures + 1))
fi

echo
echo "== 0c. support-library release versions =="
if "$PY" tools/verify_release_versions.py; then
  echo "   PASS"
else
  echo "   FAIL: support-library release versions have drifted"
  failures=$((failures + 1))
fi

echo
echo "== 1. examples/ must be clean (strict) =="
if "$PY" tools/validate_agraph.py --strict examples/; then
  echo "   PASS"
else
  echo "   FAIL: examples/ did not validate cleanly"
  failures=$((failures + 1))
fi

echo
echo "== 2. conformance/invalid/ must produce their expected codes =="
for fixture in conformance/invalid/*.agraph.yaml; do
  expected=$(grep -m1 '^# EXPECT:' "$fixture" | awk '{print $3}')
  if [ -z "$expected" ]; then
    echo "   FAIL: $fixture has no '# EXPECT:' header"
    failures=$((failures + 1))
    continue
  fi
  output=$("$PY" tools/validate_agraph.py "$fixture" 2>&1)
  if echo "$output" | grep -q "$expected"; then
    echo "   PASS: $(basename "$fixture") -> $expected"
  else
    echo "   FAIL: $(basename "$fixture") did not report $expected"
    echo "$output" | sed 's/^/        /'
    failures=$((failures + 1))
  fi
done

echo
echo "== 3. canonical example: JSON and YAML must be identical =="
if "$PY" - <<'PYEOF'
import json, sys, pathlib, yaml
a = yaml.safe_load(pathlib.Path("examples/library-v1-release.agraph.yaml").read_text())
b = json.loads(pathlib.Path("examples/library-v1-release.agraph.json").read_text())
sys.exit(0 if a == b else 1)
PYEOF
then
  echo "   PASS"
else
  echo "   FAIL: the JSON and YAML forms differ"
  failures=$((failures + 1))
fi

echo
if [ "$failures" -eq 0 ]; then
  echo "All checks passed."
  exit 0
fi
echo "$failures check group(s) failed."
exit 1

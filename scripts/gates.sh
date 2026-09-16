#!/usr/bin/env bash
# The gate chain run before every commit: lint, format, types, tests, naming.
#
# WHY THIS FILE EXISTS (docs/INSTRUMENT_AUDIT.md, entry 10). The chain used to be typed by
# hand as `pytest -q | tail -n 3 && ...`. A pipeline's exit status is its LAST command's,
# so `tail` exited 0 over a failing pytest and the commit went through (C0, `904ff77`,
# amended). The same shape masks ruff and mypy just as well. Here every stage runs under
# `pipefail`, so a stage fails when its command fails, whatever its output is piped into.
#
# Every stage runs even after one fails, so one run shows every red gate, and the script
# exits non-zero if any did.
#
# `faultline check naming` scans TRACKED files only, so a file never added is never read.
# The first stage refuses untracked, unignored files instead of letting naming pass them.
#
# FAULTLINE_GATE_STAGES replaces the stage list (one command a line). It exists for the
# regression test (tests/test_gates.py), which must be able to feed the chain a failure.
set -euo pipefail

stages=(
  "test -z \"\$(git ls-files --others --exclude-standard)\" || { git ls-files --others --exclude-standard; echo 'untracked files: git add them, or naming cannot see them'; exit 1; }"
  "ruff check ."
  "ruff format --check ."
  "mypy --strict src/"
  "pytest -q"
  "faultline check naming"
)
if [[ -n "${FAULTLINE_GATE_STAGES:-}" ]]; then
  mapfile -t stages <<<"${FAULTLINE_GATE_STAGES}"
fi

failed=()
for stage in "${stages[@]}"; do
  [[ -z "${stage}" ]] && continue
  echo "== gate: ${stage}"
  # The pipe to tail is the hazard this file exists for; pipefail makes it safe.
  if ! bash -o pipefail -c "${stage}" 2>&1 | tail -n "${FAULTLINE_GATE_TAIL:-15}"; then
    failed+=("${stage}")
  fi
done

if ((${#failed[@]})); then
  printf 'GATE FAILED: %s\n' "${failed[@]}"
  exit 1
fi
echo "ALL GATES PASSED (${#stages[@]} stages)"

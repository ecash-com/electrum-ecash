#!/usr/bin/env bash
# Run upstream's test suite, minus the tests our intentional changes invalidate.
#
#   run-tests.sh                   green if nothing beyond the known list is broken
#   run-tests.sh --audit           ALSO run the known-failing tests, to see if any
#                                  now pass (list is stale). Do this after a rebase.
#   run-tests.sh --print-deselect  print the --deselect flags only, so CI can wrap
#                                  pytest in coverage and still use one source of truth
set -u
cd "$(dirname "$0")/../.."
LIST=contrib/ecx/known-test-failures.txt
PY=${PYTHON:-python3}

# Isolate the data directory. Some upstream tests build a config against the
# real user_dir() and persist settings into it -- tests/test_onion_message.py
# leaves lightning_forward_payments=true in ~/.electrum-ecash/config, which then
# logs an alarming mainnet warning on every startup. Point them at a temp dir.
ELECTRUMDIR=$(mktemp -d)
export ELECTRUMDIR
trap 'rm -rf "$ELECTRUMDIR"' EXIT

# bash 3.2 (macOS) has no mapfile
KNOWN=()
while IFS= read -r line; do KNOWN+=("$line"); done < <(grep -vE '^[[:space:]]*(#|$)' "$LIST")

if [[ "${1:-}" == "--print-deselect" ]]; then
    for t in "${KNOWN[@]}"; do printf -- '--deselect\n%s\n' "$t"; done
    exit 0
fi

if [[ "${1:-}" == "--audit" ]]; then
    echo "== auditing ${#KNOWN[@]} known-failing tests: any that PASS should be removed from"
    echo "   $LIST"
    "$PY" -m pytest "${KNOWN[@]}" -q -p no:cacheprovider --timeout=180
    exit
fi

DESELECT=()
for t in "${KNOWN[@]}"; do DESELECT+=(--deselect "$t"); done
echo "== running upstream tests, deselecting ${#KNOWN[@]} known-affected (see $LIST)"
exec "$PY" -m pytest tests/ -q -p no:cacheprovider --timeout=180 \
     --ignore=tests/qml "${DESELECT[@]}"

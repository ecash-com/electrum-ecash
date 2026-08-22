#!/usr/bin/env bash
# Show exactly what this fork changes vs the upstream release it is based on.
#
#   show-fork-diff.sh              summary: commits + per-file line counts
#   show-fork-diff.sh --full       the complete patch
#   show-fork-diff.sh --markers    every '# ECX:' marked line in the tree
set -u
cd "$(dirname "$0")/../.."
BASE=$(cat contrib/ecx/upstream-base 2>/dev/null || echo 4.8.1)

case "${1:-}" in
  --full)    exec git diff "$BASE"..HEAD ;;
  --markers) exec grep -rn '# ECX:' electrum/ ;;
esac

echo "upstream base: $BASE  ($(git log -1 --format=%ci "$BASE" 2>/dev/null | cut -d' ' -f1))"
echo
echo "== commits =="
git log --oneline --reverse "$BASE"..HEAD
echo
echo "== files touched =="
git diff --stat "$BASE"..HEAD
echo
echo "== new files (no upstream conflict surface) =="
git diff --diff-filter=A --name-only "$BASE"..HEAD | sed 's/^/  /'
echo
NEW=$(git diff --numstat "$BASE"..HEAD | awk '$3=="electrum/ecx.py"{print $1}')
TOT=$(git diff --shortstat "$BASE"..HEAD | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+')
echo "== ${TOT:-0} lines added, of which ${NEW:-0} are the self-contained electrum/ecx.py =="
echo "   so ~$(( ${TOT:-0} - ${NEW:-0} )) lines actually touch upstream files."

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
# Honest measure: lines touching files that already existed upstream. New files
# have no conflict surface, so they are not part of the maintenance burden.
git diff --diff-filter=A --name-only "$BASE"..HEAD > /tmp/.ecx_newfiles.$$
git diff --numstat "$BASE"..HEAD | awk '
  NR==FNR { isnew[$0]=1; next }
  { total+=$1; if (isnew[$3]) newl+=$1; else { existing+=$1; existdel+=$2 } }
  END {
    printf "== %d lines added total; %d of them in new files ==\n", total, newl
    printf "   %d added / %d removed actually touch pre-existing upstream files.\n", existing, existdel
  }' /tmp/.ecx_newfiles.$$ -
rm -f /tmp/.ecx_newfiles.$$

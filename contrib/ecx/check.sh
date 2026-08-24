#!/usr/bin/env bash
# Static checks for the kind of mistake the test suite does not catch.
#
# A NameError inside a function body is invisible to both `import electrum.foo`
# and to any test that never enters that branch -- exactly how a missing
# `import ecx` in gui/qt/__init__.py shipped and crashed the GUI at startup.
set -u
cd "$(dirname "$0")/../.."
PY=${PYTHON:-python3}
rc=0

echo "== undefined names (pyflakes, whole package) =="
# electrum/_vendor/ is vendored third-party code with py2 compat shims
# ('unicode'), guarded at runtime. Not ours, and not fixable here.
if out=$("$PY" -m pyflakes electrum/ 2>&1 \
         | grep -vE "^electrum/_vendor/" \
         | grep -E "undefined name|may be undefined"); then
    echo "$out"; rc=1
else
    echo "  none"
fi

echo "== every module that uses ecx. also imports it =="
missing=0
while IFS= read -r f; do
    case "$f" in */ecx.py) continue;; esac
    grep -q "ecx\." "$f" || continue
    grep -qE "^[[:space:]]*(from electrum import ecx|from \.+ import ecx|from electrum\.ecx import|import ecx)" "$f" \
        || { echo "  MISSING import: $f"; missing=1; rc=1; }
done < <(find electrum -name '*.py')
[ "$missing" = 0 ] && echo "  ok"

echo "== every '# ECX:' marked file parses =="
"$PY" - <<'PY' || rc=1
import ast, pathlib, sys
bad = 0
for p in pathlib.Path("electrum").rglob("*.py"):
    src = p.read_text(encoding="utf-8", errors="replace")
    if "# ECX:" not in src and p.name != "ecx.py":
        continue
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR {p}:{e.lineno}: {e.msg}"); bad = 1
print("  ok" if not bad else "")
sys.exit(bad)
PY

exit $rc

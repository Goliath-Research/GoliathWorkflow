#!/usr/bin/env bash
# Check for broken internal doc link patterns (post-IA revision).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

check_absent() {
  local pattern="$1"
  local msg="$2"
  if rg -l "$pattern" --glob '!.venv/**' --glob '!**/_book/**' --glob '!**/*.pdf' --glob '!**/*.html' . >/tmp/doc_link_hits.txt 2>/dev/null; then
    echo "FAIL: $msg" >&2
    head -20 /tmp/doc_link_hits.txt >&2
    fail=1
  fi
}

# Legacy paths that should not appear in active docs (exclude redirect stubs and rewrite script)
check_absent 'docs/user-manual/[0-9]' 'Legacy user-manual chapter paths (use docs/usage/)'
check_absent 'docs/domain_program_language\.md\)' 'Unqualified reference/domain-program-language.md link (use reference/)'

# Required new paths should exist
for f in \
  docs/usage/index.qmd \
  docs/reference/documentation-toolchain.md \
  docs/architecture/index.md \
  docs/implementation/index.md \
  docs/reference/domain-program-language.md \
  docs/reference/config-parameter-matrix.md
do
  if [[ ! -f "$f" ]]; then
    echo "FAIL: missing expected file $f" >&2
    fail=1
  fi
done

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo "Doc link check passed."

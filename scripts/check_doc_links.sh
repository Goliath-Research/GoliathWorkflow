#!/usr/bin/env bash
# Check for broken internal doc link patterns (post-IA revision).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

check_absent() {
  local pattern="$1"
  local msg="$2"
  if rg -l "$pattern" --glob '!.venv/**' --glob '!**/_book/**' --glob '!**/site/**' --glob '!**/site-customer/**' --glob '!**/site-pdf/**' --glob '!**/*.pdf' --glob '!**/*.html' --glob '!docs/plans/**' . >/tmp/doc_link_hits.txt 2>/dev/null; then
    echo "FAIL: $msg" >&2
    head -20 /tmp/doc_link_hits.txt >&2
    fail=1
  fi
}

# Legacy paths that should not appear in active docs (exclude redirect stubs and rewrite script)
check_absent 'docs/user-manual/[0-9]' 'Legacy user-manual chapter paths (use docs/usage/)'
check_absent 'docs/domain_program_language\.md\)' 'Unqualified reference/domain-program-language.md link (use reference/)'

# Required paths should exist (Markdown-first site)
for f in \
  docs/usage/index.md \
  docs/theory/index.md \
  docs/usage/alignment-engines.md \
  docs/CONTRIBUTING.md \
  mkdocs.yml \
  mkdocs.customer.yml \
  mkdocs.pdf.yml \
  docs-requirements.txt \
  docs/reference/documentation-toolchain.md \
  docs/architecture/index.md \
  docs/implementation/index.md \
  docs/reference/domain-program-language.md \
  docs/reference/config-parameter-matrix.md \
  docs/reference/configuration-reference.md
do
  if [[ ! -f "$f" ]]; then
    echo "FAIL: missing expected file $f" >&2
    fail=1
  fi
done

# Filesystem resolution for active published docs (exclude plans/research/…).
# Ensures migration path rewrites do not leave dangling in-repo targets.
if ! python3 - <<'PY'
from pathlib import Path
import re
from urllib.parse import unquote
import sys

ROOT = Path(".").resolve()
DOCS = ROOT / "docs"
EXCLUDE = {
    "plans", "research", "presentations", "canvas", "diagnostics",
    "_book", "node_modules", ".quarto",
}
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
missing = []
for md in DOCS.rglob("*.md"):
    if any(part in md.parts for part in EXCLUDE):
        continue
    text = md.read_text(encoding="utf-8", errors="replace")
    for match in list(LINK_RE.finditer(text)) + list(IMG_RE.finditer(text)):
        url = match.group(1).strip()
        if not url or url.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = unquote(url.split("#", 1)[0])
        if not path or path.startswith("/"):
            continue
        target = (md.parent / path).resolve()
        if not target.exists():
            missing.append(f"{md.relative_to(ROOT)} -> {url}")
if missing:
    print("FAIL: dangling relative links in active docs:", file=sys.stderr)
    for row in missing[:40]:
        print(f"  {row}", file=sys.stderr)
    if len(missing) > 40:
        print(f"  ... +{len(missing) - 40} more", file=sys.stderr)
    sys.exit(1)
print(f"Active-doc filesystem link check passed ({sum(1 for _ in DOCS.rglob('*.md'))} markdown files scanned).")
PY
then
  fail=1
fi

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo "Doc link check passed."

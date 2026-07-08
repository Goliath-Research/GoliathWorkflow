#!/usr/bin/env bash
# Fail when committed Quarto PDFs are older than source .qmd files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

check_book() {
  local book_dir="$1"
  local pdf_name="$2"
  local pdf="$book_dir/_book/$pdf_name"
  if [[ ! -f "$pdf" ]]; then
    echo "STALE: missing $pdf (run: quarto render $book_dir --to pdf)" >&2
    fail=1
    return
  fi
  while IFS= read -r -d '' qmd; do
    if [[ "$qmd" -nt "$pdf" ]]; then
      echo "STALE: $pdf older than $qmd" >&2
      fail=1
      break
    fi
  done < <(find "$book_dir" -maxdepth 2 -name '*.qmd' -print0)
}

if [[ "${1:-}" != "--check" ]]; then
  echo "Usage: $0 --check" >&2
  exit 2
fi

check_book docs/theory "MethylPipeline-Theory.pdf"
check_book docs/usage "MethylPipeline-Usage-Manual.pdf"

if [[ $fail -ne 0 ]]; then
  exit 1
fi
echo "Book PDF freshness check passed."

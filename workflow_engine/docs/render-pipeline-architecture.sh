#!/usr/bin/env bash
# Local preview (HTML + Mermaid) and optional PDF export for pipeline_architecture.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python workflow_engine/docs/build_pipeline_architecture_qmd.py
case "${1:-preview}" in
  preview)
    exec quarto preview workflow_engine/docs/pipeline_architecture.qmd
    ;;
  pdf)
    quarto render workflow_engine/docs/pipeline_architecture.qmd --to pdf
    echo "Wrote workflow_engine/docs/pipeline_architecture.pdf"
    ;;
  html)
    echo "Note: open via 'quarto preview', not the static .html file (Mermaid needs HTTP + JS)."
    quarto render workflow_engine/docs/pipeline_architecture.qmd --to html
    ;;
  *)
    echo "Usage: $0 [preview|pdf|html]" >&2
    exit 1
    ;;
esac

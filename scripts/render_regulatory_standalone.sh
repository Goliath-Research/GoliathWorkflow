#!/usr/bin/env bash
# Render the regulatory strategy article to standalone HTML (Mermaid embedded).
set -euo pipefail
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$ROOT_DIR"
node scripts/render_markdown_standalone.mjs --regulatory
echo "Open: docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.html"

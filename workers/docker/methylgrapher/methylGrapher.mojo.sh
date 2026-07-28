#!/usr/bin/env bash
# Container entrypoint for the :1.70-mojo image — runs the patched engine CLI.
set -euo pipefail
export PYTHONPATH="/opt/methylgrapher-mojo${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m engine.cli "$@"

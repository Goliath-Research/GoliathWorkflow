#!/usr/bin/env bash
# Container entrypoint for the :1.70-mojo image.
#
# Prefer the native Mojo CLI (MethylCall hot path) when the staged Mojo
# runtime is present; otherwise fall back to the patched Python engine
# (same argv surface). Set METHYLGRAPHER_MCALL_ENGINE=python to force the
# Python MethylCall path even when Mojo is available.
set -euo pipefail

ROOT="/opt/methylgrapher-mojo"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

MOJO_BIN="${ROOT}/mojo-env/bin/mojo"
if [[ -x "${MOJO_BIN}" ]]; then
  export MODULAR_HOME="${ROOT}/mojo-env/share/max"
  export LD_LIBRARY_PATH="${ROOT}/mojo-env/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export PATH="${ROOT}/mojo-env/bin:${PATH}"
  cd "${ROOT}"
  exec "${MOJO_BIN}" src/main.mojo "$@"
fi

exec python3 -m engine.cli "$@"

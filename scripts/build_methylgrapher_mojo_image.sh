#!/usr/bin/env bash
# Build epimethyl/methylgrapher:1.70-mojo from methylGrapher-mojo engine + vg.
#
# Stages engine/ from METHYLGRAPHER_MOJO_ROOT (default: sibling ../methylGrapher-mojo
# or /home/ubuntu/methylGrapher-mojo) into workers/docker/methylgrapher/engine/.
# Reuses vg.arm64 / vg_libs from a prior scripts/build_methylgrapher_image.sh run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/workers/docker/methylgrapher"

IMAGE_TAG="${METHYLGRAPHER_MOJO_IMAGE_TAG:-1.70-mojo}"
IMAGE="${METHYL_METHYLGRAPHER_MOJO_IMAGE:-epimethyl/methylgrapher:${IMAGE_TAG}}"
MOJO_ROOT="${METHYLGRAPHER_MOJO_ROOT:-}"
if [[ -z "${MOJO_ROOT}" ]]; then
  if [[ -d "${REPO_ROOT}/../methylGrapher-mojo/engine" ]]; then
    MOJO_ROOT="$(cd "${REPO_ROOT}/../methylGrapher-mojo" && pwd)"
  elif [[ -d /home/ubuntu/methylGrapher-mojo/engine ]]; then
    MOJO_ROOT=/home/ubuntu/methylGrapher-mojo
  else
    echo "ERROR: set METHYLGRAPHER_MOJO_ROOT to the methylGrapher-mojo checkout" >&2
    exit 1
  fi
fi

log() { printf '[methylgrapher-mojo-image] %s\n' "$*"; }

[[ -d "${MOJO_ROOT}/engine" ]] || { echo "missing ${MOJO_ROOT}/engine" >&2; exit 1; }
[[ -f "${DOCKER_DIR}/vg.arm64" || -f "${DOCKER_DIR}/vg" ]] || {
  echo "ERROR: vg binary missing under ${DOCKER_DIR}; run build_methylgrapher_image.sh first" >&2
  exit 1
}

VG_PREBUILT=vg.arm64
if [[ ! -f "${DOCKER_DIR}/vg.arm64" && -f "${DOCKER_DIR}/vg" ]]; then
  VG_PREBUILT=vg
fi

log "staging engine from ${MOJO_ROOT}"
rm -rf "${DOCKER_DIR}/engine"
mkdir -p "${DOCKER_DIR}/engine"
cp -a "${MOJO_ROOT}/engine/." "${DOCKER_DIR}/engine/"
# Do not ship __pycache__ into the image context.
find "${DOCKER_DIR}/engine" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

chmod +x "${DOCKER_DIR}/methylGrapher.mojo.sh"

log "building ${IMAGE}"
docker build \
  -f "${DOCKER_DIR}/Dockerfile.mojo" \
  --build-arg "VG_PREBUILT=${VG_PREBUILT}" \
  -t "${IMAGE}" \
  "${DOCKER_DIR}"

log "smoke"
bash "${DOCKER_DIR}/smoke_64k.sh" "${IMAGE}"

log "done: ${IMAGE}"
log "Pin via actionConfig.methylgrapher_wgbs.engine=mojo (default image ${IMAGE})"
# Leave staged engine for inspect; CI may clean.

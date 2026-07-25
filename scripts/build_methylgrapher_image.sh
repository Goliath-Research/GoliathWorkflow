#!/usr/bin/env bash
# Build the methylGrapher(+vg) worker image once (CI / image refresh).
#
# Deployments must NOT run this. They only pull/load the published image
# (see scripts/ensure_methylgrapher_image.sh).
#
# Arm64: compiles vg with jemalloc=off so the binary runs on 64 KB-page
# kernels (Grace/GH200). Amd64: uses the stock vg GitHub release binary.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/workers/docker/methylgrapher"

VG_VERSION="${VG_VERSION:-1.70.0}"
METHYLGRAPHER_VERSION="${METHYLGRAPHER_VERSION:-0.2.0}"
IMAGE="${METHYL_METHYLGRAPHER_IMAGE:-epimethyl/methylgrapher:${VG_VERSION}}"
VG_SRC_DIR="${VG_SRC_DIR:-${REPO_ROOT}/.cache/vg-src/vg}"
SAVE_TAR="${METHYLGRAPHER_IMAGE_TAR:-}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"

log() { printf '[methylgrapher-image] %s\n' "$*"; }
die() { printf '[methylgrapher-image] ERROR: %s\n' "$*" >&2; exit 1; }

arch="$(uname -m)"
case "$arch" in
  aarch64|arm64) arch_key=arm64 ;;
  x86_64|amd64) arch_key=amd64 ;;
  *) die "unsupported arch: $arch" ;;
esac

install_build_deps() {
  [[ "${INSTALL_DEPS}" == "1" ]] || return 0
  if ! command -v sudo >/dev/null 2>&1; then
    log "sudo unavailable; assuming build deps already installed"
    return 0
  fi
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    build-essential cmake pkg-config git autoconf automake libtool \
    protobuf-compiler libprotobuf-dev \
    libjansson-dev libbz2-dev liblzma-dev zlib1g-dev libncurses-dev \
    ca-certificates curl
}

build_vg_arm64() {
  mkdir -p "$(dirname "${VG_SRC_DIR}")"
  if [[ ! -d "${VG_SRC_DIR}/.git" ]]; then
    git clone --branch "v${VG_VERSION}" https://github.com/vgteam/vg.git "${VG_SRC_DIR}"
  fi
  (
    cd "${VG_SRC_DIR}"
    git fetch --tags --force
    git checkout "v${VG_VERSION}"
    local i
    for i in 1 2 3 4 5 6 7 8; do
      git submodule sync --recursive
      if git submodule update --init --recursive; then
        break
      fi
      log "submodule update failed (attempt ${i}); retrying..."
      sleep $((i * 3))
      if [[ "${i}" -eq 8 ]]; then
        die "git submodule update failed after retries (often sourceware.org/elfutils 502)"
      fi
    done
    make -j"$(nproc)" jemalloc=off
  )
  [[ -x "${VG_SRC_DIR}/bin/vg" ]] || die "vg binary missing after build"
  "${VG_SRC_DIR}/bin/vg" version
  cp -f "${VG_SRC_DIR}/bin/vg" "${DOCKER_DIR}/vg.arm64"
  chmod +x "${DOCKER_DIR}/vg.arm64"
}

fetch_vg_amd64() {
  local dest="${DOCKER_DIR}/vg.amd64"
  curl -fsSL -o "${dest}" \
    "https://github.com/vgteam/vg/releases/download/v${VG_VERSION}/vg" \
  || curl -fsSL -o "${dest}" \
    "https://github.com/vgteam/vg/releases/download/v${VG_VERSION}/vg-amd64"
  chmod +x "${dest}"
  "${dest}" version
}

build_docker() {
  local prebuilt="vg.${arch_key}"
  [[ -f "${DOCKER_DIR}/${prebuilt}" ]] || die "missing ${DOCKER_DIR}/${prebuilt}"
  docker build \
    --build-arg "VG_VERSION=${VG_VERSION}" \
    --build-arg "METHYLGRAPHER_VERSION=${METHYLGRAPHER_VERSION}" \
    --build-arg "VG_PREBUILT=${prebuilt}" \
    -t "${IMAGE}" \
    -f "${DOCKER_DIR}/Dockerfile" \
    "${DOCKER_DIR}"
  log "built ${IMAGE}"
}

maybe_smoke() {
  if [[ "${SKIP_SMOKE}" == "1" ]]; then
    log "SKIP_SMOKE=1; not running smoke_64k.sh"
    return 0
  fi
  local page
  page="$(getconf PAGE_SIZE 2>/dev/null || echo 0)"
  if [[ "${arch_key}" == "arm64" && "${page}" != "65536" ]]; then
    log "host page size ${page} (not 65536); smoke deferred to a 64K worker (SKIP_SMOKE implied)"
    return 0
  fi
  bash "${DOCKER_DIR}/smoke_64k.sh" "${IMAGE}"
}

maybe_save() {
  [[ -n "${SAVE_TAR}" ]] || return 0
  mkdir -p "$(dirname "${SAVE_TAR}")"
  docker save "${IMAGE}" | gzip -c >"${SAVE_TAR}"
  log "saved ${SAVE_TAR} ($(du -h "${SAVE_TAR}" | awk '{print $1}'))"
}

main() {
  command -v docker >/dev/null 2>&1 || die "docker required"
  install_build_deps
  if [[ "${arch_key}" == "arm64" ]]; then
    build_vg_arm64
  else
    fetch_vg_amd64
  fi
  build_docker
  maybe_smoke
  maybe_save
  log "OK — publish/push this image; workers only pull/load it"
}

main "$@"

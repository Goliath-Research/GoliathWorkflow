#!/usr/bin/env bash
# 64K-page ARM64 smoke for the methylGrapher worker image (python or mojo).
set -euo pipefail

IMAGE="${1:-${METHYL_METHYLGRAPHER_IMAGE:-epimethyl/methylgrapher:1.70}}"

echo "== host page size =="
getconf PAGE_SIZE || true

echo "== image: ${IMAGE} =="
docker image inspect "${IMAGE}" >/dev/null

echo "== methylGrapher help =="
# Stock 0.2.0 accepts --help; mojo engine uses `help` (and also tolerates --help via argv).
if ! docker run --rm "${IMAGE}" methylGrapher help >/tmp/mg_help.txt 2>/tmp/mg_help.err; then
  docker run --rm "${IMAGE}" methylGrapher --help >/tmp/mg_help.txt
fi
grep -E 'Align|MethylCall|MergeCpG' /tmp/mg_help.txt

if [[ "${IMAGE}" == *mojo* ]]; then
  echo "== mojo engine provenance =="
  docker run --rm "${IMAGE}" python3 -c "import sys; sys.path.insert(0,'/opt/methylgrapher-mojo'); import engine; print(engine.__file__)"
fi

echo "== vg version =="
docker run --rm "${IMAGE}" vg version

echo "== samtools =="
docker run --rm "${IMAGE}" samtools --version | head -n 2

echo "OK: methylGrapher image smoke passed for ${IMAGE}"

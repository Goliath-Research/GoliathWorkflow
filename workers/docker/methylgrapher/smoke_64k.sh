#!/usr/bin/env bash
# 64K-page ARM64 smoke for the methylGrapher worker image.
set -euo pipefail

IMAGE="${1:-${METHYL_METHYLGRAPHER_IMAGE:-epimethyl/methylgrapher:1.70}}"

echo "== host page size =="
getconf PAGE_SIZE || true

echo "== image: ${IMAGE} =="
docker image inspect "${IMAGE}" >/dev/null

echo "== methylGrapher help =="
docker run --rm "${IMAGE}" methylGrapher --help >/tmp/mg_help.txt
grep -E 'Align|MethylCall|MergeCpG' /tmp/mg_help.txt

echo "== vg version =="
docker run --rm "${IMAGE}" vg version

echo "== samtools =="
docker run --rm "${IMAGE}" samtools --version | head -n 2

echo "OK: methylGrapher image smoke passed for ${IMAGE}"

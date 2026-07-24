# Multi-arch methylGrapher + vg worker image for WGBS pangenome SamplePrep.
# Build indexes on a 4K-page host; this image is for align/extract on 64K ARM64 workers.
#
# Example:
#   docker buildx build --platform linux/arm64,linux/amd64 \
#     -t epimethyl/methylgrapher:1.70 --push \
#     -f workers/docker/methylgrapher/Dockerfile .
#
# Smoke (64K ARM64):
#   docker run --rm epimethyl/methylgrapher:1.70 methylGrapher --help
#   docker run --rm epimethyl/methylgrapher:1.70 vg version
#   getconf PAGE_SIZE   # expect 65536 on GH200 / Grace workers

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3 python3-pip python3-venv \
        samtools tabix pigz \
    && rm -rf /var/lib/apt/lists/*

# Install vg (pin via build-arg). Operators must keep this aligned with index builder.
ARG VG_VERSION=1.70.0
ARG TARGETARCH
RUN set -eux; \
    arch="$TARGETARCH"; \
    if [ "$arch" = "arm64" ]; then vg_arch="arm64"; else vg_arch="amd64"; fi; \
    curl -fsSL -o /usr/local/bin/vg \
      "https://github.com/vgteam/vg/releases/download/v${VG_VERSION}/vg-${vg_arch}" \
    || curl -fsSL -o /usr/local/bin/vg \
      "https://github.com/vgteam/vg/releases/download/v${VG_VERSION}/vg"; \
    chmod +x /usr/local/bin/vg

# Install methylGrapher from PyPI / git (pin via build-arg).
ARG METHYLGRAPHER_VERSION=0.2.0
RUN pip3 install --no-cache-dir --break-system-packages \
      "methylGrapher==${METHYLGRAPHER_VERSION}" \
    || pip3 install --no-cache-dir --break-system-packages \
      "git+https://github.com/twlab/methylGrapher.git@v${METHYLGRAPHER_VERSION}"

LABEL org.opencontainers.image.title="methylGrapher WGBS worker" \
      org.opencontainers.image.description="methylGrapher + vg for MethylPipeline pangenome_wgbs SamplePrep" \
      methylpipeline.vg_version="${VG_VERSION}" \
      methylpipeline.methylgrapher_version="${METHYLGRAPHER_VERSION}"

ENTRYPOINT []
CMD ["methylGrapher", "--help"]

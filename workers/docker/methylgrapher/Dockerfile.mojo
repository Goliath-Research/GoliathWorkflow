# methylGrapher-mojo dual-ship image (native Mojo CLI + patched engine) for WGBS SamplePrep.
# Same vg/jemalloc=off story as Dockerfile; entrypoint stays `methylGrapher`.
#
# Build via scripts/build_methylgrapher_mojo_image.sh (stages engine/, src/, and a
# trimmed mojo-env/ from METHYLGRAPHER_MOJO_ROOT before docker build).
#
# Smoke:
#   bash workers/docker/methylgrapher/smoke_64k.sh epimethyl/methylgrapher:1.70-mojo
#
# Rollback: set actionConfig.methylgrapher_wgbs.engine=python and image
# epimethyl/methylgrapher:1.70. In-image: METHYLGRAPHER_MCALL_ENGINE=python
# (methylGrapher.mojo.sh skips Mojo and runs engine.cli).

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3 python3-pip python3-venv \
        samtools tabix pigz \
        libcairo2 libatomic1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ARG VG_VERSION=1.70.0
ARG VG_PREBUILT=vg.arm64

COPY ${VG_PREBUILT} /usr/local/bin/vg
COPY vg_libs/ /usr/local/lib/
RUN chmod +x /usr/local/bin/vg && ldconfig && vg version

# Stock 0.2.0 kept as rollback reference inside the image (optional import).
ARG METHYLGRAPHER_VERSION=0.2.0
RUN pip3 install --no-cache-dir --break-system-packages \
      "methylGrapher==${METHYLGRAPHER_VERSION}" \
    || pip3 install --no-cache-dir --break-system-packages \
      "git+https://github.com/twlab/methylGrapher.git@v${METHYLGRAPHER_VERSION}"

# Patched engine + native Mojo CLI / MethylCall hot path.
COPY engine /opt/methylgrapher-mojo/engine
COPY src /opt/methylgrapher-mojo/src
COPY mojo-env /opt/methylgrapher-mojo/mojo-env
COPY methylGrapher.mojo.sh /usr/local/bin/methylGrapher
RUN chmod +x /usr/local/bin/methylGrapher /opt/methylgrapher-mojo/mojo-env/bin/mojo \
    && python3 -c "import sys; sys.path.insert(0,'/opt/methylgrapher-mojo'); from engine import cli; print('engine ok')" \
    && methylGrapher help | head -5

LABEL org.opencontainers.image.title="methylGrapher-mojo WGBS worker" \
      org.opencontainers.image.description="Native Mojo MethylCall + patched engine + vg for pangenome_wgbs SamplePrep" \
      methylpipeline.vg_version="${VG_VERSION}" \
      methylpipeline.methylgrapher_engine="mojo" \
      methylpipeline.methylgrapher_version="0.1.0-mojo"

ENTRYPOINT []
CMD ["methylGrapher", "help"]

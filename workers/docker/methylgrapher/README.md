# methylGrapher worker image

Pinned runtime for `alignmentMode: pangenome_wgbs` (`sample.methylgrapher_wgbs_*`).

## Engines (dual-ship)

| `actionConfig.methylgrapher_wgbs.engine` | Image (default) | Notes |
|-----------------------------------------|-----------------|-------|
| `python` (default) | `epimethyl/methylgrapher:1.70` | Stock methylGrapher 0.2.0 + GAF-header patch |
| `mojo` | `epimethyl/methylgrapher:1.70-mojo` | methylGrapher-mojo patched engine (single GFA worker; CLI parity) |

Build mojo image: `scripts/build_methylgrapher_mojo_image.sh` (requires `METHYLGRAPHER_MOJO_ROOT` and a prior vg bake from `build_methylgrapher_image.sh`). Plan: [`docs/plans/methylgrapher-mojo-cutover.plan.md`](../../../docs/plans/methylgrapher-mojo-cutover.plan.md).

## Compute model (CPU only — by design)

methylGrapher and stock `vg` **do not use NVIDIA GPUs**. Baking a CUDA base image or passing
`--gpus` to `docker run` does **not** accelerate Align / MethylCall / MergeCpG / surject.
The worker invokes the image without GPU flags (`workers/methyl_worker/methylgrapher_wgbs_runner.py`).

| Mode | Tool | Accelerator |
|------|------|-------------|
| `linear` | Clara Parabricks `fq2bam_meth` | GPU |
| `pangenome` | Clara Parabricks `giraffe` | GPU |
| `pangenome_wgbs` | methylGrapher + `vg` (this image) | **CPU threads + host RAM** |

On a Grace/GH200 node, this path still benefits from many cores and large memory, but wall time
is typically **much longer** than Parabricks linear on the same host (dual C2T/G2A giraffe plus
surject/sort/markdup). Use site/profile `actionConfig.methylgrapher_wgbs.threads` to size
parallelism; calibrate cost vs CpG yield with
[`scripts/compare_sample_prep_linear_vs_wgbs.sh`](../../../scripts/compare_sample_prep_linear_vs_wgbs.sh).

## Production model (do not compile on deploy)

| When | What |
|------|------|
| **CI / image refresh** | `scripts/build_methylgrapher_image.sh` (ADO: `ci/azure-pipelines-methylgrapher-image.yml`) builds vg once with `jemalloc=off` on arm64, installs methylGrapher, publishes a `docker save` tarball (and optionally `docker push`). |
| **Cluster deploy** | Set `METHYL_METHYLGRAPHER_IMAGE`, then `scripts/ensure_methylgrapher_image.sh` → **pull or load only**. |

Rebuild the image only when **vg**, **methylGrapher**, or this Dockerfile changes — not on every study or release promote.

## Why arm64 builds vg from source

Stock GitHub / quay.io arm64 `vg` binaries link jemalloc compiled for **4 KB** pages. On **64 KB** kernels (Grace / GH200) they abort with `Unsupported system page size`. CI builds `make jemalloc=off` once and bakes that binary into the image.

Amd64 uses the stock vg release binary.

## Local (developer) build

```bash
./scripts/build_methylgrapher_image.sh
# optional: METHYLGRAPHER_IMAGE_TAR=/tmp/mg.tar.gz ./scripts/build_methylgrapher_image.sh
bash workers/docker/methylgrapher/smoke_64k.sh   # on a real 64K host
```

## Deploy on a worker

```bash
export METHYL_METHYLGRAPHER_IMAGE=epimethyl/methylgrapher:1.70
# either registry:
#   docker pull "$METHYL_METHYLGRAPHER_IMAGE"
# or CI artifact:
#   export METHYLGRAPHER_IMAGE_TAR=/path/to/methylgrapher-1.70-arm64.tar.gz
./scripts/ensure_methylgrapher_image.sh
```

Image tag is `:1.70` (platform matrix). CI compiles vg `v1.70.0` but publishes `:1.70` — do not retag to the full vg semver unless you also change `METHYLGRAPHER_IMAGE_*`.

`scripts/write_worker_env.sh` writes `METHYL_METHYLGRAPHER_IMAGE` from `platform_matrix.env` when set.

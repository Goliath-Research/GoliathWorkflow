# methylGrapher worker image

Pinned runtime for `alignmentMode: pangenome_wgbs` (`sample.methylgrapher_wgbs_*`).

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

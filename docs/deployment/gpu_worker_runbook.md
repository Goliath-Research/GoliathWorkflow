# GPU worker node runbook

Operator checklist for NVIDIA driver, shared Docker data-root, and Parabricks on production GPU VMs.

Related: [production_release.md](production_release.md), [worker_provision.md](worker_provision.md), [platform_matrix.md](platform_matrix.md).

## Prerequisites

| Check | Command |
|-------|---------|
| Shared `/work` mounted | `ls /work/epimethyl/current/manifest.json` |
| NVIDIA driver | `nvidia-smi` |
| Architecture | `uname -m` → `aarch64` or `x86_64` |
| Host tools (per VM) | `bash …/verify_host_tools.sh` — **samtools**, **bedtools**, **fastp** via `install_host_tools_gpu_vm.sh` / `setup_host.sh --system-deps` (not on `/work` NFS) |
| samtools TMPDIR | Prefer local disk e.g. `TMPDIR=/var/tmp/methyl-samtools` (faster than NFS spill) |

## Driver and CUDA matrix (per architecture)

| Platform | `uname -m` | MethylExtractor dir | Parabricks default | Host CuPy (optional) |
|----------|------------|---------------------|--------------------|----------------------|
| ARM64 (Grace, etc.) | `aarch64` | `methyl-extractor-aarch64/` | See `platform_matrix.env` — **verify ARM on NGC** | `libnvrtc12`, pip `requirements-gpu-cuda12.txt` |
| x86_64 | `x86_64` / `amd64` | `methyl-extractor-amd64/` | `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1` | Same |

Record tested combinations in release `manifest.json`:

- `min_driver_version`
- `parabricks_image` + `parabricks_image_digest`

**Linear / stock pangenome alignment** uses CUDA **inside** the Clara Parabricks container when that mode is **explicitly** configured. Host CUDA toolkit is not required for fq2bam.

### native-Mojo methylGrapher (`pangenome_wgbs`)

Buffy default WGBS pangenome Align runs **native-Mojo** on the same NVIDIA workers via `epimethyl/methylgrapher:1.70-mojo-cuda` (`actionConfig.methylgrapher_wgbs.engine=mojo`, `align_engine=gpu_giraffe|mojo_giraffe`, `giraffe_device=auto|nvidia`). Pass `--gpus all` (or site GPU flags) into the methylGrapher container — fail-closed on DeviceContext errors; do **not** switch to Clara on Mojo failure. AMD ROCm twin: [`worker-rocm.md`](worker-rocm.md). Canonical contract: [`mojo-multi-gpu-dual-align.md`](../architecture/mojo-multi-gpu-dual-align.md), [`workers/docker/methylgrapher/README.md`](../../workers/docker/methylgrapher/README.md).

**HBM admission / release (GH200).** One Align or MojoGiraffe QC ≈ a full card. Pin in `worker.env` (not Python defaults):

| Env | Role |
|-----|------|
| `METHYL_GPU_HBM_FREE_FRACTION=0.90` | Require ≥ this share of *total* HBM free before starting a GPU action, and again after it finishes (orphan kill + reclaim) |
| `METHYL_GPU_ALIGN_HBM_WAIT_S=180` | Seconds to wait for admit / post-action release |
| `METHYL_GPU_ALIGN_MIN_FREE_GIB` | Legacy absolute GiB floor (used only when `FREE_FRACTION` is unset) |

The worker flock kills leftover `Align` **and** `MojoGiraffe` containers, then waits for the free fraction. Do **not** run `nvidia-smi --gpu-reset` on GH200 (Grace–Hopper coherent fabric); reboot or kill holders instead.
## Proteomics GPU tools (DIA-NN / Prosit / Casanovo)

The proteomics pack adds non-Parabricks GPU Docker tools that run on the same GPU VMs
(Lambda/Nebius GH200). Each has its own image env and advertises a capability only when
the image is set on the node:

| Capability | Image env | Notes |
|------------|-----------|-------|
| `proteomics.diann` | `METHYL_DIANN_IMAGE` | DIA search + quant (GPU) |
| `proteomics.prosit` | `METHYL_PROSIT_IMAGE` | rescoring / in-silico library (GPU) |
| `proteomics.casanovo` | `METHYL_CASANOVO_IMAGE` | de novo (GPU) |
| `proteomics.sage` | `METHYL_SAGE_IMAGE` (or `sage` binary / `METHYL_SAGE_BIN`) | DDA search + LFQ — **CPU** (Apache-2.0, open MSFragger alternative); multi-arch, no page-size caveat; lands on non-GPU workers |
| `proteomics.panel_ingest` | (none) | panel matrix ingest — **CPU**, lands on non-GPU workers |

**GH200 / ARM64 caveat.** Workers run `docker run` host-native (no `--platform` pin), so on
Grace/Hopper (`aarch64`) these images **must be linux/arm64 or multi-arch**. Set defaults in
`scripts/platform_matrix.env` (`PROTEOMICS_*_IMAGE_aarch64`) and **verify an arm64 GPU build
exists** before enabling — otherwise the GPU benefit does not materialize on these VMs. A
known GH200 gotcha: some CPU images crash under the 64 KB memory page size (see
`scripts/download_pangenome_hprc_grch38.sh`); test each proteomics image for page-size/arch
before production. `setup_gpu_node.sh` writes `proteomics.env` (loaded by the worker
systemd unit) from these matrix defaults.

**Centroid GPU paths** may need host NVRTC (`setup_host.sh --system-deps --gpu`).

## Shared Docker data-root

All GPU VMs use one image store on fast shared storage:

```json
{
  "data-root": "/work/epimethyl/docker"
}
```

Install/configure via:

```bash
RUNTIME="$(readlink -f /work/epimethyl/current/runtime-bundle)"
bash "$RUNTIME/scripts/setup_gpu_node.sh" \
  --docker-data-root /work/epimethyl/docker \
  --env-dir /work/epimethyl/env
```

Do **not** pass `--pull-parabricks` on node join if release promote already pulled the image.

## Release promote (once per version)

From one admin node with NGC login:

```bash
bash /work/epimethyl/current/runtime-bundle/scripts/promote_release.sh \
  --root /work/epimethyl \
  --release /work/epimethyl/releases/2026.6.1 \
  --arch "$(platform_arch_key "$(uname -m)" 2>/dev/null || echo aarch64)" \
  --pull-parabricks
```

Run pulls **serially** — never from all VMs at once.

## Driver upgrade window

1. Drain worker: `sudo systemctl stop methyl-worker.service`
2. Upgrade driver; reboot if required
3. `nvidia-smi` + `bash scripts/verify_parabricks.sh`
4. `bash scripts/verify_e2e_node.sh`
5. `sudo systemctl start methyl-worker.service`

## Verification

```bash
source /work/epimethyl/env/worker.env
source /work/epimethyl/env/parabricks.env
bash /work/epimethyl/current/runtime-bundle/scripts/verify_e2e_node.sh
```

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `docker pull` fails | NGC login required on promote node |
| Parabricks verify fails | Wrong image for SKU; override `METHYL_PARABRICKS_IMAGE` |
| overlay2 errors on shared FS | Validate cluster FS with Docker; use `docker save` tarball in manifest |
| CuPy NVRTC missing (ARM) | `sudo apt-get install -y libnvrtc12 libnvrtc-builtins12` |

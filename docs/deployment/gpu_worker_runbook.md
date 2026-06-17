# GPU worker node runbook

Operator checklist for NVIDIA driver, shared Docker data-root, and Parabricks on production GPU VMs.

Related: [production_release.md](production_release.md), [worker_provision.md](worker_provision.md), [platform_matrix.md](platform_matrix.md).

## Prerequisites

| Check | Command |
|-------|---------|
| Shared `/work` mounted | `ls /work/epimethyl/current/manifest.json` |
| NVIDIA driver | `nvidia-smi` |
| Architecture | `uname -m` → `aarch64` or `x86_64` |

## Driver and CUDA matrix (per architecture)

| Platform | `uname -m` | MethylExtractor dir | Parabricks default | Host CuPy (optional) |
|----------|------------|---------------------|--------------------|----------------------|
| ARM64 (Grace, etc.) | `aarch64` | `methyl-extractor-aarch64/` | See `platform_matrix.env` — **verify ARM on NGC** | `libnvrtc12`, pip `requirements-gpu-cuda12.txt` |
| x86_64 | `x86_64` / `amd64` | `methyl-extractor-amd64/` | `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1` | Same |

Record tested combinations in release `manifest.json`:

- `min_driver_version`
- `parabricks_image` + `parabricks_image_digest`

**Alignment** uses CUDA **inside** the Parabricks container. Host CUDA toolkit is not required for fq2bam.

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
  --release /work/epimethyl/releases/2026.06.1 \
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

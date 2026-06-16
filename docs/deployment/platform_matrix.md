# Platform matrix (ARM64 vs x86_64)

MethylPipeline GPU worker nodes use **host-native** Python (`.venv`) and invoke **Docker only for Clara Parabricks**. Native **MethylExtractor** must be built on each machine architecture.

## Architecture detection

Scripts use `uname -m` via [`scripts/detect_platform.sh`](../../scripts/detect_platform.sh):

| `uname -m` | Matrix key | MethylExtractor build dir |
|------------|------------|---------------------------|
| `aarch64`  | `aarch64`  | `build/dynamic/arm64/`    |
| `x86_64`   | `amd64`    | `build/dynamic/x64/`      |

Defaults live in [`scripts/platform_matrix.env`](../../scripts/platform_matrix.env).

## Parabricks container images

Set `METHYL_PARABRICKS_IMAGE` per node after confirming the tag on [NGC Clara Parabricks](https://catalog.ngc.nvidia.com).

| Platform | Default (override as needed) |
|----------|------------------------------|
| x86_64   | `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1` |
| aarch64  | Same tag in `platform_matrix.env` — **verify ARM support** for your GPU SKU (Grace, etc.) |

Hopper/Blackwell vs Ampere may require different image generations. Run:

```bash
export METHYL_PARABRICKS_IMAGE=<your-tag>
bash scripts/verify_parabricks.sh
```

## CUDA Python stack

Both architectures install from:

- [`requirements-gpu-cuda12.txt`](../../requirements-gpu-cuda12.txt)
- [`scripts/constraints-cuda12.txt`](../../scripts/constraints-cuda12.txt)

On **ARM64**, `setup_host.sh` may require system NVRTC packages:

```bash
sudo apt-get install -y libnvrtc12 libnvrtc-builtins12
```

## What is not multi-arch today

- [`docker/Dockerfile.production`](../../docker/Dockerfile.production) — Miniforge x86_64 only; **not** used for GPU worker provisioning.
- MethylExtractor — must `make` on each target architecture (enforced by `make install`).

# GPU workers on AMD ROCm (native-Mojo Align)

Companion to [`docs/architecture/mojo-multi-gpu-dual-align.md`](../architecture/mojo-multi-gpu-dual-align.md). Same native-Mojo binary as NVIDIA; site image tag + host ROCm runtime select HIP. Clara Parabricks is NVIDIA-only and is never used as an automatic Mojo fallback.

## Image

```bash
METHYLGRAPHER_MOJO_GPU_VARIANT=rocm \
METHYLGRAPHER_MOJO_IMAGE_TAG=1.70-mojo-rocm \
  bash scripts/build_methylgrapher_mojo_image.sh
```

Load on each ROCm worker (NFS tar pattern same as CUDA `:1.70-mojo`).

## Site / procedure pins (resolvedConfig — not worker.env)

```json
"actionConfig": {
  "methylgrapher_wgbs": {
    "engine": "mojo",
    "align_engine": "gpu_giraffe",
    "align_device": "auto",
    "giraffe_device": "auto",
    "image": "epimethyl/methylgrapher:1.70-mojo-rocm"
  },
  "parabricks": {
    "engine": "mojo",
    "align_device": "auto",
    "image": "epimethyl/methylgrapher:1.70-mojo-rocm",
    "bwa_threads": 32
  }
}
```

## Container runtime

Expose KFD/DRI (example flags; site may set `parabricks.gpu_flags`):

```text
--device=/dev/kfd --device=/dev/dri --group-add video
```

Clara `--gpus all` is NVIDIA-only; do not use it on ROCm nodes when `engine=mojo`.

## Capabilities

Unchanged: `methylgrapher.wgbs_align`, `methylgrapher.wgbs_extract`, `parabricks.fq2bam`. Register workers as today; image + `resolvedConfig` select CUDA vs ROCm.

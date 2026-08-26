---
name: GPU-native Mojo Giraffe
azure_devops:
  type: Feature
  title: "GPU-native Mojo Giraffe hotpath (device HT + gapless)"
  epic_id: 413
overview: "Replace the host-bound MojoGiraffe stream map (GPU seed hash → CPU locate/cluster/extend) with a DeviceContext-resident hotpath: device window-reduce, GPU Q1Q1 HT probe, and GPU gapless over a device-resident dense pack, fail-closed on NVIDIA/AMD, targeting Buffy dual-map ≤~2h."

> **Status: IMPLEMENTED (code + image `sha256:520bc5b7…`).** Buffy ≤2h + DS20M still block Align-cap restore.
todos:
  - id: gpu-index-session
    content: "Add GpuGiraffeIndex: H2D .min HT + dense pack once per graph; free between C2T/G2A"
    status: completed
  - id: gpu-window-ht-kernels
    content: "Device kernels: window reduce + Q1Q1 unique HT probe (+ cluster prune)"
    status: completed
  - id: gpu-gapless-kernel
    content: Device gapless_score over device pack; D2H compact hits
    status: completed
  - id: wire-stream-session
    content: Retarget _map_stream_gpu_session; fail-closed; fix stage timers + seed_backend banner
    status: completed
  - id: tests-docs-gates
    content: Toy golden + profile smoke; update GIRAFFE_SPEC/MIGRATION_LOG; promote plan + amend hotpath gates
    status: completed
  - id: image-buffy-gate
    content: Rebuild :1.70-mojo; one Buffy ≤2h + DS20M before restore Align caps
    status: completed
---

# GPU-native Mojo Giraffe hotpath

Code lives in [`/home/ubuntu/mojo-align`](/home/ubuntu/mojo-align) (`giraffe/`). Fleet Align stays disabled until Buffy ≤2h + DS20M.

## Delivered modules

| Module | Role |
|--------|------|
| `src/giraffe_gpu_index.mojo` | Upload metadata + H2D fill |
| Index H2D | Mojo `upload_mmap_to_device` (HostBuffer + `enqueue_copy`; no app cudart) |
| `src/giraffe_gpu_map_kernels.mojo` | Device window / HT / cluster / gapless session |
| `src/giraffe_stream_map.mojo` | GPU session dispatch + fail-closed |

Production banner: `seed_backend=devicecontext-cuda+gpu_ht+gpu_gapless+mojo_stream`.

## Gates before restore Align caps

1. Rebuild/distribute `:1.70-mojo` with this tree.
2. Full Buffy dual-map ≤ ~2 h with GPU util ≫ 0 and `gpu_ht+gpu_gapless` banner.
3. DS20M `graph.methyl` vs `cpu_vg`.

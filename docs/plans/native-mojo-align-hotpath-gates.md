# Native Mojo Align Hotpath — gate status

Companion to [`native-mojo-align-hotpath.plan.md`](native-mojo-align-hotpath.plan.md) and superseding GPU work in [`gpu-native-mojo-giraffe.plan.md`](gpu-native-mojo-giraffe.plan.md).

> **Correction (2026-08-09):** The earlier “native Mojo GPU stream map” cutover was **seed-only DeviceContext** (host window-reduce / mmap HT / gapless). Live Buffy showed ~20 k pairs/s at 0% GPU util. Production now requires **`gpu_ht+gpu_gapless`** ([`gpu-native-mojo-giraffe.plan.md`](gpu-native-mojo-giraffe.plan.md)).

| Gate | Status | Evidence |
|------|--------|----------|
| Toy GBZ PE stream map (CPU) | **PASS** | `device=cpu` → 6 GAF lines + `ri`/`os`/`rc` |
| Toy GBZ PE GPU-native banner | **PASS** | `device=nvidia` → `seed_backend=…+gpu_ht+gpu_gapless+mojo_stream`; short-read fixture 6 lines |
| GPU stage timers on longer reads | **PASS** | non-zero `gpu_seed` / `locate` / `cluster_extend` with 80 bp toy FASTQ |
| Prior seed-only stream map as fleet path | **FAIL / retired** | host-bound; operator-aborted 2026-08-09 |
| Dual-map DeviceContext safe | **PASS** (serialized) | `METHYLGRAPHER_DUAL_GRAPH_PARALLEL=0` |
| QC BAM off vg fallback | **PASS** | `qc_bam_fallback=error` |
| Image `:1.70-mojo` with GPU-native tree | **PASS** (50-58) | config `sha256:520bc5b7c06d9a5e84b02391d35c2400e84b86ba1ad410ee5d8c3b9a4d935fd2`; NFS tar updated |
| Fleet sisters load | **PENDING** operator | after new digest; Align caps still stripped |
| Full Buffy dual-map ≤ ~2 h | **PENDING** operator | require `gpu_ht+gpu_gapless` banner + GPU util ≫ 0 |
| DS20M `graph.methyl` vs `cpu_vg` | **PENDING** operator | `scripts/parity_compare.py` |

## Do not restore Align caps / ACTIVE until

1. New image digest on all four GH200s with `gpu_ht+gpu_gapless` path.
2. At least one Buffy dual-map ≤ ~2 h.
3. No Align log shows host mmap locate as the GPU production path or `host-nvidia-fallback`.

## Kill / hold (ops)

- `/work/epimethyl/images/URGENT_KILL_HOST_MOJO.md`
- `/work/epimethyl/images/fleet-kill-host-mojo-align.sh`
- Workers 1–4: Align caps stripped; `desired_state=STOPPING` until gates pass.

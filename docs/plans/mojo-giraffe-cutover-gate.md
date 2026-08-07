# Mojo Giraffe cutover gate

Companion to [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md) and
[`gh200-align-phase3-gate.md`](gh200-align-phase3-gate.md).

## Status (2026-08-06)

| Criterion | Status |
|-----------|--------|
| Toy PE GAF vs golden (`path` / `cs` / `ri` / `os` / `rc`) | **PASS** |
| Portable GPU seed path on GH200 (`nvidia:sm_90` label + device helper) | **PASS** (CuPy optional) |
| `gpu_giraffe` prefers Mojo (fallback default `mojo`, not hard-coded `vg`) | **PASS** |
| Auto-vg for oversized / GBZ-only indexes | **PASS** (safe progressive) |
| DS20M MethylCall `graph.methyl` vs `cpu_vg` | **PENDING** (needs subset GFA or GBZ-native) |
| Full Buffy dual-map Align ≤ ~2 h on GH200 | **PENDING** operator measure |
| Site flip `align_engine=gpu_giraffe` on GH200 fleets as “Mojo map done” | **BLOCKED** until Buffy wall + DS20M/GBZ parity |

## Operator knobs

```bash
export METHYLGRAPHER_ALIGN_ENGINE=gpu_giraffe
export METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo   # default; emergency: vg
export METHYLGRAPHER_GIRAFFE_DEVICE=auto         # cpu|nvidia|amd
export METHYLGRAPHER_GIRAFFE_GFA=/path/to/subset.wl.gfa   # optional
export METHYLGRAPHER_MOJO_GIRAFFE_MAX_GFA_BYTES=67108864  # 0 = unlimited
```

Rollback: `align_engine=cpu_vg` or `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=vg`.

## Site flip (only after Buffy + parity gates)

```json
"actionConfig": {
  "methylgrapher_wgbs": {
    "engine": "mojo",
    "image": "epimethyl/methylgrapher:1.70-mojo",
    "align_engine": "gpu_giraffe",
    "threads": 64
  }
}
```

Parabricks remains BAM-only for science GAF (Phase 0 NO-GO).

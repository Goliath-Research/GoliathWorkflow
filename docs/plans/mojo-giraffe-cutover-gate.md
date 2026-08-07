# Mojo Giraffe cutover gate

Companion to [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md),
[`gbz-native-mojo-giraffe.plan.md`](gbz-native-mojo-giraffe.plan.md), and
[`gh200-align-phase3-gate.md`](gh200-align-phase3-gate.md).

## Status (2026-08-07)

| Criterion | Status |
|-----------|--------|
| Toy PE GAF vs golden (GFA path) | **PASS** |
| Toy GBZ→GAF vs golden (`path` / `cs` / PE tags) | **PASS** |
| Portable GPU seed on GH200 (`nvidia:sm_90`) | **PASS** |
| `gpu_giraffe` prefers **GBZ quartet** (no GFA size-cap) | **PASS** |
| Production C2T/G2A segment caches built | **PENDING** (`build_mojo_gbz_cache.py`) |
| DS20M / Buffy-subset `graph.methyl` vs `cpu_vg` | **PENDING** |
| Full Buffy dual-map Align ≤ ~2 h on GH200 | **PENDING** operator measure |
| Site “Mojo map done” claim | **BLOCKED** until Buffy wall + MethylCall parity |

## Operator knobs (`pangenome_wgbs` only)

```bash
export METHYLGRAPHER_ALIGN_ENGINE=gpu_giraffe
export METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo   # emergency: vg
export METHYLGRAPHER_GIRAFFE_DEVICE=nvidia
# After caches exist for both strands:
# python …/build_mojo_gbz_cache.py --gbz …/hprc-d9-bs.wl.C2T.giraffe.gbz
# python …/build_mojo_gbz_cache.py --gbz …/hprc-d9-bs.wl.G2A.giraffe.gbz
```

Rollback: `align_engine=cpu_vg` or `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=vg`.

## Site flip (after Buffy + parity gates)

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

Do **not** change cfDNA / linear / stock `pangenome` packs. Parabricks remains BAM-only for science GAF (Phase 0 NO-GO). Linear arm = comparator only.

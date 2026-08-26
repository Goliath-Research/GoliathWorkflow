# GH200 Align Phase 3 gate

Companion to [`gh200-wgbs-dual-graph-align.plan.md`](gh200-wgbs-dual-graph-align.plan.md).

## Status (2026-08-06)

| Criterion | Status |
|-----------|--------|
| Parabricks GAF + named-coordinates | **FAIL** (Phase 0 NO-GO on 4.7.0-1) |
| Mojo Align orchestration + backends | **PASS** (shipped) |
| Image `:1.70-mojo` with Align native | **PASS** (rebuilt on GH200 host) |
| Full Buffy Align wall ≤ ~2 h on GH200 | **PENDING** operator measurement (local NVMe work dir) |
| MethylCall GAF science parity vs CPU ref | **PENDING** on full-sample GAF from new Align |
| Site flip `align_engine=gpu_giraffe` on GH200 fleets | **BLOCKED** until wall + parity pass (operator); living docs already describe native-Mojo GPU as the SamplePrep contract — this row is the fleet flip gate, not a “CPU-only” claim |
| Mojo Giraffe fixture GAF + prefer-mojo backend | **PASS** — see [`mojo-giraffe-cutover-gate.md`](mojo-giraffe-cutover-gate.md) |

## How to measure the wall gate

```bash
# On GH200, prefer local NVMe for work_dir (not NFS) during Align.
export METHYLGRAPHER_ALIGN_ENGINE=gpu_giraffe
export METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo   # default; auto-vg if GFA too large
export METHYLGRAPHER_GIRAFFE_DEVICE=nvidia
# Run sample.methylgrapher_wgbs_align for one full Buffy sample; record wall
# from methylgrapher_align.log COMMAND → GAF land.
```

When Parabricks (or successor) gains GAF output, re-run `giraffe/scripts/spike_gh200_dual_graph_align.sh` in mojo-align and update Phase 0.
Also see [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md).

## Site flip (only after gate)

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

Enroll GH200 workers so capabilities include `methylgrapher.wgbs_gpu_align`.

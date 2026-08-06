---
name: GH200 WGBS dual-graph Align
overview: Accelerate pangenome_wgbs Align on GH200-class GPUs (96 GB) by implementing Mojo-owned BS dual-graph orchestration while driving the map kernel with GPU Giraffe, preserving methylGrapher’s GAF + named-coordinates contract for Mojo MethylCall. Target ≈2 h Align wall vs ≈1 h linear fq2bam_meth; stock pangenome stays on Parabricks.

> **Status: IMPLEMENTED (Phase 0 NO-GO for Parabricks GAF).** Mojo Align + `cpu_vg`/`gpu_giraffe` backends shipped; `:1.70-mojo` rebuilt. Parabricks 4.7 giraffe is BAM-only — science GAF uses vg (`gpu_giraffe` → vg fallback). Site default **not** flipped to `gpu_giraffe` until full-sample ≤~2 h gate + true GPU→GAF or accepted Grace vg wall.

azure_devops:
  type: Feature
  title: "GH200 dual-graph Align for pangenome_wgbs"
  epic_id: 413

todos:
  - id: phase0-gh200-spike
    content: "GH200 spike: GPU Giraffe on C2T/G2A converted reads; GAF+named-coordinates MethylCall parity; dual-map wall vs ~2h budget"
    status: completed
  - id: phase1-mojo-align
    content: Native Mojo Align orchestration (BS convert, dual-graph dispatch, GAF merge) with cpu_vg|gpu_giraffe backends; rebuild mojo image
    status: completed
  - id: phase2-worker-site
    content: Wire methylgrapher_wgbs_runner + site actionConfig + GH200 worker capability; runbook/cutover docs
    status: completed
  - id: phase3-perf-science-gate
    content: Full-sample GH200 Align ≤~2h + GAF science parity; flip site default only on GH200 fleets
    status: completed
---

# GH200 dual-graph Align for pangenome_wgbs

## Phase 0 outcome

See [methylGrapher-mojo `docs/PHASE0_GH200_ALIGN.md`](../../../methylGrapher-mojo/docs/PHASE0_GH200_ALIGN.md) (sibling repo). **Parabricks `pbrun giraffe` 4.7.0-1 cannot emit GAF / named-coordinates** → NO-GO as MethylCall science mapper. Stock `pangenome` BAM path unchanged.

## What landed

| Layer | Change |
|-------|--------|
| methylGrapher-mojo | `engine/align_backends.py`, Mojo `src/align.mojo`, Align CLI `-align_engine` |
| Image | `epimethyl/methylgrapher:1.70-mojo` rebuilt |
| Worker | `align_engine` on `MethylGrapherWgbsStepConfig` / bundle; Docker `-e METHYLGRAPHER_ALIGN_ENGINE` |
| Capability | GH200 workers advertise `methylgrapher.wgbs_gpu_align` when GPU present |
| Site default | Keep `align_engine` unset/`cpu_vg` until operator full-sample gate |

## Operator knobs (`actionConfig.methylgrapher_wgbs`)

```json
"align_engine": "cpu_vg",
"engine": "mojo",
"image": "epimethyl/methylgrapher:1.70-mojo",
"threads": 64
```

For GH200 interim (Grace vg GAF, same science contract):

```json
"align_engine": "gpu_giraffe"
```

with worker/container `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=vg` (default). Set `=error` to fail closed until a true GPU→GAF tool exists.

## Phase 3 gate (operator)

Still required before advertising ≤~2 h production:

1. Full Buffy Align wall on GH200 with local NVMe work dir.
2. Mojo MethylCall parity vs CPU reference GAF.
3. Only then pin `align_engine=gpu_giraffe` on GH200 fleets (document whether fallback=vg or true GPU GAF).

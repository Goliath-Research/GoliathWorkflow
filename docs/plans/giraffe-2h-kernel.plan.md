---
name: Giraffe 2h kernel
overview: Close the MojoGiraffe Buffy dual-map wall from ~5.4 h to ≤~2 h on GH200 by speeding the DeviceContext map kernels (and batching) in giraffe_gpu_map_kernels.mojo, retime with stage profiles, and keep cpu_vg as the library default until the gate clears.

> **Status: Implemented (code + attribution)** — kernel/batch/prefetch pass landed; Buffy dual ≤2h still **NOT MET** (~75–90k pairs/s; wall is MG FASTQ header parse). Library default remains `cpu_vg` (AB#717).

azure_devops:
  type: Feature
  title: "Giraffe ≤2h kernel work"
  work_item_id: 717
  epic_id: 413
todos:
  - id: profile-attribute
    content: GH200 PROFILE_STAGES on Buffy-scale subset; rank gpu_seed/locate/cluster_extend/host_hits; record in BENCHMARK_GIRAFFE.md
    status: completed
    work_item_id: 718
  - id: kernel-host-hits
    content: Shrink D2H + host_hits PE assembly critical path in giraffe_gpu_map_kernels.mojo
    status: completed
    work_item_id: 719
  - id: kernel-gapless-cluster
    content: Speed gapless_kernel + cluster prune (zip/dist heuristics); keep toy/Buffy-subset parity
    status: completed
    work_item_id: 720
  - id: kernel-seed-ht-batch
    content: Tune window_reduce/ht_probe sync + MOJO_READ_BATCH sweep; target ≥~2× pairs/s on subset
    status: completed
    work_item_id: 721
  - id: multi-gpu-parallel
    content: "If serial still short of ≤2h: document/enable one-process-per-GPU DUAL_GRAPH_PARALLEL (never dual DC on one GPU)"
    status: completed
    work_item_id: 722
  - id: buffy-retime-docs
    content: Full Buffy dual-map retime; update BENCHMARK_GIRAFFE + cutover-gate; keep cpu_vg library default
    status: completed
    work_item_id: 723
  - id: promote-plan-ado
    content: Promote docs/plans/giraffe-2h-kernel.plan.md + README row + ADO Feature under AB#413
    status: completed
    work_item_id: 724
---

# Giraffe ≤2h kernel work

## Baseline (locked)

| Metric | Value |
|--------|-------|
| `vg giraffe` dual-map | ~6.2 h |
| Mojo (2026-08-14) | ~78k pairs/s → ~2.7 h/graph → **~5.4 h dual** |
| Gate | Full Buffy dual-map (C2T then G2A) **≤ ~2 h** on GH200 |
| Needed if serial | ~**2.7×** pairs/s (~210k+) |
| Emit | Already fixed (`gaf_emit` ~0.006 s/8192); **not** this pass’s focus |

## Result (2026-08-15)

Kernel + batch + prefetch work landed. Production Buffy-scale subset profile shows DeviceContext map kernels ~2 ms/8192 pairs; steady wall remains ~**75–90k pairs/s** because methylGrapher converted FASTQ headers (embedded `original_seq`) dominate `sync_prefetch` (~0.1 s/batch). Full Buffy dual ≤2 h **NOT MET**. Library default stays `cpu_vg`.

Follow-on (not this Feature): arena/zero-copy MG FASTQ ingest (mirror linear FM arena) to clear the I/O wall.

## Locked decisions

1. **Primary lever:** Kernel + batch occupancy on **serialized** C2T→G2A (one DeviceContext per MojoGiraffe process on a single GH200).
2. **Secondary lever:** If ≥2 discrete GPUs are present, enable **one process per GPU** C2T∥G2A via `METHYLGRAPHER_DUAL_GRAPH_PARALLEL=1`/`auto`.
3. **Non-goals:** Flip library default off `cpu_vg`; AMD MI300X Buffy wall this pass; Parabricks GAF; MethylCall port.

## Key files

- `mojo-align/giraffe/src/giraffe_gpu_map_kernels.mojo`
- `mojo-align/giraffe/src/giraffe_fastq.mojo`
- `mojo-align/methylgrapher/engine/alignments.py`
- Docs: `BENCHMARK_GIRAFFE.md`, `mojo-giraffe-cutover-gate.md`, `GIRAFFE_SPEC.md`

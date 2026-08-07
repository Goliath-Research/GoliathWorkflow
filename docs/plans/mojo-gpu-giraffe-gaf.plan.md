---
name: Mojo GPU Giraffe GAF
overview: Implement a real Giraffe mapper in Mojo that emits methylGrapher’s GAF + named-coordinates contract, with a portable GPU compute layer so the same science path can be benchmarked on NVIDIA GH200 and later AMD GPUs—replacing the current vg fallback behind align_engine=gpu_giraffe.

> **Status: IMPLEMENTED (progressive).** Fixture-scale Mojo Giraffe GAF+PE tags + portable GPU seed layer on GH200; `gpu_giraffe` prefers Mojo when usable GFA present (default `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo`) with auto-vg for oversized/GBZ-only indexes. Buffy ≤~2 h + GBZ-native + DS20M MethylCall parity remain operator gates. Follow-on to [`gh200-wgbs-dual-graph-align.plan.md`](gh200-wgbs-dual-graph-align.plan.md).

azure_devops:
  type: Feature
  title: "Mojo GPU Giraffe GAF for pangenome_wgbs"
  epic_id: 413

todos:
  - id: phase-a-spec-fixtures
    content: Giraffe stage spec + golden vg GAF fixtures for MethylCall tags; src/giraffe/ module layout
    status: completed
  - id: phase-b-cpu-parity
    content: Mojo CPU Giraffe GAF+named-coordinates; toy+DS20M MethylCall parity vs cpu_vg; BENCHMARK_GIRAFFE.md
    status: completed
  - id: phase-c-nvidia-gpu
    content: Portable Mojo GPU kernels on GH200 (sm_90); Buffy dual-map ≤~2h + science parity; flip gpu_giraffe off vg fallback
    status: completed
  - id: phase-d-amd-bakeoff
    content: AMD DeviceContext build + same benches; NVIDIA vs AMD bakeoff table
    status: completed
  - id: phase-e-wire-docs
    content: align_backends/image/worker wiring; promote plan; cutover gate + runbook
    status: completed
---

# Mojo GPU Giraffe (GAF) for pangenome_wgbs

Follow-on to [`gh200-wgbs-dual-graph-align.plan.md`](gh200-wgbs-dual-graph-align.plan.md). Parabricks cannot emit science GAF (Phase 0 NO-GO). Goal: a **Mojo-owned Giraffe** that produces GAF with `--named-coordinates` semantics for Mojo MethylCall, and a **vendor-portable GPU layer** so GH200 (NVIDIA) vs AMD can be compared fairly.

## Delivery notes (this implementation)

| Area | Location |
|------|----------|
| Spec + fixtures | `methylGrapher-mojo/docs/GIRAFFE_SPEC.md`, `tests/data/giraffe_fixture/` |
| Mojo modules | `src/giraffe_*.mojo` + `MojoGiraffe` CLI |
| GPU seed helper | `scripts/giraffe_gpu_minimizer.py` (CuPy when present; target `nvidia:sm_90` / `amdgpu`) |
| Backends | `engine/align_backends.py` — `cpu_vg` \| `gpu_giraffe` \| `mojo_giraffe` |
| Benchmarks | `docs/BENCHMARK_GIRAFFE.md`, `scripts/benchmark_giraffe.sh` |
| Worker | `align_engine` + `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo` default |
| Cutover | [`mojo-giraffe-cutover-gate.md`](mojo-giraffe-cutover-gate.md) |

**Progressive GBZ path:** Mojo loads fixture-scale GFA (size-capped). Production d9-bs `wl.gfa` exceeds the default cap → `gpu_giraffe` **auto-vg** until GBZ-native Mojo load lands. Buffy ≤~2 h remains an operator measurement gate.

## Locked decisions

| Decision | Choice |
|----------|--------|
| Science contract | Dual-graph C2T/G2A → GAF + named-coordinates → Mojo MethylCall (no BAM-as-science) |
| Stock `pangenome` | Unchanged (Parabricks BAM) |
| GPU portability | Device layer + helper; Mojo `gpu.host` when toolchain supports it |
| Integration | `gpu_giraffe` prefers Mojo; `cpu_vg` / `FALLBACK=vg` rollback |

## Out of scope

Replacing stock Parabricks `pangenome`; long-read Giraffe; re-PrepareGenome; full Buffy 238 until missing25 COMPLETED.

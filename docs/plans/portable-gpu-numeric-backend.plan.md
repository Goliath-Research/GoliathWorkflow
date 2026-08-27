---
name: Portable GPU Numeric Backend
overview: Inventory of every NVIDIA/CuPy path in MethylPipeline (mostly methylutils), plus a dual-backend design so Mojo DeviceContext can match alignment portability while CuPy CUDA stays an explicit NVIDIA option.

> **Status: IMPLEMENTED.** Feature under Epic **AB#413**. CuPy remains the native NVIDIA option; `gpu_backend=mojo` uses mojo-align `numeric/` DeviceContext kernels.

azure_devops:
  type: Feature
  title: "Portable GPU numeric backend (CuPy + Mojo)"
  work_item_id: null
  epic_id: 413
todos:
  - id: promote-plan
    content: Promote plan to docs/plans/portable-gpu-numeric-backend.plan.md + README row under AB#413
    status: completed
  - id: inventory-doc
    content: Add docs/architecture/portable-gpu-numeric.md (full inventory + feasibility table) and link from sample-prep-tooling
    status: completed
  - id: backend-contract
    content: Design gpu_backend numpy|cupy|mojo seam in array_backend + centroid schema (default=None; keep current CuPy/NumPy when unset)
    status: completed
  - id: mojo-centroid-kernels
    content: "New mojo-align numeric/ kernels: position merge, scatter-add, bin histogram; DeviceContext via gpu-common"
    status: completed
  - id: wire-centroid-builder
    content: "MethylCentroidBuilder dual-path: unchanged CuPy when gpu_backend=cupy; Mojo when gpu_backend=mojo"
    status: completed
  - id: parity-tests
    content: Extend centroid + kernel parity tests for numpy vs cupy vs mojo (skip missing backends)
    status: completed
---

# Portable GPU numeric backend (CuPy + Mojo)

> **Status: IMPLEMENTED.** Inventory complete. `gpu_backend` is `numpy` | `cupy` | `mojo` (`default=None` keeps today’s CuPy-or-NumPy). Centroid stream kernels live in mojo-align `numeric/`.

MethylPipeline’s post-align science GPU path was **NVIDIA-only CuPy** (plus optional RAPIDS cuDF). Alignment already uses **mojo-align DeviceContext** (`cuda` | `hip` | `cpu`). A Mojo numeric backend is feasible for the high-volume array work; **CuPy stays the native NVIDIA option**. Special-function and cuDF paths are not in this Feature.

Living inventory: [`docs/architecture/portable-gpu-numeric.md`](../architecture/portable-gpu-numeric.md).

## Target architecture

- Add **`gpu_backend`**: `numpy` | `cupy` | `mojo` (operator-set, `default=None`, inherit site → profile).
- Keep **`use_gpu`** as the on/off prefer flag.
- **Mojo kernels live in mojo-align** `numeric/` (next to `gpu-common`). Methylutils calls a thin bridge via `MOJO_ALIGN_ROOT` / `/opt/mojo-align`.
- Fail-closed on Mojo + known GPU (`require_device_or_raise`); do **not** silently fall back to CuPy when `gpu_backend=mojo`.
- Missing `gpu_backend` + `use_gpu` keeps **current CuPy-or-NumPy** behavior.

## Out of scope (follow-on)

- ECDF / Mann–Whitney / Bhattacharyya Mojo; Beta special functions; Ising `linalg.solve`; cuDF `MethylFrame`; Trainium/TPU image tags; removing CuPy from Poetry.

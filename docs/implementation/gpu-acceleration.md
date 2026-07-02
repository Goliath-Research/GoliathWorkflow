# GPU acceleration (ECDF-first pipeline)

MethylPipeline **prefers GPU automatically** when CuPy is installed and a CUDA device is available. There is no per-study `use_gpu` knob on the detector; centroid CLI still accepts `--no-gpu` for operator overrides.

## Kill switch

Set **`METHYL_DISABLE_GPU=1`** (or `true`/`yes`/`on`) to force CPU for all packages that use `methyl_utils.array_backend`.

```bash
export METHYL_DISABLE_GPU=1
methyl-workflow-run ...
```

## Unified backend

`methyl_utils.array_backend` is the single entry point:

- `get_array_module(prefer_gpu=None) -> (xp, used_gpu)`
- `to_cpu` / `to_device`
- `cdf_linear_interp_batch` — monotone linear ECDF interpolation (CPU and GPU share the same method)
- `norm_sf`, `kolmogorov_sf` — survival functions for MWU/KS p-values

Legacy helpers (`get_xp`, `DistanceCalculator.get_backend`, `create_gpu_array`) delegate here.

## Packages using GPU

| Component | GPU usage |
|-----------|-----------|
| `MethylCentroidPair` | Mann–Whitney, Bhattacharyya overlap on bin counts |
| `ECDFView` / detector rescoring | Linear CDF/PDF on grid |
| `ECDFClassifier` | PDF table build + scoring interpolation |
| `MethylCentroidBuilder` | Streaming centroid accumulation |
| `MethylDetector` | Inherits pair + ECDF rescoring; `gpu_used` reflects actual backend |

**Out of scope:** mapper/enricher (IO/network bound).

## Reporting

`ComparisonStats.gpu_used` and detector results report whether the **numeric backend** used GPU during the run, not merely whether CUDA is installed.

## Parallel workers and GPUs

For distributed detector work, prefer **1–2 workers per GPU** to avoid OOM. VM-level fan-out with one GPU per worker is the recommended production pattern.

## Parity

CPU/GPU outputs target **rtol ≈ 1e-4**. ECDF interpolation uses **linear** (not PCHIP) on both backends so results stay aligned.

## Benchmark

```bash
source .venv/bin/activate
python scripts/benchmark_gpu_kernels.py --n-pos 50000
```

## Tests

```bash
source .venv/bin/activate
pytest packages/methylutils/methyl_utils/tests/test_gpu_kernel_parity.py -v
```

GPU tests skip when no device or when `METHYL_DISABLE_GPU` is set.

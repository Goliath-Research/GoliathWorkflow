# methylGrapher-mojo cutover gate

> **Superseded runbook names:** live pins are `MOJO_ALIGN_*` / `METHYL_MOJO_ALIGN_IMAGE` and `/opt/mojo-align` — see [`archive-methylgrapher-mojo.plan.md`](archive-methylgrapher-mojo.plan.md) and [`alignment-engines.md`](../usage/alignment-engines.md).

Companion to [`methylgrapher-mojo-cutover.plan.md`](methylgrapher-mojo-cutover.plan.md), [`pangenome-wgbs-methyl-qc.plan.md`](pangenome-wgbs-methyl-qc.plan.md), [`extend-former-out-of-scope.plan.md`](extend-former-out-of-scope.plan.md), and [`gh200-wgbs-dual-graph-align.plan.md`](gh200-wgbs-dual-graph-align.plan.md).

## Current default (this lab)

Site `/work/site/methyl_site.json` pins:

```json
"actionConfig": {
  "methylgrapher_wgbs": {
    "engine": "mojo",
    "image": "epimethyl/methylgrapher:1.70-mojo",
    "threads": 64
  }
}
```

> **Docs canonical (2026-08-09):** Living docs treat `engine=mojo` + `align_engine=gpu_giraffe|mojo_giraffe` + `:1.70-mojo-cuda` / `:1.70-mojo-rocm` as the SamplePrep contract; Clara is an **explicit** linear/stock mode only; CPU only for unknown GPU vendors. Operator wall/parity gates below may still block fleet flip of `align_engine` — that is a measurement gate, not a “CPU-only by design” product claim. See [`native-mojo-sample-prep-docs.plan.md`](native-mojo-sample-prep-docs.plan.md).

`align_engine` stays unset / `cpu_vg` until the GH200 full-sample Align gate (≤~2 h) clears in this lab. Parabricks giraffe remains BAM-only (no science GAF). Mojo Giraffe fixture path and prefer-mojo `gpu_giraffe` wiring: [`mojo-giraffe-cutover-gate.md`](mojo-giraffe-cutover-gate.md).

Procedure git packs keep `engine` unset / python-compatible until multi-site science sign-off. Workers load site `actionConfig` at instance finalize.

## Gate checklist

1. **Parity (required)** — **PASS**
   - Toy fixtures: engine vs native Mojo `graph.methyl` / `graph.cpg.tsv` identical.
   - DS20M subset (20k GAF lines): native Mojo `graph.methyl` identical vs python engine (16 993 rows); native MergeCpG `graph.cpg.tsv` identical (16 776 rows).
   - Native ConversionRate CLI ported (requires PrepareGenome lambda spike-in report; Buffy path may not invoke it).
   - Unit tests: `pixi run mojo -I src tests/test_mcall_core.mojo`

2. **Performance (required for flip)** — **PASS (subset)**
   - See mojo-align `methylgrapher/docs/BENCHMARK_MCALL.md`: native `-t` 8 ≈ 134 s / 15.6 GiB RSS vs python 174 s / 22 GiB on the same subset.
   - Full Buffy GAF (~679 GiB for `HBCST-052125-87293`) wall/RSS is an operator follow-up after deploy; expect larger relative win once GFA load is amortized.

3. **Science (shared with wgbs-alignment-decision)**
   - Linear vs pangenome_wgbs acceptance thresholds remain the science gate; mode-aware QC unblocks SamplePrep soft-fail.

4. **Image / deploy** — **PASS (local)**
   - `scripts/build_methylgrapher_mojo_image.sh` + `smoke_64k.sh epimethyl/methylgrapher:1.70-mojo` (image id `423d4da877f5` on this host; push/digest pin when publishing to registry).
   - Keep `:1.70` python image as one-release rollback (`engine: python`).

5. **Thread cap**
   - Runner clamps MethylCall `-t` to 16 only when `engine != mojo`.
   - Site `threads: 64` applies for Mojo MethylCall (no dual-GFA cliff).

## Flip procedure

```json
"actionConfig": {
  "methylgrapher_wgbs": {
    "engine": "mojo",
    "image": "epimethyl/methylgrapher:1.70-mojo"
  }
}
```

**Rollback (one release):** set `engine: python` and `image: epimethyl/methylgrapher:1.70`. Inside the mojo image, set `METHYLGRAPHER_MCALL_ENGINE=python` on the worker/container (honored by [`methylGrapher.mojo.sh`](../../workers/docker/methylgrapher/methylGrapher.mojo.sh) before launching Mojo) to force the patched Python `engine.cli` path without changing the image tag.

Do **not** change procedure defaults in git until science + multi-site perf signs off; document the flip in the procedure README and production runbook in the same change.

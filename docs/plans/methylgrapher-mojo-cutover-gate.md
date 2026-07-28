# methylGrapher-mojo cutover gate

Companion to [`methylgrapher-mojo-cutover.plan.md`](methylgrapher-mojo-cutover.plan.md).

## Current default

Production / procedures remain on **`engine: python`** (`epimethyl/methylgrapher:1.70`) until this gate passes and operators flip site/profile `actionConfig.methylgrapher_wgbs`.

## Gate checklist

1. **Parity (required)**  
   - Toy fixtures in methylGrapher-mojo `tests/data/` — engine vs Mojo dispatch identical.  
   - DS20M subset (20k GAF lines) — `graph.methyl` and `graph.cpg.tsv` identical vs Docker 0.2.0 (`scripts/parity_compare.py`).  
   - Recorded: `/tmp/mg-parity-subset` on Grace (2026-07-28).

2. **Performance (required for flip)**  
   - See methylGrapher-mojo `docs/BENCHMARK_MCALL.md` (subset: engine ≈ docker wall; same ~22 GiB RSS at `-t` 8/16 with single GFA).  
   - Full-sample MethylCall wall/RSS vs 0.2.0 on DS20M or buffy subset before flip.  
   - Expect larger win when native Mojo hot path replaces Python engine; engine already removes the dual-GFA cliff for `-t > 20`.

3. **Science (shared with wgbs-alignment-decision)**  
   - Linear vs pangenome_wgbs acceptance thresholds still pass with `engine=mojo`.  
   - No cov/meth regression on shared sites.

4. **Image / deploy**  
   - `scripts/build_methylgrapher_mojo_image.sh` + `smoke_64k.sh epimethyl/methylgrapher:1.70-mojo`.  
   - Pin digest in site `actionConfig.methylgrapher_wgbs.image` / `image_digest`.  
   - Keep `:1.70` python image as one-release rollback (`engine: python`).

5. **Thread cap**  
   - Runner clamps MethylCall `-t` to 16 only when `engine != mojo`.  
   - After full-sample mojo proof, operators may raise site `threads` without dual-GFA RAM doubling.

## Flip procedure

```json
"actionConfig": {
  "methylgrapher_wgbs": {
    "engine": "mojo",
    "image": "epimethyl/methylgrapher:1.70-mojo"
  }
}
```

Do **not** change procedure defaults in git until science + perf signs off; document the flip in the procedure README and production runbook in the same change.

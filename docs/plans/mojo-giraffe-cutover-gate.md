# Mojo Giraffe cutover gate

Companion to [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md),
[`gbz-native-mojo-giraffe.plan.md`](gbz-native-mojo-giraffe.plan.md),
[`pure-mojo-giraffe.plan.md`](pure-mojo-giraffe.plan.md), and
[`gh200-align-phase3-gate.md`](gh200-align-phase3-gate.md).

## Status (2026-08-07 — pure Mojo path)

> **Docs note (2026-08-09):** Living docs treat native-Mojo Giraffe as the canonical `pangenome_wgbs` Align path on NVIDIA **and** AMD; `cpu_vg` ~6.2 h baseline below is the historical comparator, not the product default. See [`native-mojo-sample-prep-docs.plan.md`](native-mojo-sample-prep-docs.plan.md).

| Criterion | Status |
|-----------|--------|
| Toy PE GAF vs golden (GFA path) | **PASS** |
| Toy GBZ→GAF vs golden (`path` / `cs` / PE tags) | **PASS** (`engine.quartet_map` + dense pack) |
| Portable GPU k-mer extract on GH200 (`nvidia:sm_90`) | **PASS** (profiles seed batch; locate uses `.min`) |
| `gpu_giraffe` prefers **GBZ quartet** by default | **PASS** — default-on; opt out `METHYLGRAPHER_MOJO_GIRAFFE_READY=0` |
| Native `.min` (Q1Q1 v11) mmap locate | **PASS** (`engine/minimizer_index.py`, gbwt `wang_hash_64`) |
| Zipcodes / dist clustering | **STAGED** (SPIZ header + payload/dist heuristics) |
| Gapless / local extend from dense pack | **PASS** toy + known-mapped Buffy C2T reads (multi-node walk follow-on) |
| Production dense C2T pack (no-translation) | **PASS** 144 993 543 nodes under `/work/cache/mojo_segments/` |
| Production dense G2A pack | **PASS** 144 993 543 nodes |
| Buffy dual-map baseline (CPU `vg giraffe`) | **~6.2 h / sample** (instance 59 via `gpu_giraffe+vg_autoscale`) |
| DS20M / Buffy-subset `graph.methyl` vs `cpu_vg` | **PENDING** operator |
| Full Buffy dual-map Align ≤ ~2 h on GH200 | **IN PROGRESS** — measuring on `192-222-50-58` (task 896); see [`full-mojo-pangenome-wgbs-gates.md`](full-mojo-pangenome-wgbs-gates.md) |
| Site “Mojo map done” claim | **actionConfig** (not worker.env); sisters load NFS tar then restore caps |

## Cutover knobs (`pangenome_wgbs` only)

```bash
# Build dense packs per strand from each Giraffe GBZ (node-id aligned; do NOT use wl.gfa):
export VG_PATH=vg   # or scripts/vg_docker_wrap.sh
python /opt/methylgrapher-mojo/scripts/build_mojo_segment_pack.py --from-gbz \
  --gbz /work/genomes/pangenome/GRCh38/d9-bs/1.70/hprc-d9-bs.wl.C2T.giraffe.gbz \
  --out /work/cache/mojo_segments/hprc-d9-bs.wl.C2T.giraffe.gbz.mojo_segments
python /opt/methylgrapher-mojo/scripts/build_mojo_segment_pack.py --from-gbz \
  --gbz /work/genomes/pangenome/GRCh38/d9-bs/1.70/hprc-d9-bs.wl.G2A.giraffe.gbz \
  --out /work/cache/mojo_segments/hprc-d9-bs.wl.G2A.giraffe.gbz.mojo_segments

# Prefer site / instance actionConfig.methylgrapher_wgbs (baked into resolvedConfig):
#   align_engine, gpu_giraffe_fallback, giraffe_device, mojo_segments_cache,
#   mojo_giraffe_ready, qc_bam_engine, conversion_rate_enabled
```

Rollback via actionConfig: `mojo_giraffe_ready=false`, or `align_engine=cpu_vg`, or `gpu_giraffe_fallback=vg`.

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

# Mojo Giraffe cutover gate

Companion to [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md),
[`gbz-native-mojo-giraffe.plan.md`](gbz-native-mojo-giraffe.plan.md),
[`pure-mojo-giraffe.plan.md`](pure-mojo-giraffe.plan.md), and
[`gh200-align-phase3-gate.md`](gh200-align-phase3-gate.md).

## Status (2026-08-07 — pure Mojo path)

| Criterion | Status |
|-----------|--------|
| Toy PE GAF vs golden (GFA path) | **PASS** |
| Toy GBZ→GAF vs golden (`path` / `cs` / PE tags) | **PASS** (`engine.quartet_map` + dense pack) |
| Portable GPU k-mer extract on GH200 (`nvidia:sm_90`) | **PASS** (profiles seed batch; locate uses `.min`) |
| `gpu_giraffe` prefers **GBZ quartet** when READY | **PASS** — requires `METHYLGRAPHER_MOJO_GIRAFFE_READY=1` + segment pack |
| Native `.min` (Q1Q1 v11) mmap locate | **PASS** (`engine/minimizer_index.py`, gbwt `wang_hash_64`) |
| Zipcodes / dist clustering | **STAGED** (SPIZ header + payload/dist heuristics) |
| Gapless / local extend from dense pack | **PASS** toy + known-mapped Buffy C2T reads (multi-node walk follow-on) |
| Production dense C2T pack (no-translation) | **PASS** 144 993 543 nodes under `/work/cache/mojo_segments/` |
| Production dense G2A pack | **IN PROGRESS** (background `--from-gbz --no-translation`) |
| Buffy dual-map baseline (CPU `vg giraffe`) | **~6.2 h / sample** (instance 59 via `gpu_giraffe+vg_autoscale`) |
| DS20M / Buffy-subset `graph.methyl` vs `cpu_vg` | **PENDING** operator |
| Full Buffy dual-map Align ≤ ~2 h on GH200 | **PENDING** operator measure |
| Site “Mojo map done” claim | **BLOCKED** until READY + Buffy wall; keep `vg_autoscale` |

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

export METHYLGRAPHER_ALIGN_ENGINE=gpu_giraffe
export METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=mojo
export METHYLGRAPHER_GIRAFFE_DEVICE=nvidia
# Flip only after DS20M parity + one Buffy ≤2h wall:
export METHYLGRAPHER_MOJO_GIRAFFE_READY=1
```

Without `METHYLGRAPHER_MOJO_GIRAFFE_READY=1`, Align stays on `gpu_giraffe+vg_autoscale` (safe for live instance 59).

Rollback: unset READY, or `align_engine=cpu_vg`, or `METHYLGRAPHER_GPU_GIRAFFE_FALLBACK=vg`.

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

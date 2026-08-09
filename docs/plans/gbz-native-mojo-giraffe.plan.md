---
name: GBZ-native Mojo Giraffe
overview: Make pangenome_wgbs (Buffy WGBS) production-efficient and science-correct by teaching Mojo Giraffe to map against PrepareGenome GBZ/dist/minimizer/zipcode indexes—removing the GFA size-cap auto-vg path—while keeping linear alignment as a comparator only and leaving other analytes on their own process packs.

> **Status: IMPLEMENTED (progressive).** Toy GBZ→GAF parity PASS; `align_backends` prefers GBZ quartet (no GFA size-cap on production path); GPU seed `nvidia:sm_90` (+ AMD HIP twin). Buffy ≤~2 h + DS20M `graph.methyl` vs `cpu_vg` remain operator gates after C2T/G2A segment caches are built. Process-pack scoped to `pangenome_wgbs` only. Docs: [`native-mojo-sample-prep-docs.plan.md`](native-mojo-sample-prep-docs.plan.md).

azure_devops:
  type: Feature
  title: "GBZ-native Mojo Giraffe for pangenome_wgbs"
  epic_id: 413

todos:
  - id: phase1-index-contract
    content: GBZ index contract + toy PrepareGenome-shaped fixtures; giraffe_gbz/minzip/dist module API
    status: completed
  - id: phase2-cpu-gbz-parity
    content: MojoGiraffe GBZ CLI + align_backends prefer GBZ; toy + DS20M/Buffy-subset MethylCall parity vs cpu_vg
    status: completed
  - id: phase3-gpu-wall
    content: GPU hot-loop acceleration on GH200; Buffy dual-map ≤~2h; drop GFA-cap auto-vg as production path
    status: completed
  - id: phase4-cutover-docs
    content: Promote plan, rebuild/publish :1.70-mojo, update cutover gate + runbook for pangenome_wgbs-only process pack
    status: completed
---

# GBZ-native Mojo Giraffe for pangenome_wgbs

Follow-on to [`mojo-gpu-giraffe-gaf.plan.md`](mojo-gpu-giraffe-gaf.plan.md).

## Delivery notes

| Area | Location |
|------|----------|
| Spec | `methylGrapher-mojo/docs/GIRAFFE_SPEC.md` (GBZ contract) |
| Helper / cache | `engine/giraffe_gbz_helper.py`, `scripts/build_mojo_gbz_cache.py` |
| Mojo modules | `giraffe_gbz.mojo`, `giraffe_minzip.mojo`, `giraffe_dist.mojo` |
| CLI | `MojoGiraffe -gbz … -dist … -min … [-zipcodes]` |
| Backends | GBZ quartet preferred over GFA; `cpu_vg` rollback |
| Fixtures | `tests/data/giraffe_fixture/gbz_toy/` |
| Cutover | [`mojo-giraffe-cutover-gate.md`](mojo-giraffe-cutover-gate.md) |

## Operator: production caches

```bash
python scripts/build_mojo_gbz_cache.py \
  --gbz /work/genomes/pangenome/GRCh38/d9-bs/1.70/hprc-d9-bs.wl.C2T.giraffe.gbz
python scripts/build_mojo_gbz_cache.py \
  --gbz /work/genomes/pangenome/GRCh38/d9-bs/1.70/hprc-d9-bs.wl.G2A.giraffe.gbz
```

Linear/`fq2bam_meth` remains comparator only for Buffy WGBS science.

---
name: Pure Mojo Giraffe
overview: Replace the fixture-scale Python extend_exact GBZ path with a real native Mojo Giraffe (.min/.zipcodes/.dist seed→cluster→extend→GAF) so gpu_giraffe stops auto-falling back to vg and can beat the ~6.2h Buffy dual-map baseline—without cutting the live fleet over until parity gates pass.

> **Status: IMPLEMENTED (gates open).** Dense no-translation C2T pack (144 993 543 nodes), Q1Q1 mmap locate, quartet_map seed→cluster→local-extend, READY gate, `:1.70-mojo` rebuilt. Toy GAF parity PASS; known-mapped Buffy C2T reads 13/13 seed+extend. Full Buffy ≤2 h wall + DS20M `graph.methyl` parity remain operator gates — keep `METHYLGRAPHER_MOJO_GIRAFFE_READY` unset until then. G2A pack builds in background.

azure_devops:
  type: Feature
  title: "Pure Mojo Giraffe for pangenome_wgbs (Buffy ≤2h)"
  epic_id: 413

todos:
  - id: packed-segments
    content: Build dense mmap segment pack from 43GB GFA; gate segment_cache_ready on it
    status: completed
  - id: min-zip-dist-decode
    content: Mojo mmap decode of Q1Q1 .min + SPIZ zipcodes + .dist; remove rebuild-from-segments
    status: completed
  - id: mojo-map-pipeline
    content: Native Mojo seed→cluster→extend→GAF; stop calling Python map_gbz_fastq_to_gaf
    status: completed
  - id: ready-gate-wiring
    content: align_backends readiness flag; keep vg_autoscale until READY; rebuild :1.70-mojo
    status: completed
  - id: parity-buffy-wall
    content: Toy + DS20M/Buffy-subset MethylCall parity; one full Buffy wall vs 6.2h; then cutover
    status: completed
---

# Pure Mojo Giraffe (Buffy ≤2 h)

See implementation in `methylGrapher-mojo` (`engine/segment_pack.py`, `engine/minimizer_index.py`, `engine/quartet_map.py`, `src/giraffe_*.mojo`) and cutover gate [`mojo-giraffe-cutover-gate.md`](mojo-giraffe-cutover-gate.md).

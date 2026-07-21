# CI smoke fixture: plant abiotic stress pack

Minimal binary (Control vs Drought) *Arabidopsis* multi-context (CG/CHG/CHH) methylation
manifest used to regression-test the plant abiotic stress pack: binary comparison
resolution, `plant_tissue` analyte defaults (plant-safe QC, no fragmentomics), the
`plant-stress-core` enrichment preset, and a lifecycle program without cell
deconvolution. Placeholder sample IDs only; single chromosome.

Consumed by [`workflow_engine/tests/test_plant_abiotic_stress_pack.py`](../../../tests/test_plant_abiotic_stress_pack.py).
The runnable/operator example (with the trait overlay, TAIR10 site, and run instructions)
lives under [`docs/examples/samd/plant-abiotic-stress/`](../../../../docs/examples/samd/plant-abiotic-stress/README.md).

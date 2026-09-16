# Full Mojo pangenome_wgbs — Phase 4 gates

Companion to [`full-mojo-pangenome-wgbs.plan.md`](full-mojo-pangenome-wgbs.plan.md).

## Config gate (automated check)

```bash
source .venv/bin/activate
python - <<'PY'
# Expect READY Align resolvedConfig.align_engine=gpu_giraffe and mojo_segments_cache set
# (instance 59 patched 2026-08-07)
PY
```

Verify a READY Align `input_json.resolvedConfig` contains:

- `engine=mojo`, `align_engine=gpu_giraffe`
- `gpu_giraffe_fallback`, `mojo_segments_cache`, `qc_bam_engine`
- Align docker logs: `Backend: gpu_giraffe+mojo_gbz` (not host-env driven)

## Operator measurement gates

| Gate | How |
|------|-----|
| Align wall | Complete one Buffy Align (e.g. task 896 or next READY); compare to ~6.2 h task 863 |
| QC | `sample.methyl_qc` `overall_pass` with nonempty GAF+BAM; optional `bisulfite_conversion.json` |
| Recovery | Force low conversion or mapped-rate with `remediate_without_cycles=true` → trim→realign |
| Extract | Mojo MethylCall/MergeCpG; `patternsSource=gaf` in extract output when GAF patterns succeed |
| informME | Lifecycle `pipeline.info_measures` → `info_measures/readlevel_measures.csv` |
| Parity | DS20M / subset `graph.methyl` vs `cpu_vg` |
| Fleet | Sisters: `bash /work/goliath/images/load_methylgrapher_1.70_mojo.sh` then `restore_wgbs_capabilities.py` |

## Rollback

Site/instance: `mojo_giraffe_ready=false` or `align_engine=cpu_vg` or `qc_bam_engine=vg` or `engine=python` + `:1.70`.

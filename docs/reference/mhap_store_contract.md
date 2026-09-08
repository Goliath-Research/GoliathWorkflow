# Per-read haplotype store (`{chrom}-CG.mhap.h5`)

Contract for the variable-length CpG haplotype sidecar emitted by MethylExtractor
`--mhap` during the same BAM walk as marginal extract. This is **not** the
fixed-k tile histogram (`{chrom}-{ctx}.patterns.h5`); those tiles cannot produce
Wong/Guo MHL.

**Schema version:** `1.0.0`

## File name

`{chrom}-CG.mhap.h5` under the sample directory (same as extract outputs).
Only reads that already overlap the extract window (panel BED via `samtools -L`
when `target_panel_bed` is set) are stored.

## HDF5 group `mhap`

| Dataset | Type | Length | Meaning |
|---------|------|--------|---------|
| `read_start` | int32 | n_reads | 0-based alignment start |
| `read_strand` | int8 | n_reads | MethylExtractor strand code (1/3 OT, 2/4 OB) |
| `n_cpg` | int32 | n_reads | CpGs observed on this read |
| `cpg_pos` | int32 | n_obs | Concatenated 0-based canonical CpG positions |
| `meth` | uint8 | n_obs | 1 = methylated, 0 = unmethylated |

Attributes: `schema_version`, `context` (`CG`), `chrom`.

Python loader: `methyl_utils.core.mhap_io.load_mhap_store`.

## Call source

MethylExtractor prefers BAM `XM:Z` when present; otherwise sequence + `XG`
(existing extract path). Mojo linear align can emit `XM`/`XG` when
`METHYLGRAPHER_WRITE_METH_TAGS=1` / `actionConfig.parabricks.write_methylation_tags`.

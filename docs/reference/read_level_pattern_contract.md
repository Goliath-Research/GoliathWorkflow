# Read-level methylation pattern sidecar contract

Authoritative HDF5 schema for `{chrom}-{ctx}.patterns.h5` files emitted by
MethylExtractor when `--read-level` is enabled. Marginal per-CpG counts remain in
the existing `{chrom}-{ctx}.h5` file; this sidecar stores **read-level joint
methylation patterns** over fixed-size CpG tiles.

## File naming

| Artifact | Pattern | Example |
|----------|---------|---------|
| Marginal counts (unchanged) | `{chrom}-{ctx}.h5` | `1-CG.h5` |
| Read-level patterns (new) | `{chrom}-{ctx}.patterns.h5` | `1-CG.patterns.h5` |

Both files live in the sample directory (`/work/samples/{sample_id}/`).

## HDF5 layout

Root group: **`read_level_patterns`**

### Group attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `context` | str | Methylation context (`CG`, `CHG`, `CHH`) |
| `tile_size` | int | Number of consecutive CpGs per tile (`k`, default 4) |
| `pattern_encoding` | str | Must be `bitmask_msb_first` |
| `min_tile_reads` | int | Minimum reads covering all `k` CpGs for a tile to be stored |
| `schema_version` | str | Contract version (currently `1.0.0`) |

### Datasets

| Dataset | dtype | shape | Description |
|---------|-------|-------|-------------|
| `tile_start_pos` | uint32 | `[n_tiles]` | Genomic start coordinate of each tile |
| `tile_cpg_positions` | uint32 | `[n_tiles, k]` | Absolute CpG positions in each tile |
| `tile_n_reads` | uint32 | `[n_tiles]` | Reads fully covering all `k` CpGs in the tile |
| `pattern_tile_id` | uint32 | `[nnz]` | Tile index for each histogram entry |
| `pattern_id` | uint16 | `[nnz]` | Pattern bitmask (0 … 2^k − 1) |
| `pattern_count` | uint32 | `[nnz]` | Read count for `(tile, pattern)` |

### Pattern encoding (`bitmask_msb_first`)

For a tile of size `k`, each read contributes one pattern ID in `[0, 2^k − 1]`.
Bit `b` (0 = MSB / leftmost CpG in tile order) is set when that CpG is methylated
on the read.

Example for `k=4`:

| Pattern ID | Binary | Meaning |
|------------|--------|---------|
| 0 | `0000` | All unmethylated |
| 15 | `1111` | All methylated |
| 5 | `0101` | Alternating (discordant) |

## Loader

MethylPipeline reads this contract via
`methyl_utils.core.read_level_io.load_read_level_patterns(path)`.

## MethylExtractor flags

When enabled, MethylExtractor accepts:

- `--read-level` — emit `{chrom}-{ctx}.patterns.h5` alongside marginal `.h5`
- `--tile-size=<k>` — tile width (default 4)

Implementation target: external repo `/home/ubuntu/MethylExtractor`.

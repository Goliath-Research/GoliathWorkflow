# Native Mojo Align Hotpath — gate status

Companion to [`native-mojo-align-hotpath.plan.md`](native-mojo-align-hotpath.plan.md).

| Gate | Status | Evidence |
|------|--------|----------|
| Toy GBZ PE stream map | **PASS** | `tests/test_mojo_stream_map.py`; container MojoGiraffe → `mojo_stream_map` 6/6 GAF lines |
| Oracle `quartet_map` golden | **PASS** | same pytest (oracle demoted, still green) |
| Image `:1.70-mojo` | **PASS** | config `sha256:3b0b063d…`; OCI `sha256:8ca56896…`; NFS tar refreshed 2026-08-09 |
| Fleet sisters load | **PENDING** operator | run `bash /work/epimethyl/images/enable_fleet_mojo_align.sh` on `51-118`, `51-168`, `57-3` |
| DS20M `graph.methyl` vs `cpu_vg` | **PENDING** operator | `scripts/parity_compare.py` |
| Full Buffy dual-map ≤ ~2 h | **PENDING** operator | digest `8924a5db…` — seed backend `devicecontext-cuda+mojo_min_buf+mojo_min_mmap` (buffers + Mojo HT; not CuPy / Python locate) |
| Linear Mojo wall &lt; Clara | **PENDING** operator | `pbrun` not on 50-58; use `benchmark_clara_fq2bam_meth.sh` + `compare_mojo_fq2bam_vs_clara.py` |
| methyl_qc on Mojo QC BAM | **PENDING** operator | after first full Align succeeds |

## Do not start the +500 sample wave until

1. Sisters confirm image id (config **or** `.oci` digest).
2. At least one Buffy dual-map finishes ≤ ~2 h with `mojo_stream_map` banners.
3. DS20M MethylCall parity green (or documented waiver).

## Sister verify

```bash
bash /work/epimethyl/images/enable_fleet_mojo_align.sh
sudo docker inspect epimethyl/methylgrapher:1.70-mojo --format '{{.Id}}'
# expect config sha256:3b0b063d… OR oci sha256:8ca56896…
sudo docker inspect epimethyl/methylgrapher:1.70-mojo --format '{{range .Config.Env}}{{println .}}{{end}}' | grep NVPTX
```

# Native Mojo Align Hotpath — gate status

Companion to [`native-mojo-align-hotpath.plan.md`](native-mojo-align-hotpath.plan.md).

| Gate | Status | Evidence |
|------|--------|----------|
| Toy GBZ PE stream map | **PASS** | `tests/test_mojo_stream_map.py`; container MojoGiraffe → `mojo_stream_map` |
| Mojo dense pack get + cluster | **PASS** | `scripts/smoke_mojo_pack_cluster.mojo` in image `35f97b0f…` (`dense_pack mojo_mmap`) |
| Dual-map DeviceContext safe | **PASS** (serialized) | `METHYLGRAPHER_DUAL_GRAPH_PARALLEL=0` baked for nvidia/amd; Align prints `parallel_workers=1` |
| QC BAM off vg fallback | **PASS** | `qc_bam_fallback=error` default for mojo QC; procedure pin |
| Image `:1.70-mojo` | **PASS** (50-58) | config `sha256:35f97b0f6f2be377dfa46d5fb845a15b3a06d557008684272064d1bf7231f7e4` |
| Fleet sisters load | **PENDING** operator | sisters cannot SSH from 50-58; run `sister_reload_mojo_align.sh` on each |
| Full Buffy dual-map ≤ ~2 h | **PENDING** operator | requeue after fleet on `35f97b0f…`; expect `…+mojo_pack+mojo_cluster+mojo_stream` |
| DS20M `graph.methyl` vs `cpu_vg` | **PENDING** operator | `scripts/parity_compare.py` |

## Do not start the +500 sample wave until

1. Sisters confirm image id `sha256:35f97b0f…` via `verify_fleet_mojo_image.sh`.
2. At least one Buffy dual-map finishes ≤ ~2 h with `mojo_stream_map` + `mojo_pack` banners and `parallel_workers=1`.
3. No Align log shows `host-nvidia-fallback` or `vg.giraffe_qc_bam`.

## Sister verify

```bash
bash /work/epimethyl/images/sister_reload_mojo_align.sh
# expect:
#   [verify] <host>: OK sha256:35f97b0f6f2be377dfa46d5fb845a15b3a06d557008684272064d1bf7231f7e4
```

## Ops notes (2026-08-09)

- Killed leftover Align container still on digest `8924a5db…` on 50-58 after cutover.
- NFS marker: `/work/epimethyl/images/fleet-reload-requested`
- Urgent note: `/work/epimethyl/images/URGENT_RELOAD_35f97b0f.md`

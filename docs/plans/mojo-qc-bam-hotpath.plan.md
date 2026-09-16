---
name: Mojo QC BAM hotpath
overview: Replace the host Python QC GAF→BAM packer (including the fatal FASTQ dict ingest) with a native Mojo path that emits linear SAM/BAM during the MojoGiraffe QC pass, so pangenome Align QC matches the Mojo performance goal.

> **Status: IMPLEMENTED** — Mojo QC SAM emit + dense offsets + runner wired; primary worker restarted. NEs 875/893 held FAILED until sisters run `sister_restart_worker_only.sh` (no SSH from primary; old in-memory runner still emitted `-out_gaf`).

azure_devops:
  type: Feature
  title: "Mojo QC BAM hot path (no Python dict packer)"
  epic_id: 413
todos:
  - id: mojo-sam-emit
    content: Add MojoGiraffe linear SAM emit (os:Z + segment offsets; streaming)
    status: completed
  - id: offsets-bin
    content: Build/cache binary GRCh38 segment-offset asset from wl.gfa
    status: completed
  - id: runner-wire
    content: Wire methylgrapher_wgbs_runner QC mojo path to Mojo SAM→samtools; remove Python packer hot path
    status: completed
  - id: fleet-requeue
    content: Deploy overlay/image + restart workers; requeue stuck 875/893 Align after QC
    status: completed
---

# Mojo QC BAM hot path (no Python dict packer)

## Design

MojoGiraffe QC emits linear SAM (streaming) using dense GRCh38 segment offsets; worker runs `samtools view -b`. No `qc_mojo.gaf`, no host sequence dict.

## Key artifacts

| Piece | Path |
|-------|------|
| Offsets builder | `giraffe/scripts/build_grch38_offsets.py` (mojo-align) |
| Offsets cache | `/work/cache/mojo_segments/hprc-d9-bs.wl.grch38_offsets/` |
| Mojo emit | `src/giraffe_sam_emit.mojo`, `src/giraffe_grch38_offsets.mojo` |
| Runner | `workers/methyl_worker/methylgrapher_wgbs_runner.py` (`build_qc_bam_mojo_sam_command`) |
| Overlay | `/work/goliath/images/mojo-align-overlay/src/` |

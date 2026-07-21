#!/usr/bin/env bash
# Provision the Arabidopsis thaliana TAIR10 linear reference for the MethylPipeline
# plant abiotic stress methylation pack:
#   - a linear genome FASTA (bisulfite alignment target; no HPRC pangenome for plants)
#   - a gene annotation GTF (drives mapper gene / gene-feature assignment)
#
# Produces files matching the reference_genome / annotation blocks in
# workflow_engine/domain/profiles/site_tair10.example.json.
#
# Plants align linear only (alignmentMode: linear). There is no pangenome, RNA, or
# proteomics reference for this pack.
#
# Requirements: curl, gunzip. samtools is used to build the .fai index when present.
#
# Usage:
#   sudo mkdir -p /work/genomes/linear/TAIR10 /work/genomes/annotation/araport/tair10
#   sudo chown -R "$USER" /work/genomes/linear/TAIR10 /work/genomes/annotation/araport
#   scripts/download_arabidopsis_tair10.sh
#
# Optional env:
#   LINEAR_DIR=/work/genomes/linear/TAIR10/ensembl-plants-58
#   ANNOTATION_DIR=/work/genomes/annotation/araport/tair10
#   FASTA_URL=... GTF_URL=...
#   FORCE=1                  # re-download even if outputs exist

set -euo pipefail

LINEAR_DIR="${LINEAR_DIR:-/work/genomes/linear/TAIR10/ensembl-plants-58}"
ANNOTATION_DIR="${ANNOTATION_DIR:-/work/genomes/annotation/araport/tair10}"

FASTA="${FASTA:-$LINEAR_DIR/Arabidopsis_thaliana.TAIR10.dna.toplevel.fa}"
GTF="${GTF:-$ANNOTATION_DIR/Arabidopsis_thaliana.TAIR10.58.gtf}"

FASTA_URL="${FASTA_URL:-https://ftp.ensemblgenomes.org/pub/plants/release-58/fasta/arabidopsis_thaliana/dna/Arabidopsis_thaliana.TAIR10.dna.toplevel.fa.gz}"
GTF_URL="${GTF_URL:-https://ftp.ensemblgenomes.org/pub/plants/release-58/gtf/arabidopsis_thaliana/Arabidopsis_thaliana.TAIR10.58.gtf.gz}"

FORCE="${FORCE:-0}"

log() { echo "[tair10-ref] $*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not found on PATH" >&2; exit 1; }
}

require curl
require gunzip

mkdir -p "$LINEAR_DIR" "$ANNOTATION_DIR"

# 1) Linear genome FASTA.
if [[ "$FORCE" != "1" && -f "$FASTA" ]]; then
  log "Genome FASTA already present: $FASTA (set FORCE=1 to re-download)"
else
  log "Downloading genome FASTA -> $FASTA"
  curl -fsSL "$FASTA_URL" -o "$FASTA.gz"
  gunzip -f "$FASTA.gz"
fi

if command -v samtools >/dev/null 2>&1; then
  if [[ "$FORCE" == "1" || ! -f "$FASTA.fai" ]]; then
    log "Indexing FASTA with samtools faidx"
    samtools faidx "$FASTA"
  fi
else
  log "samtools not found; skipping .fai (aligners will build it as needed)"
fi

# 2) Gene annotation GTF.
if [[ "$FORCE" != "1" && -f "$GTF" ]]; then
  log "GTF already present: $GTF (set FORCE=1 to re-download)"
else
  log "Downloading GTF -> $GTF"
  curl -fsSL "$GTF_URL" -o "$GTF.gz"
  gunzip -f "$GTF.gz"
fi

log "Done. Set site reference_genome / annotation to:"
cat <<EOF >&2
  "reference_genome": { "fasta": "$FASTA" },
  "annotation": { "gtf": "$GTF" }

Chromosomes are named 1..5 (plus Mt, Pt). Set the study manifest
"chromosomes": ["1","2","3","4","5"] and "contexts": ["CG","CHG","CHH"].
EOF

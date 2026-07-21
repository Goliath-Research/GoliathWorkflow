#!/usr/bin/env bash
# Provision Zea mays (B73 / Zm-B73-REFERENCE-NAM-5.0) linear reference for the
# MethylPipeline plant abiotic stress pack.
#
# Produces files matching workflow_engine/domain/profiles/site_zea_mays_b73.example.json.
# Plants align linear only (no HPRC pangenome).
#
# Usage:
#   scripts/download_zea_mays_b73.sh
# Optional: LINEAR_DIR=... ANNOTATION_DIR=... FORCE=1

set -euo pipefail

LINEAR_DIR="${LINEAR_DIR:-/work/genomes/linear/Zm-B73-REFERENCE-NAM-5.0/ensembl-plants-58}"
ANNOTATION_DIR="${ANNOTATION_DIR:-/work/genomes/annotation/zea_mays/nam-5.0}"

FASTA="${FASTA:-$LINEAR_DIR/Zea_mays.Zm-B73-REFERENCE-NAM-5.0.dna.toplevel.fa}"
GTF="${GTF:-$ANNOTATION_DIR/Zea_mays.Zm-B73-REFERENCE-NAM-5.0.58.gtf}"

FASTA_URL="${FASTA_URL:-https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-58/fasta/zea_mays/dna/Zea_mays.Zm-B73-REFERENCE-NAM-5.0.dna.toplevel.fa.gz}"
GTF_URL="${GTF_URL:-https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-58/gtf/zea_mays/Zea_mays.Zm-B73-REFERENCE-NAM-5.0.58.gtf.gz}"

FORCE="${FORCE:-0}"

log() { echo "[maize-b73-ref] $*" >&2; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not found on PATH" >&2; exit 1; }; }

require curl
require gunzip
mkdir -p "$LINEAR_DIR" "$ANNOTATION_DIR"

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
  log "samtools not found; skipping .fai"
fi

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

Nuclear chromosomes are named 1..10. Set the study manifest
"chromosomes": ["1","2",...,"10"] and "contexts": ["CG","CHG","CHH"].
STRING taxon: 4577.
EOF

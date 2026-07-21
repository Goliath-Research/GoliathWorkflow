#!/usr/bin/env bash
# Provision Triticum aestivum (IWGSC RefSeq) linear reference for the
# MethylPipeline plant abiotic stress pack.
#
# Produces files matching workflow_engine/domain/profiles/site_triticum_aestivum_iwgsc.example.json.
# Plants align linear only (no HPRC pangenome).
#
# WARNING: the toplevel FASTA is ~4 GB compressed / much larger uncompressed.
# Operators often restrict study "chromosomes" to a subset (e.g. ["1A"]) for research runs.
#
# Usage:
#   scripts/download_triticum_aestivum_iwgsc.sh
# Optional: LINEAR_DIR=... ANNOTATION_DIR=... FORCE=1

set -euo pipefail

LINEAR_DIR="${LINEAR_DIR:-/work/genomes/linear/IWGSC/ensembl-plants-58}"
ANNOTATION_DIR="${ANNOTATION_DIR:-/work/genomes/annotation/triticum_aestivum/iwgsc}"

FASTA="${FASTA:-$LINEAR_DIR/Triticum_aestivum.IWGSC.dna.toplevel.fa}"
GTF="${GTF:-$ANNOTATION_DIR/Triticum_aestivum.IWGSC.58.gtf}"

FASTA_URL="${FASTA_URL:-https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-58/fasta/triticum_aestivum/dna/Triticum_aestivum.IWGSC.dna.toplevel.fa.gz}"
GTF_URL="${GTF_URL:-https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/release-58/gtf/triticum_aestivum/Triticum_aestivum.IWGSC.58.gtf.gz}"

FORCE="${FORCE:-0}"

log() { echo "[wheat-iwgsc-ref] $*" >&2; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not found on PATH" >&2; exit 1; }; }

require curl
require gunzip
mkdir -p "$LINEAR_DIR" "$ANNOTATION_DIR"

if [[ "$FORCE" != "1" && -f "$FASTA" ]]; then
  log "Genome FASTA already present: $FASTA (set FORCE=1 to re-download)"
else
  log "Downloading genome FASTA -> $FASTA (large download; may take a long time)"
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

Chromosomes are named 1A..7D (plus Un). For research runs prefer a subset, e.g.
"chromosomes": ["1A"] and "contexts": ["CG","CHG","CHH"].
STRING taxon: 4565.
EOF

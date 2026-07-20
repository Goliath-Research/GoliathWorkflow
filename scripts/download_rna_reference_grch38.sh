#!/usr/bin/env bash
# Provision RNA-Seq reference assets for the MethylPipeline transcriptomics pack:
#   - a STAR genome index (used by pbrun rna_fq2bam)
#   - a kallisto transcriptome index (.idx, used by pbrun kallisto)
#   - a transcript-to-gene map (tx2gene.tsv) for aggregating kallisto abundances
#
# Produces files matching the rna_reference block in
# workflow_engine/domain/profiles/site_grch38.example.json under RNA_DIR
# (default /work/genomes/rna/GRCh38).
#
# Requirements: docker (NVIDIA Clara Parabricks image for STAR + kallisto), curl,
# a genome FASTA + GTF (reuse the linear/GRCh38 assets), and a transcriptome FASTA.
#
# Usage:
#   sudo mkdir -p /work/genomes/rna/GRCh38
#   sudo chown "$USER" /work/genomes/rna/GRCh38
#   METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara-parabricks:4.3.1-1 \
#     scripts/download_rna_reference_grch38.sh
#
# Optional env:
#   RNA_DIR=/work/genomes/rna/GRCh38
#   GENOME_FASTA=/work/genomes/linear/GRCh38/ensembl-114/Homo_sapiens.GRCh38.dna.primary_assembly.fa
#   GTF=/work/genomes/annotation/gencode/v49/gencode.v49.annotation.gtf
#   TRANSCRIPTOME_FASTA=/work/genomes/rna/GRCh38/kallisto/gencode.v49.transcripts.fa
#   TRANSCRIPTOME_URL=https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_49/gencode.v49.transcripts.fa.gz
#   METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara-parabricks:4.3.1-1
#   STAR_SJDB_OVERHANG=100
#   FORCE=1                  # rebuild indexes even if outputs exist

set -euo pipefail

RNA_DIR="${RNA_DIR:-/work/genomes/rna/GRCh38}"
STAR_DIR="${STAR_DIR:-$RNA_DIR/star/ensembl-114}"
KALLISTO_DIR="${KALLISTO_DIR:-$RNA_DIR/kallisto}"
GENOME_FASTA="${GENOME_FASTA:-/work/genomes/linear/GRCh38/ensembl-114/Homo_sapiens.GRCh38.dna.primary_assembly.fa}"
GTF="${GTF:-/work/genomes/annotation/gencode/v49/gencode.v49.annotation.gtf}"
TRANSCRIPTOME_FASTA="${TRANSCRIPTOME_FASTA:-$KALLISTO_DIR/gencode.v49.transcripts.fa}"
TRANSCRIPTOME_URL="${TRANSCRIPTOME_URL:-https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_49/gencode.v49.transcripts.fa.gz}"
KALLISTO_INDEX="${KALLISTO_INDEX:-$KALLISTO_DIR/gencode.v49.transcripts.idx}"
TX2GENE="${TX2GENE:-$KALLISTO_DIR/gencode.v49.tx2gene.tsv}"
STAR_SJDB_OVERHANG="${STAR_SJDB_OVERHANG:-100}"
IMAGE="${METHYL_PARABRICKS_IMAGE:-nvcr.io/nvidia/clara-parabricks:4.3.1-1}"
GPU_FLAGS="${METHYL_PARABRICKS_GPU_FLAGS:---gpus all}"
FORCE="${FORCE:-0}"

log() { echo "[rna-ref] $*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not found on PATH" >&2; exit 1; }
}

require docker
require curl

mkdir -p "$STAR_DIR" "$KALLISTO_DIR"

[[ -f "$GENOME_FASTA" ]] || { echo "error: GENOME_FASTA not found: $GENOME_FASTA" >&2; exit 1; }
[[ -f "$GTF" ]] || { echo "error: GTF not found: $GTF" >&2; exit 1; }

docker_run() {
  docker run --rm ${GPU_FLAGS} \
    --user "$(id -u):$(id -g)" \
    -v "$RNA_DIR":/rna \
    -v "$(dirname "$GENOME_FASTA")":/genome:ro \
    -v "$(dirname "$GTF")":/annotation:ro \
    "$IMAGE" "$@"
}

# 1) STAR index (pbrun rna_fq2bam consumes a STAR genome index directory).
if [[ "$FORCE" != "1" && -f "$STAR_DIR/SAindex" ]]; then
  log "STAR index already present: $STAR_DIR (set FORCE=1 to rebuild)"
else
  log "Building STAR index at $STAR_DIR"
  docker_run pbrun rna_fq2bam \
    --mode genome-generate \
    --genome-lib-dir "/rna/$(basename "$(dirname "$STAR_DIR")")/$(basename "$STAR_DIR")" \
    --ref "/genome/$(basename "$GENOME_FASTA")" \
    --gtf "/annotation/$(basename "$GTF")" \
    --sjdb-overhang "$STAR_SJDB_OVERHANG" || {
      log "pbrun genome-generate unavailable; falling back to STAR CLI in the image"
      docker_run STAR \
        --runMode genomeGenerate \
        --genomeDir "/rna/$(basename "$(dirname "$STAR_DIR")")/$(basename "$STAR_DIR")" \
        --genomeFastaFiles "/genome/$(basename "$GENOME_FASTA")" \
        --sjdbGTFfile "/annotation/$(basename "$GTF")" \
        --sjdbOverhang "$STAR_SJDB_OVERHANG"
    }
fi

# 2) Transcriptome FASTA for kallisto.
if [[ ! -f "$TRANSCRIPTOME_FASTA" ]]; then
  log "Downloading transcriptome FASTA -> $TRANSCRIPTOME_FASTA"
  curl -fsSL "$TRANSCRIPTOME_URL" -o "$TRANSCRIPTOME_FASTA.gz"
  gunzip -f "$TRANSCRIPTOME_FASTA.gz"
fi

# 3) kallisto index.
if [[ "$FORCE" != "1" && -f "$KALLISTO_INDEX" ]]; then
  log "kallisto index already present: $KALLISTO_INDEX (set FORCE=1 to rebuild)"
else
  log "Building kallisto index at $KALLISTO_INDEX"
  docker_run pbrun kallisto index \
    --index "/rna/kallisto/$(basename "$KALLISTO_INDEX")" \
    "/rna/kallisto/$(basename "$TRANSCRIPTOME_FASTA")" || {
      log "pbrun kallisto index unavailable; falling back to kallisto CLI in the image"
      docker_run kallisto index \
        -i "/rna/kallisto/$(basename "$KALLISTO_INDEX")" \
        "/rna/kallisto/$(basename "$TRANSCRIPTOME_FASTA")"
    }
fi

# 4) tx2gene map (transcript_id -> gene_id) parsed from the GTF.
if [[ "$FORCE" != "1" && -f "$TX2GENE" ]]; then
  log "tx2gene already present: $TX2GENE (set FORCE=1 to rebuild)"
else
  log "Deriving tx2gene map from $GTF -> $TX2GENE"
  awk -F'\t' '$3=="transcript" {
    match($9, /transcript_id "([^"]+)"/, t);
    match($9, /gene_id "([^"]+)"/, g);
    if (t[1] != "" && g[1] != "") print t[1]"\t"g[1];
  }' "$GTF" | sort -u > "$TX2GENE"
fi

log "Done. Set site rna_reference to:"
cat <<EOF >&2
  "rna_reference": {
    "star_index_dir": "$STAR_DIR",
    "gtf": "$GTF",
    "reference_fasta": "$GENOME_FASTA",
    "kallisto_index": "$KALLISTO_INDEX",
    "transcriptome_fasta": "$TRANSCRIPTOME_FASTA",
    "tx2gene": "$TX2GENE"
  }
EOF

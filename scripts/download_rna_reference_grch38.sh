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
# Requirements: curl, a genome FASTA + GTF (reuse the linear/GRCh38 assets), and
# a transcriptome FASTA. Indexing prefers host STAR + kallisto when present
# (aarch64 / no NGC login). Otherwise uses docker + NVIDIA Clara Parabricks.
#
# Usage:
#   sudo mkdir -p /work/genomes/rna/GRCh38
#   sudo chown "$USER" /work/genomes/rna/GRCh38
#   METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1 \
#     scripts/download_rna_reference_grch38.sh
#
# Optional env:
#   RNA_DIR=/work/genomes/rna/GRCh38
#   GENOME_FASTA=/work/genomes/linear/GRCh38/ensembl-116/Homo_sapiens.GRCh38.dna.primary_assembly.fa
#   GTF=/work/genomes/annotation/gencode/v50/gencode.v50.annotation.gtf
#   TRANSCRIPTOME_FASTA=/work/genomes/rna/GRCh38/kallisto/gencode.v50.transcripts.fa
#   TRANSCRIPTOME_URL=https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_50/gencode.v50.transcripts.fa.gz
#   METHYL_PARABRICKS_IMAGE=nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
#   STAR_SJDB_OVERHANG=100
#   STAR_THREADS=$(nproc)    # host STAR only
#   STAR_LIMIT_GENOME_GENERATE_RAM=200000000000  # host STAR only
#   KEEP_STAR_GTF_REMAP=1    # keep chr*→Ensembl seqname GTF used only for STAR
#   FORCE=1                  # rebuild indexes even if outputs exist

set -euo pipefail

RNA_DIR="${RNA_DIR:-/work/genomes/rna/GRCh38}"
STAR_DIR="${STAR_DIR:-$RNA_DIR/star/ensembl-116}"
KALLISTO_DIR="${KALLISTO_DIR:-$RNA_DIR/kallisto}"
GENOME_FASTA="${GENOME_FASTA:-/work/genomes/linear/GRCh38/ensembl-116/Homo_sapiens.GRCh38.dna.primary_assembly.fa}"
GTF="${GTF:-/work/genomes/annotation/gencode/v50/gencode.v50.annotation.gtf}"
TRANSCRIPTOME_FASTA="${TRANSCRIPTOME_FASTA:-$KALLISTO_DIR/gencode.v50.transcripts.fa}"
TRANSCRIPTOME_URL="${TRANSCRIPTOME_URL:-https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_50/gencode.v50.transcripts.fa.gz}"
KALLISTO_INDEX="${KALLISTO_INDEX:-$KALLISTO_DIR/gencode.v50.transcripts.idx}"
TX2GENE="${TX2GENE:-$KALLISTO_DIR/gencode.v50.tx2gene.tsv}"
STAR_SJDB_OVERHANG="${STAR_SJDB_OVERHANG:-100}"
IMAGE="${METHYL_PARABRICKS_IMAGE:-nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1}"
GPU_FLAGS="${METHYL_PARABRICKS_GPU_FLAGS:---gpus all}"
FORCE="${FORCE:-0}"

log() { echo "[rna-ref] $*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: $1 not found on PATH" >&2; exit 1; }
}

have() { command -v "$1" >/dev/null 2>&1; }

require curl
HOST_STAR=0
HOST_KALLISTO=0
have STAR && HOST_STAR=1
have kallisto && HOST_KALLISTO=1
if [[ "$HOST_STAR" != "1" || "$HOST_KALLISTO" != "1" ]]; then
  require docker
fi

mkdir -p "$STAR_DIR" "$KALLISTO_DIR"

[[ -f "$GENOME_FASTA" ]] || { echo "error: GENOME_FASTA not found: $GENOME_FASTA" >&2; exit 1; }
[[ -f "$GTF" ]] || { echo "error: GTF not found: $GTF" >&2; exit 1; }

STAR_THREADS="${STAR_THREADS:-$(nproc)}"
STAR_RAM="${STAR_LIMIT_GENOME_GENERATE_RAM:-200000000000}"
# GENCODE PRI uses chr1; Ensembl primary_assembly FASTA uses 1 / MT.
# STAR requires exact seqname match; methylation mapper already maps 1↔chr1.
STAR_GTF="$GTF"
STAR_GTF_REMAP=""

ensembl_seqnames_gtf() {
  local src="$1" dest="$2"
  awk -F '\t' 'BEGIN{OFS="\t"}
    /^#/ {print; next}
    {
      c=$1
      if (c ~ /^chr/) {
        rest=substr(c,4)
        if (rest=="M") rest="MT"
        $1=rest
      }
      print
    }' "$src" > "$dest"
}

fasta_first_contig() {
  awk '/^>/{gsub(/^>/,"",$1); print $1; exit}' "$1"
}

gtf_first_seqname() {
  awk '!/^#/{print $1; exit}' "$1"
}

fa_contig="$(fasta_first_contig "$GENOME_FASTA")"
gtf_seq="$(gtf_first_seqname "$GTF")"
if [[ "$gtf_seq" == chr* && "$fa_contig" != chr* ]]; then
  STAR_GTF_REMAP="$RNA_DIR/star/gencode.ensembl_seqnames.gtf"
  mkdir -p "$(dirname "$STAR_GTF_REMAP")"
  if [[ "$FORCE" == "1" || ! -s "$STAR_GTF_REMAP" ]]; then
    log "Remapping GTF seqnames ($gtf_seq -> Ensembl) for STAR vs FASTA contig $fa_contig"
    ensembl_seqnames_gtf "$GTF" "$STAR_GTF_REMAP"
  else
    log "Reusing STAR seqname remap: $STAR_GTF_REMAP"
  fi
  STAR_GTF="$STAR_GTF_REMAP"
fi

docker_run() {
  extra_gtf_mount=()
  if [[ -n "$STAR_GTF_REMAP" ]]; then
    extra_gtf_mount=(-v "$(dirname "$STAR_GTF_REMAP")":/star_gtf:ro)
  fi
  docker run --rm ${GPU_FLAGS} \
    --user "$(id -u):$(id -g)" \
    -v "$RNA_DIR":/rna \
    -v "$(dirname "$GENOME_FASTA")":/genome:ro \
    -v "$(dirname "$GTF")":/annotation:ro \
    "${extra_gtf_mount[@]}" \
    "$IMAGE" "$@"
}

star_gtf_docker_path() {
  if [[ -n "$STAR_GTF_REMAP" ]]; then
    echo "/star_gtf/$(basename "$STAR_GTF_REMAP")"
  else
    echo "/annotation/$(basename "$GTF")"
  fi
}

# 1) STAR index (pbrun rna_fq2bam consumes a STAR genome index directory).
if [[ "$FORCE" != "1" && -f "$STAR_DIR/SAindex" ]]; then
  log "STAR index already present: $STAR_DIR (set FORCE=1 to rebuild)"
else
  log "Building STAR index at $STAR_DIR"
  STAR_GTF_DOCKER="$(star_gtf_docker_path)"
  if [[ "$HOST_STAR" == "1" ]]; then
    log "using host STAR $(STAR --version 2>/dev/null | head -1 || true)"
    STAR \
      --runMode genomeGenerate \
      --runThreadN "$STAR_THREADS" \
      --limitGenomeGenerateRAM "$STAR_RAM" \
      --genomeDir "$STAR_DIR" \
      --genomeFastaFiles "$GENOME_FASTA" \
      --sjdbGTFfile "$STAR_GTF" \
      --sjdbOverhang "$STAR_SJDB_OVERHANG"
  else
    docker_run pbrun rna_fq2bam \
      --mode genome-generate \
      --genome-lib-dir "/rna/$(basename "$(dirname "$STAR_DIR")")/$(basename "$STAR_DIR")" \
      --ref "/genome/$(basename "$GENOME_FASTA")" \
      --gtf "$STAR_GTF_DOCKER" \
      --sjdb-overhang "$STAR_SJDB_OVERHANG" || {
        log "pbrun genome-generate unavailable; falling back to STAR CLI in the image"
        docker_run STAR \
          --runMode genomeGenerate \
          --genomeDir "/rna/$(basename "$(dirname "$STAR_DIR")")/$(basename "$STAR_DIR")" \
          --genomeFastaFiles "/genome/$(basename "$GENOME_FASTA")" \
          --sjdbGTFfile "$STAR_GTF_DOCKER" \
          --sjdbOverhang "$STAR_SJDB_OVERHANG"
      }
  fi
  if [[ -n "$STAR_GTF_REMAP" && "${KEEP_STAR_GTF_REMAP:-0}" != "1" ]]; then
    log "Removing temporary STAR seqname remap $STAR_GTF_REMAP"
    rm -f "$STAR_GTF_REMAP"
  fi
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
  if [[ "$HOST_KALLISTO" == "1" ]]; then
    log "using host kallisto $(kallisto version 2>/dev/null | head -1 || true)"
    kallisto index -i "$KALLISTO_INDEX" "$TRANSCRIPTOME_FASTA"
  else
    docker_run pbrun kallisto index \
      --index "/rna/kallisto/$(basename "$KALLISTO_INDEX")" \
      "/rna/kallisto/$(basename "$TRANSCRIPTOME_FASTA")" || {
        log "pbrun kallisto index unavailable; falling back to kallisto CLI in the image"
        docker_run kallisto index \
          -i "/rna/kallisto/$(basename "$KALLISTO_INDEX")" \
          "/rna/kallisto/$(basename "$TRANSCRIPTOME_FASTA")"
      }
  fi
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

#!/usr/bin/env bash
# Print canonical methyl-workflow-run command presets (program + profile + context).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/workflow_presets.sh [list|show PRESET]

Presets collapse --program, --context-file, and --context for common studies.

  list              Show preset names (default)
  show PRESET       Print a copy-ready command block

Environment overrides:
  METHYL_PROJECT_PATH   Study manifest (default: prostate-cancer example paths)
  METHYL_RUNTIME_ROOT   Use /work/epimethyl/current/runtime-bundle instead of repo paths
EOF
}

PROJECT="${METHYL_PROJECT_PATH:-/work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-5-CG.json}"
RUNTIME="${METHYL_RUNTIME_ROOT:-}"

prog() {
  local relpath="$1"
  if [[ -n "$RUNTIME" ]]; then
    echo "${RUNTIME}/domain/${relpath#workflow_engine/domain/}"
  else
    echo "$ROOT/$relpath"
  fi
}

profile() {
  local name="$1"
  if [[ -n "$RUNTIME" ]]; then
    echo "${RUNTIME}/domain/profiles/${name}.profile.json"
  else
    echo "$ROOT/workflow_engine/domain/profiles/${name}.profile.json"
  fi
}

cmd_stability_binary() {
  cat <<EOF
source .venv/bin/activate
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json) \\
  --context-file $(profile mc_dmp_gene_fc) \\
  --context '{"projectPath":"/work/projects/prostate-cancer/configs/project_Buffy_healthy_vs_PCa.json","pipelineProfile":"mc_dmp_gene_fc"}' \\
  --parallel-workers 1
EOF
}

cmd_lifecycle() {
  cat <<EOF
source .venv/bin/activate
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json) \\
  --context-file $(profile mc_dmp_gene_fc) \\
  --context '{"projectPath":"${PROJECT}","pipelineProfile":"mc_dmp_gene_fc"}' \\
  --parallel-workers 1
EOF
}

cmd_mc_stability_multi() {
  cat <<EOF
source .venv/bin/activate
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability.program.json) \\
  --context-file $(profile staged_ovr_mc) \\
  --context '{"projectPath":"${PROJECT}","pipelineProfile":"staged_ovr_mc"}' \\
  --parallel-workers 1
EOF
}

SAMD_PROJECT="${METHYL_SAMD_PROJECT_PATH:-${METHYL_PROJECT_PATH:-/work/projects/example-disease/configs/project_Healthy_vs_Disease.json}}"

cmd_samd_research_binary() {
  cat <<EOF
source .venv/bin/activate
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json) \\
  --context-file $(profile samd_research) \\
  --context '{"projectPath":"${SAMD_PROJECT}","pipelineProfile":"samd_research"}' \\
  --parallel-workers 1
EOF
}

cmd_samd_research_staged() {
  cat <<EOF
source .venv/bin/activate
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability.program.json) \\
  --context-file $(profile samd_research) \\
  --context '{"projectPath":"${SAMD_PROJECT}","pipelineProfile":"samd_research"}' \\
  --parallel-workers 1
EOF
}

cmd_samd_enrichment_binary() {
  cat <<EOF
source .venv/bin/activate
methyl-study-validate-manifest --project "${SAMD_PROJECT}" --profile samd_holdout_enrichment
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/buffy_healthy_vs_pca/configs/buffy_mc_stability.program.json) \\
  --context-file $(profile samd_holdout_enrichment) \\
  --context '{"projectPath":"${SAMD_PROJECT}","pipelineProfile":"samd_holdout_enrichment"}' \\
  --parallel-workers 1
EOF
}

cmd_samd_pivotal_lifecycle() {
  cat <<EOF
source .venv/bin/activate
methyl-study-validate-manifest --project "${SAMD_PROJECT}" --profile samd_pivotal
methyl-workflow-run \\
  --program $(prog workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json) \\
  --context-file $(profile samd_pivotal) \\
  --context '{"projectPath":"${SAMD_PROJECT}","pipelineProfile":"samd_pivotal"}' \\
  --parallel-workers 1
EOF
}

PRESETS=(
  stability_binary
  lifecycle
  mc_stability_multi
  samd_research_binary
  samd_research_staged
  samd_enrichment_binary
  samd_pivotal_lifecycle
)

list_presets() {
  printf '%s\n' "${PRESETS[@]}"
}

show_preset() {
  case "$1" in
    stability_binary) cmd_stability_binary ;;
    lifecycle) cmd_lifecycle ;;
    mc_stability_multi) cmd_mc_stability_multi ;;
    samd_research_binary) cmd_samd_research_binary ;;
    samd_research_staged) cmd_samd_research_staged ;;
    samd_enrichment_binary) cmd_samd_enrichment_binary ;;
    samd_pivotal_lifecycle) cmd_samd_pivotal_lifecycle ;;
    *) echo "Unknown preset: $1" >&2; list_presets >&2; exit 1 ;;
  esac
}

ACTION="${1:-list}"
case "$ACTION" in
  list) list_presets ;;
  show) show_preset "${2:?usage: workflow_presets.sh show PRESET}" ;;
  -h|--help) usage ;;
  *) usage; exit 1 ;;
esac

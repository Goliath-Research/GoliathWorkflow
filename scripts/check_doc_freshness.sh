#!/usr/bin/env bash
# Fail when active documentation reintroduces stale config/export patterns.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

RG_GLOBS=(
  --glob 'docs/**'
  --glob 'packages/**/docs/**'
  --glob 'packages/**/README.md'
  --glob 'workflow_engine/docs/**'
  --glob 'workers/docs/**'
  --glob 'workflow_engine/domain/checks/**/README.md'
  --glob '!.venv/**'
  --glob '!**/_book/**'
  --glob '!**/.quarto/**'
  --glob '!**/*.html'
  --glob '!**/*.pdf'
  --glob '!docs/plans/**'
  --glob '!docs/architecture/documentation-audit-2026-07.md'
  --glob '!docs/architecture/integrity-and-design-review-2026-07-01.md'
  --glob '!docs/deployment/work_layout_migration.md'
  --glob '!docs/reference/action-parameter-contract.md'
  --glob '!docs/theory/chapters/13-configuration-reference.qmd'
  --glob '!docs/theory/chapters/14-user-guide.qmd'
)

check_absent() {
  local pattern="$1"
  local msg="$2"
  if rg -l "$pattern" "${RG_GLOBS[@]}" . >/tmp/doc_fresh_hits.txt 2>/dev/null; then
    echo "FAIL: $msg" >&2
    head -30 /tmp/doc_fresh_hits.txt >&2
    fail=1
  fi
}

# Study manifests must not document step_config as the configuration surface.
check_absent '"step_config"' 'Active docs must not teach step_config in study manifests (use actionConfig layers)'

check_absent 'step_config\.validation' 'Use actionConfig.validation or profile validation keys instead of step_config.validation'

check_absent 'step_config\.detection' 'Use actionConfig.detection instead of step_config.detection'

check_absent 'step_config\.predictor' 'Use actionConfig.predictor instead of step_config.predictor'

check_absent 'step_config\.centroid' 'Use actionConfig.centroid instead of step_config.centroid'

check_absent 'step_config\.mapper' 'Use actionConfig.mapper instead of step_config.mapper'

check_absent 'step_config\.enricher' 'Use actionConfig.enricher instead of step_config.enricher'

check_absent 'step_config\.classifier' 'Use actionConfig.classifier instead of step_config.classifier'

check_absent 'step_config\.alignment_qc' 'Use actionConfig.alignment_qc instead of step_config.alignment_qc'

check_absent 'step_config\.methyl_extract' 'Use actionConfig.methyl_extract instead of step_config.methyl_extract'

check_absent 'step_config\.extraction_qc' 'Use actionConfig.extraction_qc instead of step_config.extraction_qc'

# Precedence must not imply Python package defaults for tunable science knobs.
check_absent 'site manifest → package defaults' 'Precedence must end with no Python fallback, not package defaults'

check_absent 'site manifest -> package defaults' 'Precedence must end with no Python fallback, not package defaults'

# Deprecated profile names as primary paths (aliases remain in code only).
check_absent 'discovery_gene_featurecuts\.profile\.json' 'Use mc_dmp_gene_fc profile name'

check_absent 'mc_dmp_discovery\.profile\.json' 'Use mc_dmp profile name'

check_absent 'mc_dmp_featurecuts\.profile\.json' 'Use mc_dmp_fc profile name'

check_absent 'mc_gene_mapper\.profile\.json' 'Use mc_gene profile name'

check_absent 'mc_gene_featurecuts\.profile\.json' 'Use mc_gene_fc profile name'

check_absent 'dmp_panel_stability\.profile\.json' 'Use mc_dmp_fc profile name'

check_absent 'gene_enricher_stability\.profile\.json' 'Use mc_dmp profile name'

# Hardcoded gene FC cap example that contradicts site/profile config.
check_absent 'stability_gene_featurecuts_max_dmps": 500' 'Gene FC caps belong in site/profile actionConfig, not hardcoded 500 in docs'

check_absent 'package defaults in MonteCarloConfig' 'Do not document Python package defaults for MC tunables'

# Usage manual PDF uses pre-rendered PNG; inline Mermaid renders as source in LaTeX.
if rg -l '```mermaid' --glob 'docs/usage/**/*.qmd' . >/tmp/doc_fresh_hits.txt 2>/dev/null; then
  echo "FAIL: docs/usage must not use inline \`\`\`mermaid (use ../diagrams/out/*.png for PDF)" >&2
  head -30 /tmp/doc_fresh_hits.txt >&2
  fail=1
fi

# Primary DMP export should be selected, not classifier-extended as the main narrative.
check_absent 'dmps-\*-classifier-extended\.csv' 'Prefer dmps-*-selected.csv; classifier-extended is transitional'

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo "Doc freshness check passed."

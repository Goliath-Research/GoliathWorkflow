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
  --glob '!docs/architecture/documentation-audit-2026-07-09.md'
  --glob '!docs/architecture/integrity-and-design-review-2026-07-01.md'
  --glob '!workflow_engine/docs/pipeline_architecture.md'
  --glob '!workflow_engine/CAPABILITY_CHECK.md'
  --glob '!workflow_engine/delphi/**'
  --glob '!tools/methyl-config-editor/**'
  --glob '!docs/deployment/production_runbook.md'
  --glob '!docs/reference/action-parameter-contract.md'
  --glob '!docs/implementation/sample-preparation-flow.md'
  --glob '!docs/theory/chapters/13-configuration-reference.md'
  --glob '!docs/theory/chapters/14-user-guide.md'
  --glob '!**/site/**'
  --glob '!**/site-customer/**'
  --glob '!**/site-pdf/**'
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

# Markdown-first site: no Quarto .qmd sources anywhere in the repo.
if find docs workflow_engine packages workers deploy scripts \
    -name '*.qmd' -not -path '*/.venv/*' -not -path '*/site/*' \
    -print >/tmp/doc_fresh_hits.txt 2>/dev/null && [[ -s /tmp/doc_fresh_hits.txt ]]; then
  echo "FAIL: Quarto .qmd sources remain (convert to .md or delete)" >&2
  head -30 /tmp/doc_fresh_hits.txt >&2
  fail=1
fi

if rg -l 'diagrams/out/.*\.png' --glob 'docs/usage/**/*.md' --glob 'docs/theory/**/*.md' . >/tmp/doc_fresh_hits.txt 2>/dev/null; then
  echo "FAIL: usage/theory must use inline \`\`\`mermaid (not diagrams/out PNG embeds)" >&2
  head -30 /tmp/doc_fresh_hits.txt >&2
  fail=1
fi

# Leftover Quarto directives hide diagrams or break admonitions in MkDocs.
check_absent 'content-visible when-format' 'Use one fenced mermaid block for HTML and PDF (Playwright); do not split with Quarto content-visible'
check_absent '\{\.callout-' 'Use MkDocs admonitions (!!! warning / !!! note), not Quarto callouts'

# Primary DMP export should be selected, not classifier-extended as the main narrative.
check_absent 'dmps-\*-classifier-extended\.csv' 'Prefer dmps-*-selected.csv; classifier-extended is transitional'

# Retired gateway admin / catalog HTTP (worker-only gateway).
check_absent 'Gateway routes: `GET /v1/actions`' 'Gateway is worker-only; use schemas/actions/catalog.json'
check_absent 'Fetch live metadata with `GET /v1/actions`' 'Workers use catalog.json metadata'
check_absent '`POST /v1/workflows/definitions`' 'Deploy via deploy_workflow_definitions.sh or methyl-study-start'
check_absent '`POST /v1/workflows/instances`' 'Start instances via methyl-study-start or portal SQL'
check_absent '/v1/admin/catalog' 'Admin routes removed; use seed_action_catalog.py'

# SamplePrep facts that drifted after mojo-align / MethylExtractor / arm-layout (2026-08-25).
check_absent 'GPU MethylExtractor' 'MethylExtractor is CPU (C/HTSlib/HDF5); GPU is alignment'

check_absent 'alignmentMode is not yet on the methyl_qc' 'alignmentMode is on schemas/tasks/sample_methyl_qc.input.schema.json'

# METHYL_METHYLGRAPHER_MOJO_IMAGE as a primary pin (a same-line "deprecated alias" note is allowed).
if rg -n 'METHYL_METHYLGRAPHER_MOJO_IMAGE' "${RG_GLOBS[@]}" . >/tmp/doc_fresh_mojo_image.txt 2>/dev/null; then
  if grep -vi 'deprecated' /tmp/doc_fresh_mojo_image.txt >/tmp/doc_fresh_hits.txt && [[ -s /tmp/doc_fresh_hits.txt ]]; then
    echo "FAIL: Use METHYL_MOJO_ALIGN_IMAGE as the primary pin (deprecated alias sentence OK)" >&2
    head -30 /tmp/doc_fresh_hits.txt >&2
    fail=1
  fi
fi

check_absent 'does \*\*not\*\* emit.*extraction_manifest' 'MethylExtractor emits {sampleId}.extraction_manifest.json; describe preserve-or-synthesize'

# Retired action name in active operator docs.
check_absent 'sample\.upload_h5' 'Use sample.archive_sample'

check_absent '37 workflow actions' 'Action count drifts; cite schemas/actions/catalog.json'

# PostgreSQL env: code reads POSTGRES_*, not libpq PGHOST in deployment docs.
if rg -l 'export PGHOST=' --glob 'docs/deployment/**' --glob 'docs/usage/**' --glob '!**/.quarto/**' . >/tmp/doc_fresh_hits.txt 2>/dev/null; then
  echo "FAIL: deployment docs must use POSTGRES_* not PGHOST" >&2
  head -30 /tmp/doc_fresh_hits.txt >&2
  fail=1
fi

# Deploy env templates must exist.
for f in deploy/env/gateway.postgres.env.example deploy/env/gateway.mssql.env.example deploy/env/worker.env.example; do
  [[ -f "$ROOT/$f" ]] || { echo "FAIL: missing $f" >&2; fail=1; }
done

if [[ $fail -ne 0 ]]; then
  exit 1
fi

echo "Doc freshness check passed."

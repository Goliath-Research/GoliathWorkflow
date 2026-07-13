# Azure DevOps traceability seed tools
#
# Generate manifest from docs/plans:
#   .venv/bin/python scripts/ado_traceability/generate_manifest.py
#
# Dry-run seed (no Boards writes):
#   .venv/bin/python scripts/ado_traceability/seed_platform_boards.py
#
# Apply (create Epic / Features / User Stories):
#   .venv/bin/python scripts/ado_traceability/seed_platform_boards.py --apply
#
# Backfill AB# into plan frontmatter:
#   .venv/bin/python scripts/ado_traceability/backfill_plan_ids.py
#
# Link Azure Repos commits to Features + User Stories (no history rewrite):
#   .venv/bin/python scripts/ado_traceability/link_commits.py          # dry-run
#   .venv/bin/python scripts/ado_traceability/link_commits.py --apply
#
# Requires: az CLI + azure-devops extension; defaults org/project from
# `az devops configure` (EpiMethyl / Development).

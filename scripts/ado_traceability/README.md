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
# Requires: az CLI + azure-devops extension; defaults org/project from
# `az devops configure` (EpiMethyl / Development).

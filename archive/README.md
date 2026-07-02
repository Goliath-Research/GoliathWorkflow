# Archive

Git-tracked storage for **ambiguous or regenerable artifacts** that do not belong in the active repo layout. Nothing here is required for builds, tests, or production deploys.

| Item | Why archived |
|------|----------------|
| `MethylPipeline.pdf` | Historical Quarto/PDF export; regenerate from `docs/theory` or `docs/usage` |
| `MethylPipeline-analysis.pdf` | Analysis snapshot PDF |
| `Meta.mmd` | Stray ERD diagram (portal DB designer export); not part of `docs/diagrams/` pipeline |
| `samples.csv` | Example sample list; generic `samples.csv` names appear in package docs as placeholders only |

**Deleted (not archived)** during repo structure cleanup: `run_methyldetector.py` (superseded by `methyl-detector` CLI), empty `MethylPipeline.session.sql`, `mkdocs.yml` (docs are Quarto).

**Frozen reference (not archived):** Delphi gateway under [`workflow_engine/delphi/`](../workflow_engine/delphi/) — production uses Python `methyl-gateway`.

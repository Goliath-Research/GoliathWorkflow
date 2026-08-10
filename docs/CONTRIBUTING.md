# Contributing to MethylPipeline documentation

Documentation is **Markdown-first**. The site is built with Material for MkDocs.

## Quick commands

```bash
source .venv/bin/activate
pip install -r docs-requirements.txt

make docs-serve          # live preview at http://127.0.0.1:8000
make docs                # mkdocs build --strict → site/
make docs-customer       # customer subset → site-customer/
make docs-pdf            # Playwright PDF of the HTML site → site-pdf/
make check-docs          # link + freshness guards
```

Host the static `site/` folder anywhere (local file server, GitHub Pages, Azure Static Web Apps, Blob, `/work` share). Customer subset builds to `site-customer/`. Aggregated PDF is `site-pdf/MethylPipeline-Documentation.pdf`.

## One canonical home per fact

| Kind of content | Home |
|-----------------|------|
| Math, assumptions, citations | `docs/theory/` |
| Commands, artifacts, runbooks | `docs/usage/` |
| Engine / worker / compiler internals | `docs/implementation/` |
| System topology, layers | `docs/architecture/` |
| Schemas, DomainProgram language | `docs/reference/` |
| Production ops | `docs/deployment/` |
| Product controls / SaMD synthesis | `docs/regulatory/` |
| Engineering plans | `docs/plans/` (internal; excluded from published nav) |
| Exploratory notes | `docs/research/` (not product truth) |

If a fact is duplicated, **link upward** — do not copy prose.

## Writing rules

1. **Markdown only** for new pages (`.md`). Do not add Quarto `.qmd` books.
2. **Mermaid** — use fenced ` ```mermaid ` blocks (dynamic in the site and on GitHub). Prefer editing `docs/diagrams/src/*.mmd` when a diagram is shared, then paste or reference the same source. Pre-rendered PNG/SVG under `docs/diagrams/out/` is optional (Marp / offline).
3. **Math** — use `$inline$` and `$$…$$` blocks (MathJax). Give important equations an HTML id:
   ```markdown
   <div id="eq-effect-size" markdown="1">

   $$
   e_i = \ldots
   $$

   </div>
   ```
4. **Cross-page links** — link to the target file + anchor (`../theory/chapters/01-methylutils.md#eq-effect-size`), not Quarto `@eq-` / `@sec-`.
5. **Update `mkdocs.yml` nav** when adding a page that should appear in the site.
6. **Claim boundary** — regulatory / customer pages must state that architecture and profiles are not FDA clearance; link `regulatory/validation-evidence-index.md` for live evidence.
7. **Config not code** — document tunables under site/profile `actionConfig`, never as Python `DEFAULT_*` or study `step_config`.

## CI guards

- `mkdocs build --strict`
- `scripts/check_doc_links.sh`
- `scripts/check_doc_freshness.sh`
- Diagram `--check` remains available for shared `docs/diagrams/src` assets used by Marp

## Customer vs internal

- Full site: `mkdocs.yml`
- Customer subset (no implementation internals / plans): `mkdocs.customer.yml`

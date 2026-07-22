---
name: Regulatory pitch presentation
overview: Convert the regulatory product-positioning markdown into a self-contained Marp slide deck (HTML + PDF) under `docs/presentations/`, prioritizing diagrams, tables, and concise talking points so it can be shared without the rest of the repository.

> **Status: IMPLEMENTED.** Sales-themed interactive deck at [`docs/presentations/regulatory-ready-platform-multiomics.md`](../presentations/regulatory-ready-platform-multiomics.md) (`themes/epimethyl-sales.css`, DomainProgram + worker diagrams); render via [`scripts/render_presentations.sh`](../../scripts/render_presentations.sh) + [`scripts/embed_marp_mermaid.mjs`](../../scripts/embed_marp_mermaid.mjs).

azure_devops:
  type: Feature
  title: "Regulatory-ready pitch presentation (Marp)"
  epic_id: 413
  # work_item_id: assign after Boards seed
todos:
  - id: author-deck
    content: "Author docs/presentations/regulatory-ready-platform-multiomics.md (~12 slides: pillars, roadmap table, open-core Mermaid, GTM, selling points)"
    status: completed
  - id: render-pipeline
    content: Update scripts/render_presentations.sh to emit HTML+PDF; render the new deck
    status: completed
  - id: index-docs
    content: Link the deck from docs/presentations/README.md and docs/regulatory/README.md
    status: completed
  - id: verify-shareable
    content: Spot-check Mermaid/table rendering in HTML and PDF; confirm no required in-repo hyperlinks for the talk
    status: completed
---

# Regulatory-ready pitch presentation (Marp)

## Recommendation: Marp (not PowerPoint-first)

| Format | Fit for this doc |
|--------|------------------|
| **Marp → HTML (+ PDF)** | **Best.** Already the repo standard ([`docs/presentations/`](../presentations/README.md), [`scripts/render_presentations.sh`](../../scripts/render_presentations.sh)). Markdown source stays in git; Mermaid and tables render; HTML is offline-shareable; PDF is the email-friendly attach. |
| PowerPoint | Better only when the buyer must rebrand/edit slides in corporate templates. Mermaid would need image export; content drifts from git. |
| Quarto Reveal.js | Also good for Mermaid, but would duplicate the existing Marp convention for no gain here. |

**Chosen deliverable:** Marp source + rendered **self-contained HTML** and **PDF**.

## Deliverables

- [`docs/presentations/regulatory-ready-platform-multiomics.md`](../presentations/regulatory-ready-platform-multiomics.md)
- HTML/PDF siblings (Mermaid embedded via [`scripts/embed_marp_mermaid.mjs`](../../scripts/embed_marp_mermaid.mjs))
- Index links in presentations + regulatory READMEs

"""Drop static assets that must not enter the MkDocs file set.

mkdocs-exporter rewrites every CSS file listed in ``files.css_files()``.
Trees we exclude from the HTML site can still contribute CSS File objects
whose ``abs_dest_path`` is never written, which crashes the exporter.
"""

from __future__ import annotations

from mkdocs.structure.files import Files

_DROP_PREFIXES = (
    "presentations/",
    "diagrams/",
    "plans/",
    "research/",
    "diagnostics/",
    "examples/",
    "user-manual/",
    "docs/",
    "theory/.quarto/",
    "usage/.quarto/",
)

_DROP_SUFFIXES = (
    ".qmd",
    ".pdf",
    ".tex",
    ".bib",
    ".canvas.tsx",
    ".canvas.data.json",
)

# IDE-only files under canvas/; keep canvas/README.md for the HTML site.
_DROP_EXACT = frozenset(
    {
        "canvas/tsconfig.json",
    }
)


def on_files(files: Files, config) -> Files:  # noqa: ANN001
    keep = []
    for f in files:
        src = f.src_uri if hasattr(f, "src_uri") else f.src_path
        src = src.replace("\\", "/")
        if src.startswith(".quarto/") or "/.quarto/" in src:
            continue
        if src in _DROP_EXACT:
            continue
        if any(src.startswith(p) for p in _DROP_PREFIXES):
            continue
        if any(src.endswith(s) for s in _DROP_SUFFIXES):
            continue
        keep.append(f)
    return Files(keep)

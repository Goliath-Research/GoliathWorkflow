"""Turn site-external Markdown links into plain code spans for MkDocs.

Published pages intentionally cite repo paths (``workers/``, ``packages/``,
excluded trees like ``plans/`` / ``diagrams/``). MkDocs cannot resolve those as
documentation pages and floods the build with INFO lines. Convert them to
backticks so the path remains visible without validation noise.

Filesystem truth for those paths is still checked by ``scripts/check_doc_links.sh``.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

# Link / image targets that leave the published MkDocs site.
_EXTERNAL = re.compile(
    r"""
    (?P<img>!?)
    \[
      (?P<label>[^\]]*)
    \]
    \(
      (?P<url>
        (?:
          (?:\.\./)+                          # climb out of docs/…
          (?:
            workers|packages|workflow_engine|scripts|deploy|contracts|
            schemas|ci|tests|tools|docker|requirements[\w.-]*|
            pyproject\.toml|AGENTS\.md|\.cursor|README\.md|Makefile|
            mkdocs\.yml|mkdocs\.[^)/]+|
            docs/                             # mistaken docs/docs climb
          )
          [^)\s]*
        )
        |
        (?:
          (?:\.\./)*                          # or stay under docs/ but excluded
          (?:plans|research|examples|diagrams|user-manual|presentations|
             diagnostics|canvas/[^)]*\.canvas\.tsx)
          [^)\s]*
        )
      )
    \)
    """,
    re.VERBOSE,
)


def _repo_display(url: str) -> str:
    """Normalize a relative link to a repo-root-ish display path."""
    path = unquote(url.split("#", 1)[0]).rstrip("/")
    # Strip leading ../ segments for readability.
    while path.startswith("../"):
        path = path[3:]
    if path.startswith("docs/"):
        return path
    # From docs/foo/bar.md, ../../workers → workers
    return path


def on_page_markdown(markdown: str, page, config, files):  # noqa: ANN001, ARG001
    def repl(match: re.Match[str]) -> str:
        if match.group("img"):
            # Drop broken/excluded figures; inline Mermaid (or prose) should remain.
            return ""
        label = match.group("label").strip()
        url = match.group("url").strip()
        display = _repo_display(url)
        # Prefer a short label when it already looks like a path/filename.
        if not label or label in {url, display} or label.endswith(
            (".py", ".md", ".json", ".yml", ".yaml", ".sql", ".sh", ".mdc", ".svg", ".png", ".mmd")
        ):
            return f"`{display}`"
        return f"{label} (`{display}`)"

    return _EXTERNAL.sub(repl, markdown)

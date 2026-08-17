#!/usr/bin/env python3
"""Rewrite documentation links after IA revision (big-bang cutover)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "_book",
    "pipeline_architecture_files",
    "MethylPipeline-overview_files",
}

# Order matters: longer / more specific patterns first.
REPLACEMENTS: list[tuple[str, str]] = [
    (r"docs/user-manual/", "docs/usage/"),
    (r"\[`docs/user-manual/", "[`docs/usage/"),
    (r"user-manual/index\.qmd", "usage/index.md"),
    (r"user-manual/14-deployment", "usage/14-deployment-and-distributed-workflow.md"),
    (r"user-manual/13-distributed", "usage/13-distributed-methyl-validation.md"),
    (r"user-manual/15-optional", "usage/15-optional-hyperparameter-search.md"),
    (r"user-manual/(\d{2}-[^`\s\)]+)\.qmd", r"usage/\1.md"),
    (r"user-manual/(\d{2}-[^`\s\)]+\.md)", r"usage/\1"),
    (r"docs/user-manual", "docs/usage"),
    (r"\(user-manual/", "(usage/"),
    (r"`user-manual/", "`usage/"),
    (r"docs/domain_program_language\.md", "docs/reference/domain-program-language.md"),
    (r"domain_program_language\.md", "reference/domain-program-language.md"),
    (r"docs/config_parameter_matrix\.md", "docs/reference/config-parameter-matrix.md"),
    (r"config_parameter_matrix\.md", "reference/config-parameter-matrix.md"),
    (r"docs/architecture_review\.md", "docs/architecture/index.md"),
    (r"architecture_review\.md", "architecture/index.md"),
    (r"docs/MethylPipeline-overview\.qmd", "docs/architecture/index.md"),
    (r"MethylPipeline-overview\.qmd", "architecture/index.md"),
    (r"docs/MethylPipeline-analysis\.qmd", "docs/theory/index.md"),
    (r"theory/chapters/14-user-guide\.qmd", "usage/index.md"),
    (r"chapters/14-user-guide", "usage/index"),
    (r"theory/chapters/13-configuration-reference\.qmd", "reference/configuration-reference.md"),
    (r"docs/(usage|theory|reference)/([^)\s`]+)\.qmd", r"docs/\1/\2.md"),
    (r"@sec-configuration-reference", "reference/configuration-reference"),
    (r"Theory ch\.13", "Reference configuration-reference"),
    (r"theory ch\.13", "reference configuration-reference"),
    (r"User manual ch\.14", "Usage ch.14"),
    (r"user manual ch\.14", "usage ch.14"),
    (r"User manual ch\.03", "Usage ch.03"),
    (r"user manual ch\.03", "usage ch.03"),
    (r"docs/user manual", "docs/usage"),
    (r"User manual", "Usage manual"),
    (r"user-manual", "usage"),
]

TEXT_EXTENSIONS = {".md", ".qmd", ".mdc", ".yml", ".yaml", ".json", ".py", ".sh", ".plan.md"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    if path.name.endswith(".pdf") or path.name.endswith(".html"):
        return True
    if "agent-transcripts" in path.parts:
        return True
    return False


def rewrite_text(text: str) -> tuple[str, int]:
    count = 0
    for pattern, repl in REPLACEMENTS:
        new_text, n = re.subn(pattern, repl, text)
        if n:
            count += n
            text = new_text
    return text, count


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    total_files = 0
    total_repls = 0

    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix not in TEXT_EXTENSIONS and path.name not in {"README", "AGENTS.md"}:
            continue
        if path == Path(__file__).resolve():
            continue

        original = path.read_text(encoding="utf-8", errors="replace")
        updated, n = rewrite_text(original)
        if n == 0:
            continue

        total_files += 1
        total_repls += n
        rel = path.relative_to(ROOT)
        print(f"{rel}: {n} replacement(s)")
        if not dry_run:
            path.write_text(updated, encoding="utf-8")

    print(f"\nDone: {total_repls} replacement(s) in {total_files} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

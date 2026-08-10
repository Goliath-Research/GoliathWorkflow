#!/usr/bin/env python3
"""Convert Quarto .qmd theory/usage/reference docs to plain Markdown for MkDocs.

- Strips Quarto YAML front matter
- Converts $$ {#eq-id} equation labels to <div id="eq-id"> wrappers
- Converts @eq- / @sec- crossrefs to Markdown links
- Converts [@citekey] to plain citekey text (bibliography via mkdocs-bibtex separately)
- Replaces diagrams/out/*.png images with inline ```mermaid from docs/diagrams/src
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_SRC = ROOT / "docs" / "diagrams" / "src"

PNG_TO_MMD = {
    "pipeline-stages.png": "pipeline-stages.mmd",
    "sample-prep-flow.png": "sample-prep-flow.mmd",
    "layer-model.png": "layer-model.mmd",
    "distributed-runtime.png": "distributed-runtime.mmd",
    "stability-stage.png": "stability-stage.mmd",
    "samd-study-lifecycle.png": "samd-study-lifecycle.mmd",
    "methylation-application-packs.png": "methylation-application-packs.mmd",
    "alzheimer-cfdna-pack.png": "alzheimer-cfdna-pack.mmd",
    "plant-abiotic-stress-pack.png": "plant-abiotic-stress-pack.mmd",
}

IMG_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)]*?diagrams/out/([^)/]+))\)",
    re.MULTILINE,
)

EQ_BLOCK_RE = re.compile(
    r"\$\$(.*?)\$\$\s*\{#(eq-[^}]+)\}",
    re.DOTALL,
)

HEADING_ID_RE = re.compile(
    r"^(#{1,6}\s+.+?)\s*\{#(sec-[^}]+)\}\s*$",
    re.MULTILINE,
)

CROSSREF_RE = re.compile(r"@(eq|sec)-([A-Za-z0-9_-]+)")
CITE_RE = re.compile(r"\[@([A-Za-z0-9_:-]+)\]")
YAML_FM_RE = re.compile(r"^---\n.*?\n---\n+", re.DOTALL)


def mermaid_for_png(png_name: str) -> str | None:
    mmd_name = PNG_TO_MMD.get(png_name)
    if not mmd_name:
        return None
    path = DIAGRAM_SRC / mmd_name
    if not path.is_file():
        return None
    body = path.read_text(encoding="utf-8").rstrip() + "\n"
    return f"```mermaid\n{body}```"


def replace_diagram_images(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        alt, _path, png_name = match.group(1), match.group(2), match.group(3)
        block = mermaid_for_png(png_name)
        if block is None:
            return match.group(0)
        caption = f"\n\n*{alt}*\n" if alt.strip() else "\n"
        return block + caption

    return IMG_RE.sub(_sub, text)


def convert_equations(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        body = match.group(1).strip("\n")
        eq_id = match.group(2)
        return f'<div id="{eq_id}" markdown="1">\n\n$$\n{body}\n$$\n\n</div>'

    return EQ_BLOCK_RE.sub(_sub, text)


def convert_heading_ids(text: str) -> str:
    # Keep attr_list form supported by Python-Markdown: # Title {#id}
    return HEADING_ID_RE.sub(r"\1 {#\2}", text)


def convert_crossrefs(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        kind, name = match.group(1), match.group(2)
        label = f"{kind}-{name}"
        display = name.replace("-", " ")
        if kind == "eq":
            display = f"Eq. {name}"
        elif kind == "sec":
            display = f"§ {display}"
        return f"[{display}](#{kind}-{name})"

    return CROSSREF_RE.sub(_sub, text)


def convert_citations(text: str) -> str:
    # Keep cite keys readable; mkdocs-bibtex can pick up [@key] if enabled later.
    return CITE_RE.sub(r"[\1]", text)


def strip_quarto_only(text: str) -> str:
    text = YAML_FM_RE.sub("", text)
    # Drop raw Quarto/LaTeX include blocks that are PDF-only.
    text = re.sub(r"```\{=latex\}.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\{\{<[^>]+>\}\}", "", text)
    return text


def convert_text(text: str) -> str:
    text = strip_quarto_only(text)
    text = convert_equations(text)
    text = convert_heading_ids(text)
    text = convert_crossrefs(text)
    text = convert_citations(text)
    text = replace_diagram_images(text)
    # Fix known broken SaMD link target
    text = text.replace(
        "15-hyperparameter-search.qmd",
        "15-optional-hyperparameter-search.md",
    )
    text = text.replace(".qmd)", ".md)")
    text = text.replace(".qmd#", ".md#")
    text = text.replace(".qmd`", ".md`")
    return text


def convert_file(src: Path, dst: Path | None = None, *, delete_src: bool = False) -> Path:
    dst = dst or src.with_suffix(".md")
    text = src.read_text(encoding="utf-8")
    dst.write_text(convert_text(text), encoding="utf-8")
    if delete_src and dst != src:
        src.unlink()
    return dst


def main(argv: list[str]) -> int:
    delete = "--delete-src" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")]
    if not paths:
        paths = [
            *sorted((ROOT / "docs" / "theory").rglob("*.qmd")),
            *sorted((ROOT / "docs" / "usage").rglob("*.qmd")),
            ROOT / "docs" / "reference" / "configuration-reference.qmd",
        ]
        paths = [p for p in paths if p.is_file()]

    for src in paths:
        out = convert_file(src, delete_src=delete)
        print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

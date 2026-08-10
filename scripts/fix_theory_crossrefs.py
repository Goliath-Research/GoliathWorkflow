#!/usr/bin/env python3
"""Rewrite theory/reference @sec/@eq anchors into cross-page MkDocs links."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

SEC_PAGES = {
    "sec-methylutils": "theory/chapters/01-methylutils.md",
    "sec-methylcentroid": "theory/chapters/02-methylcentroid.md",
    "sec-methyldetector": "theory/chapters/03-methyldetector.md",
    "sec-detector-coverage": "theory/chapters/03-methyldetector.md",
    "sec-methylclassifier": "theory/chapters/04-methylclassifier.md",
    "sec-classifier-class-weight": "theory/chapters/04-methylclassifier.md",
    "sec-methylpredictor-validation": "theory/chapters/05-methylpredictor-and-validation.md",
    "sec-methylmapper": "theory/chapters/07-methylmapper.md",
    "sec-methyldeconv": "theory/chapters/07a-methyldeconv.md",
    "sec-methylenricher": "theory/chapters/08-methylenricher.md",
    "sec-methylalignmentqc": "theory/chapters/09-methylalignmentqc.md",
    "sec-methylextractionqc": "theory/chapters/09a-methylextractionqc.md",
    "sec-limitations": "theory/chapters/10-limitations-and-open-questions.md",
    "sec-project-configuration": "theory/chapters/11-project-configuration.md",
    "sec-two-workflows": "theory/chapters/12-two-workflows.md",
    "sec-distributed-mc-shared-storage": "theory/chapters/12-two-workflows.md",
    "sec-workflow-model-creation": "theory/chapters/12-two-workflows.md",
    "sec-workflow-prediction": "theory/chapters/12-two-workflows.md",
    "sec-model-creation-validation": "theory/chapters/15-model-creation-and-validation.md",
}

EQ_PAGES = {
    "eq-centroid-moments": "theory/chapters/01-methylutils.md",
    "eq-count-summaries": "theory/chapters/01-methylutils.md",
    "eq-ecdf-edges": "theory/chapters/01-methylutils.md",
    "eq-ks": "theory/chapters/01-methylutils.md",
    "eq-ks-pvalue": "theory/chapters/01-methylutils.md",
    "eq-mwu-bins": "theory/chapters/01-methylutils.md",
    "eq-dl": "theory/chapters/01-methylutils.md",
    "eq-overlap": "theory/chapters/01-methylutils.md",
    "eq-storey": "theory/chapters/01-methylutils.md",
    "eq-effect-size": "theory/chapters/01-methylutils.md",
    "eq-ecdf-score": "theory/chapters/01-methylutils.md",
    "eq-ecdf-softmax": "theory/chapters/01-methylutils.md",
    "eq-detector-statset": "theory/chapters/03-methyldetector.md",
    "eq-effect-coverage": "theory/chapters/03-methyldetector.md",
    "eq-chrom-fusion": "theory/chapters/04-methylclassifier.md",
    "eq-ovr-fusion": "theory/chapters/04-methylclassifier.md",
    "eq-geomean-control": "theory/chapters/04-methylclassifier.md",
    "eq-platt": "theory/chapters/04-methylclassifier.md",
    "eq-class-weight-balanced": "theory/chapters/04-methylclassifier.md",
    "eq-predictor-metrics": "theory/chapters/05-methylpredictor-and-validation.md",
    "eq-entropy": "theory/chapters/05-methylpredictor-and-validation.md",
    "eq-stability-frequency": "theory/chapters/05-methylpredictor-and-validation.md",
    "eq-houseman-qp": "theory/chapters/07a-methyldeconv.md",
    "eq-hitimed-path": "theory/chapters/07a-methyldeconv.md",
    "eq-jaccard": "theory/chapters/08-methylenricher.md",
    "eq-module-score": "theory/chapters/08-methylenricher.md",
    "eq-disease-prior": "theory/chapters/08-methylenricher.md",
    "eq-final-module-score": "theory/chapters/08-methylenricher.md",
    "eq-ppi-coherence": "theory/chapters/08-methylenricher.md",
    "eq-dup-rate": "theory/chapters/09-methylalignmentqc.md",
}

LINK_RE = re.compile(r"\[([^\]]+)\]\(#((?:eq|sec)-[A-Za-z0-9_-]+)\)")


def rel_link(from_file: Path, target_page: str, anchor: str) -> str:
    target = DOCS / target_page
    rel = Path(os_path_rel(from_file.parent, target)).as_posix()
    return f"{rel}#{anchor}"


def os_path_rel(start: Path, target: Path) -> str:
    return Path(os_relpath(str(target), str(start)))


def os_relpath(target: str, start: str) -> str:
    import os

    return os.path.relpath(target, start)


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    def _sub(match: re.Match[str]) -> str:
        label, anchor = match.group(1), match.group(2)
        page = SEC_PAGES.get(anchor) or EQ_PAGES.get(anchor)
        if page is None:
            return match.group(0)
        # Same page: keep local anchor
        if path.resolve() == (DOCS / page).resolve():
            return f"[{label}](#{anchor})"
        return f"[{label}]({rel_link(path, page, anchor)})"

    new = LINK_RE.sub(_sub, text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for path in [
        *sorted((DOCS / "theory").rglob("*.md")),
        DOCS / "reference" / "configuration-reference.md",
    ]:
        if path.is_file() and fix_file(path):
            print(f"fixed {path.relative_to(ROOT)}")
            changed += 1
    print(f"{changed} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

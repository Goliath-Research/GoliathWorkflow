#!/usr/bin/env python3
"""Generate platform_backlog.yaml from docs/plans README + plan frontmatter."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "docs" / "plans"
DEFAULT_OUT = Path(__file__).resolve().parent / "platform_backlog.yaml"

COMPLETE_RE = re.compile(
    r"Status:\s*(IMPLEMENTED|COMPLETE[D]?|implemented|complete)\b",
    re.I,
)
PATH_RE = re.compile(
    r"`((?:packages|workers|workflow_engine|ci|scripts|schemas|contracts|deploy|docs)/[^`\s]+)`"
)
ROW_RE = re.compile(
    r"\|\s*\[`([^`]+\.plan\.md)`\]\([^)]+\)\s*\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\|"
)
TODO_BLOCK_RE = re.compile(
    r"(?m)^todos:\s*\n((?:^[ \t]+.*\n|^[ \t]*\n)*)",
)
TODO_ITEM_RE = re.compile(
    r"(?m)^[ \t]+-[ \t]+id:[ \t]*(?P<id>\S+)\s*\n"
    r"(?:^[ \t]+content:[ \t]*(?P<content>.+?)\s*\n)?"
    r"(?:^[ \t]+status:[ \t]*(?P<status>\S+)\s*\n)?",
)
NAME_RE = re.compile(r"(?m)^name:\s*(.+)$")
OVERVIEW_RE = re.compile(
    r"(?ms)^overview:\s*(?:>-|\||>)?\s*(.+?)(?=\n(?:[a-zA-Z_][\w]*:|> \*\*|todos:|azure_devops:|isProject:))",
)


def extract_frontmatter_raw(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    return text[3:end].strip("\n"), text[end + 4 :]


def sanitize_frontmatter(fm_raw: str) -> str:
    """Drop markdown status blockquotes that break YAML parsers."""
    lines = []
    for line in fm_raw.splitlines():
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_todos_regex(fm_raw: str) -> list[dict[str, str]]:
    m = TODO_BLOCK_RE.search(fm_raw)
    if not m:
        return []
    block = m.group(1)
    stories: list[dict[str, str]] = []
    for item in TODO_ITEM_RE.finditer(block):
        tid = (item.group("id") or "").strip().strip("\"'")
        content = (item.group("content") or tid).strip().strip("\"'")
        status = (item.group("status") or "pending").strip().lower()
        stories.append({"id": tid, "title": content, "raw_status": status})
    return stories


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, str]:
    fm_raw, body = extract_frontmatter_raw(text)
    sanitized = sanitize_frontmatter(fm_raw)
    fm: dict[str, Any] = {}
    try:
        loaded = yaml.safe_load(sanitized) or {}
        if isinstance(loaded, dict):
            fm = loaded
    except Exception:
        fm = {}
        name_m = NAME_RE.search(fm_raw)
        if name_m:
            fm["name"] = name_m.group(1).strip()
        ov_m = OVERVIEW_RE.search(fm_raw)
        if ov_m:
            fm["overview"] = " ".join(ov_m.group(1).split())
    return fm, body, fm_raw


def plan_stem(name: str) -> str:
    return name.replace(".plan.md", "")


def infer_state(
    fm: dict[str, Any],
    fm_raw: str,
    body: str,
    stories: list[dict[str, str]],
    superseded: bool,
) -> str:
    if superseded:
        return "Closed"
    blob = "\n".join(
        [
            fm_raw,
            str(fm.get("overview") or ""),
            "\n".join(line for line in body.splitlines()[:50] if "Status:" in line),
        ]
    )
    if COMPLETE_RE.search(blob):
        return "Closed"
    if stories and all(s["state"] == "Closed" for s in stories):
        return "Closed"
    return "New"


def code_anchors(body: str, limit: int = 12) -> list[str]:
    seen: list[str] = []
    for m in PATH_RE.finditer(body):
        p = m.group(1).rstrip(").,;")
        if p not in seen:
            seen.append(p)
        if len(seen) >= limit:
            break
    return seen


def build_manifest() -> dict[str, Any]:
    readme = (PLANS / "README.md").read_text(encoding="utf-8")
    readme_rows: list[dict[str, Any]] = []
    for m in ROW_RE.finditer(readme):
        readme_rows.append(
            {
                "plan_file": m.group(1).strip(),
                "legacy_ado_type": m.group(2).strip(),
                "title": m.group(3).strip(),
            }
        )

    in_readme = {r["plan_file"] for r in readme_rows}
    extras = sorted(p.name for p in PLANS.glob("*.plan.md") if p.name not in in_readme)
    for name in extras:
        fm, _, _ = split_frontmatter((PLANS / name).read_text(encoding="utf-8"))
        title = str(fm.get("name") or plan_stem(name))
        readme_rows.append(
            {
                "plan_file": name,
                "legacy_ado_type": "Task",
                "title": title,
                "extra": True,
            }
        )

    features: list[dict[str, Any]] = []
    for row in readme_rows:
        path = PLANS / row["plan_file"]
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        fm, body, fm_raw = split_frontmatter(text)

        stories: list[dict[str, str]] = []
        todos = fm.get("todos") if isinstance(fm.get("todos"), list) else None
        if todos:
            for t in todos:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id") or "").strip()
                content = str(t.get("content") or tid).strip()
                st = str(t.get("status") or "pending").lower()
                stories.append(
                    {
                        "id": tid,
                        "title": content,
                        "state": "Closed" if st == "completed" else "New",
                    }
                )
        else:
            for t in parse_todos_regex(fm_raw):
                stories.append(
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "state": "Closed" if t["raw_status"] == "completed" else "New",
                    }
                )

        superseded = "dmp_gene_modeling_modes" in row["plan_file"]
        overview = str(fm.get("overview") or "").strip()
        if superseded:
            overview = (
                overview
                + "\n\nSuperseded by composable-pipeline-flexibility and "
                "docs-refresh-and-guardrails."
            ).strip()

        state = infer_state(fm, fm_raw, body, stories, superseded)
        # Plan rule: Status complete/superseded → Feature Closed and all US Closed
        if state == "Closed":
            for s in stories:
                s["state"] = "Closed"
        features.append(
            {
                "plan_file": f"docs/plans/{row['plan_file']}",
                "plan_stem": plan_stem(row["plan_file"]),
                "title": row["title"],
                "legacy_ado_type": row["legacy_ado_type"],
                "state": state,
                "overview": overview,
                "code_anchors": code_anchors(body + "\n" + fm_raw),
                "stories": stories,
                "superseded": superseded,
            }
        )

    return {
        "organization": "https://dev.azure.com/EpiMethyl",
        "project": "Development",
        "epic": {
            "title": "MethylPipeline platform",
            "description": (
                "Reverse-engineered platform backlog for MethylPipeline. "
                "Features map 1:1 to docs/plans/*.plan.md; User Stories map to plan todos. "
                "Related to historical Epic #283 (package-era backlog) — supersedes that "
                "structure for new work."
            ),
            "related_historical_epic_id": 283,
            "tags": ["methylpipeline-platform"],
        },
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Output YAML path",
    )
    args = parser.parse_args()
    manifest = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    features = manifest["features"]
    n_stories = sum(len(f["stories"]) for f in features)
    n_closed_f = sum(1 for f in features if f["state"] == "Closed")
    n_closed_s = sum(1 for f in features for s in f["stories"] if s["state"] == "Closed")
    print(f"Wrote {args.output}")
    print(f"Features: {len(features)} ({n_closed_f} Closed)")
    print(f"Stories: {n_stories} ({n_closed_s} Closed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Backfill azure_devops work_item_id fields into docs/plans/*.plan.md from seed_state.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLANS = ROOT / "docs" / "plans"
DEFAULT_STATE = HERE / "seed_state.json"
DEFAULT_MANIFEST = HERE / "platform_backlog.yaml"


def extract_frontmatter(text: str) -> tuple[str, str, str]:
    if not text.startswith("---"):
        raise ValueError("missing frontmatter")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError("unclosed frontmatter")
    return text[:3], text[3:end], text[end:]


def upsert_azure_block(fm: str, *, epic_id: int, feature_id: int, title: str) -> str:
    title_yaml = yaml.safe_dump(title, default_style='"', allow_unicode=True).strip()
    block = (
        "azure_devops:\n"
        "  type: Feature\n"
        f"  title: {title_yaml}\n"
        f"  work_item_id: {feature_id}\n"
        f"  epic_id: {epic_id}\n"
    )

    if re.search(r"(?m)^azure_devops:\s*$", fm):
        fm = re.sub(
            r"(?m)^azure_devops:\n(?:^[ \t]+[^\n]*\n)*",
            block,
            fm,
            count=1,
        )
    else:
        # Insert before todos: or at end of frontmatter
        if re.search(r"(?m)^todos:\s*$", fm):
            fm = re.sub(r"(?m)^todos:\s*$", block + "todos:", fm, count=1)
        else:
            fm = fm.rstrip() + "\n" + block
    return fm


def add_todo_work_item_ids(fm: str, story_ids: dict[str, int]) -> str:
    """Insert work_item_id under each todo that has a matching id."""

    m = re.search(r"(?m)^todos:\s*\n", fm)
    if not m:
        return fm
    start = m.end()
    rest = fm[start:]
    end_m = re.search(r"(?m)^[a-zA-Z_][\w]*:", rest)
    todos_body = rest if not end_m else rest[: end_m.start()]
    after = "" if not end_m else rest[end_m.start() :]

    parts = re.split(r"(?m)(?=^[ \t]+-[ \t]+id:)", todos_body)
    new_parts: list[str] = []
    for part in parts:
        if not part.strip():
            new_parts.append(part)
            continue
        tid_m = re.search(r"(?m)^[ \t]+-[ \t]+id:[ \t]*(\S+)", part)
        if not tid_m:
            new_parts.append(part)
            continue
        tid = tid_m.group(1).strip().strip("\"'")
        wid = story_ids.get(tid)
        if wid is None:
            new_parts.append(part)
            continue
        if re.search(r"(?m)^[ \t]+work_item_id:", part):
            part = re.sub(
                r"(?m)^([ \t]+work_item_id:[ \t]*).*$",
                rf"\g<1>{wid}",
                part,
            )
        elif re.search(r"(?m)^[ \t]+status:", part):
            part = re.sub(
                r"(?m)^([ \t]+status:[ \t]*.*)$",
                rf"\1\n    work_item_id: {wid}",
                part,
                count=1,
            )
        elif re.search(r"(?m)^[ \t]+content:", part):
            part = re.sub(
                r"(?m)^([ \t]+content:[ \t]*.*)$",
                rf"\1\n    work_item_id: {wid}",
                part,
                count=1,
            )
        else:
            part = re.sub(
                r"(?m)^([ \t]+-[ \t]+id:[ \t]*.*)$",
                rf"\1\n    work_item_id: {wid}",
                part,
                count=1,
            )
        new_parts.append(part)

    return fm[:start] + "".join(new_parts) + after


def backfill_plan(
    path: Path,
    *,
    epic_id: int,
    feature_id: int,
    title: str,
    story_ids: dict[str, int],
) -> None:
    text = path.read_text(encoding="utf-8")
    prefix, fm, suffix = extract_frontmatter(text)
    fm = upsert_azure_block(fm, epic_id=epic_id, feature_id=feature_id, title=title)
    fm = add_todo_work_item_ids(fm, story_ids)
    path.write_text(prefix + fm + suffix, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = json.loads(args.state.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    epic_id = int(state["epic_id"])
    titles = {f["plan_stem"]: f["title"] for f in manifest["features"]}

    updated = 0
    for stem, feat in state.get("features", {}).items():
        plan_name = f"{stem}.plan.md"
        path = PLANS / plan_name
        if not path.exists():
            print(f"SKIP missing {path}")
            continue
        feature_id = int(feat["work_item_id"])
        story_ids = {k: int(v) for k, v in (feat.get("stories") or {}).items()}
        title = titles.get(stem) or feat.get("title") or stem
        print(f"Backfill {plan_name} Feature AB#{feature_id} ({len(story_ids)} stories)")
        if not args.dry_run:
            backfill_plan(
                path,
                epic_id=epic_id,
                feature_id=feature_id,
                title=title,
                story_ids=story_ids,
            )
        updated += 1
    print(f"Updated {updated} plans (epic AB#{epic_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

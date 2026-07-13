#!/usr/bin/env python3
"""Idempotent Azure DevOps seed for MethylPipeline platform backlog.

Default is dry-run. Pass --apply to create/update work items via `az boards`.

State is persisted in seed_state.json so re-runs skip existing items.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_MANIFEST = HERE / "platform_backlog.yaml"
DEFAULT_STATE = HERE / "seed_state.json"

TAG_PLATFORM = "methylpipeline-platform"
# Azure DevOps System.Title max length
TITLE_MAX = 255


def truncate_title(title: str, limit: int = TITLE_MAX) -> str:
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def run_az(args: list[str], *, apply: bool) -> dict[str, Any] | None:
    cmd = ["az", *args, "-o", "json"]
    if not apply:
        print(f"[dry-run] {' '.join(cmd)}")
        return None
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"az failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wiql_find_by_tag(
    *,
    organization: str,
    project: str,
    work_item_type: str,
    tag: str,
    apply: bool,
) -> int | None:
    """Return first matching work item id for type+tag, or None."""
    # Escape single quotes in tag for WIQL
    safe_tag = tag.replace("'", "''")
    wiql = (
        "SELECT [System.Id] FROM WorkItems "
        f"WHERE [System.TeamProject] = '{project}' "
        f"AND [System.WorkItemType] = '{work_item_type}' "
        f"AND [System.Tags] CONTAINS '{safe_tag}'"
    )
    if not apply:
        print(f"[dry-run] WIQL find {work_item_type} tag={tag}")
        return None
    raw = run_az(
        [
            "boards",
            "query",
            "--wiql",
            wiql,
            "--org",
            organization,
            "--project",
            project,
        ],
        apply=True,
    )
    if not raw:
        return None
    # az boards query returns a list of work items
    if isinstance(raw, list) and raw:
        return int(raw[0].get("id") or raw[0].get("fields", {}).get("System.Id"))
    if isinstance(raw, dict):
        # some versions wrap under workItems
        items = raw.get("workItems") or raw.get("value") or []
        if items:
            return int(items[0].get("id"))
    return None


def format_description(
    *,
    plan_file: str,
    overview: str,
    code_anchors: list[str],
    plan_stem: str,
    extra: str = "",
) -> str:
    anchors = "\n".join(f"- `{p}`" for p in code_anchors) or "- _(none extracted)_"
    parts = [
        f"**Plan:** `{plan_file}`",
        f"**Plan stem:** `{plan_stem}`",
        "",
        overview or "_(no overview)_",
        "",
        "**Code anchors:**",
        anchors,
    ]
    if extra:
        parts.extend(["", extra])
    return "\n".join(parts)


def tags_csv(*tags: str) -> str:
    # Azure DevOps tags are semicolon-separated in System.Tags field
    cleaned = [t.strip() for t in tags if t and t.strip()]
    return "; ".join(cleaned)


def create_work_item(
    *,
    organization: str,
    project: str,
    wit: str,
    title: str,
    description: str,
    tags: str,
    apply: bool,
) -> int | None:
    fields = [f"System.Tags={tags}"]
    result = run_az(
        [
            "boards",
            "work-item",
            "create",
            "--org",
            organization,
            "--project",
            project,
            "--type",
            wit,
            "--title",
            title,
            "--description",
            description,
            "-f",
            *fields,
        ],
        apply=apply,
    )
    if not apply:
        return None
    assert result is not None
    return int(result["id"])


def add_parent_relation(
    *,
    organization: str,
    child_id: int,
    parent_id: int,
    apply: bool,
) -> None:
    run_az(
        [
            "boards",
            "work-item",
            "relation",
            "add",
            "--id",
            str(child_id),
            "--relation-type",
            "parent",
            "--target-id",
            str(parent_id),
            "--org",
            organization,
        ],
        apply=apply,
    )


def add_related(
    *,
    organization: str,
    source_id: int,
    target_id: int,
    apply: bool,
) -> None:
    run_az(
        [
            "boards",
            "work-item",
            "relation",
            "add",
            "--id",
            str(source_id),
            "--relation-type",
            "Related",
            "--target-id",
            str(target_id),
            "--org",
            organization,
        ],
        apply=apply,
    )


def set_state(
    *,
    organization: str,
    work_item_id: int,
    state: str,
    apply: bool,
) -> None:
    if state == "New":
        return
    run_az(
        [
            "boards",
            "work-item",
            "update",
            "--id",
            str(work_item_id),
            "--state",
            state,
            "--org",
            organization,
        ],
        apply=apply,
    )


def ensure_epic(
    *,
    manifest: dict[str, Any],
    state: dict[str, Any],
    apply: bool,
) -> int | None:
    organization = manifest["organization"]
    project = manifest["project"]
    epic_cfg = manifest["epic"]
    if state.get("epic_id"):
        print(f"Epic already in seed_state: AB#{state['epic_id']}")
        return int(state["epic_id"])

    tag = TAG_PLATFORM
    existing = wiql_find_by_tag(
        organization=organization,
        project=project,
        work_item_type="Epic",
        tag=tag,
        apply=apply,
    )
    if existing:
        print(f"Found existing Epic by tag: AB#{existing}")
        state["epic_id"] = existing
        return existing

    epic_id = create_work_item(
        organization=organization,
        project=project,
        wit="Epic",
        title=epic_cfg["title"],
        description=epic_cfg["description"],
        tags=tags_csv(tag, *epic_cfg.get("tags", [])),
        apply=apply,
    )
    if apply and epic_id:
        print(f"Created Epic AB#{epic_id}: {epic_cfg['title']}")
        related = epic_cfg.get("related_historical_epic_id")
        if related:
            try:
                add_related(
                    organization=organization,
                    source_id=epic_id,
                    target_id=int(related),
                    apply=True,
                )
                print(f"Linked Epic AB#{epic_id} Related → AB#{related}")
            except RuntimeError as exc:
                print(f"Warning: could not add Related link to #{related}: {exc}")
        state["epic_id"] = epic_id
    else:
        print(f"[dry-run] would create Epic: {epic_cfg['title']}")
    return epic_id


def ensure_feature(
    *,
    manifest: dict[str, Any],
    state: dict[str, Any],
    feature: dict[str, Any],
    epic_id: int | None,
    apply: bool,
) -> int | None:
    organization = manifest["organization"]
    project = manifest["project"]
    stem = feature["plan_stem"]
    features_state: dict[str, Any] = state.setdefault("features", {})
    entry = features_state.get(stem) or {}
    if entry.get("work_item_id"):
        fid = int(entry["work_item_id"])
        print(f"  Feature cached AB#{fid}: {feature['title']}")
        return fid

    plan_tag = f"plan:{stem}"
    existing = wiql_find_by_tag(
        organization=organization,
        project=project,
        work_item_type="Feature",
        tag=plan_tag,
        apply=apply,
    )
    if existing:
        print(f"  Found Feature by tag {plan_tag}: AB#{existing}")
        features_state[stem] = {
            "work_item_id": existing,
            "title": feature["title"],
            "stories": entry.get("stories") or {},
        }
        return existing

    desc = format_description(
        plan_file=feature["plan_file"],
        overview=feature.get("overview") or "",
        code_anchors=feature.get("code_anchors") or [],
        plan_stem=stem,
        extra="Superseded historical plan." if feature.get("superseded") else "",
    )
    fid = create_work_item(
        organization=organization,
        project=project,
        wit="Feature",
        title=truncate_title(feature["title"]),
        description=desc,
        tags=tags_csv(TAG_PLATFORM, plan_tag),
        apply=apply,
    )
    if apply and fid:
        print(f"  Created Feature AB#{fid}: {feature['title']}")
        if epic_id:
            add_parent_relation(
                organization=organization,
                child_id=fid,
                parent_id=epic_id,
                apply=True,
            )
        set_state(
            organization=organization,
            work_item_id=fid,
            state=feature.get("state") or "New",
            apply=True,
        )
        features_state[stem] = {
            "work_item_id": fid,
            "title": feature["title"],
            "stories": {},
        }
        time.sleep(0.2)
    else:
        print(f"  [dry-run] Feature: {feature['title']} ({feature.get('state')})")
    return fid


def ensure_story(
    *,
    manifest: dict[str, Any],
    state: dict[str, Any],
    feature: dict[str, Any],
    story: dict[str, Any],
    feature_id: int | None,
    apply: bool,
) -> int | None:
    organization = manifest["organization"]
    project = manifest["project"]
    stem = feature["plan_stem"]
    todo_id = story["id"]
    features_state: dict[str, Any] = state.setdefault("features", {})
    entry = features_state.setdefault(
        stem, {"work_item_id": feature_id, "title": feature["title"], "stories": {}}
    )
    stories_state: dict[str, Any] = entry.setdefault("stories", {})
    if stories_state.get(todo_id):
        sid = int(stories_state[todo_id])
        print(f"    Story cached AB#{sid}: {todo_id}")
        return sid

    plan_tag = f"plan:{stem}"
    todo_tag = f"todo:{todo_id}"
    # Prefer state lookup; WIQL by two tags is awkward — use combined unique tag
    unique_tag = f"plan-todo:{stem}/{todo_id}"
    existing = wiql_find_by_tag(
        organization=organization,
        project=project,
        work_item_type="User Story",
        tag=unique_tag,
        apply=apply,
    )
    if existing:
        print(f"    Found Story by tag {unique_tag}: AB#{existing}")
        stories_state[todo_id] = existing
        return existing

    desc = format_description(
        plan_file=feature["plan_file"],
        overview=f"Plan todo `{todo_id}`.\n\n{story.get('title') or ''}",
        code_anchors=feature.get("code_anchors") or [],
        plan_stem=stem,
        extra=f"Tags: `{plan_tag}`, `{todo_tag}`",
    )
    title = story.get("title") or todo_id
    # Keep titles readable; prefix with todo id for uniqueness in Boards
    us_title = truncate_title(f"[{todo_id}] {title}")
    sid = create_work_item(
        organization=organization,
        project=project,
        wit="User Story",
        title=us_title,
        description=desc,
        tags=tags_csv(TAG_PLATFORM, plan_tag, todo_tag, unique_tag),
        apply=apply,
    )
    if apply and sid:
        print(f"    Created User Story AB#{sid}: {us_title[:80]}")
        if feature_id:
            add_parent_relation(
                organization=organization,
                child_id=sid,
                parent_id=feature_id,
                apply=True,
            )
        set_state(
            organization=organization,
            work_item_id=sid,
            state=story.get("state") or "New",
            apply=True,
        )
        stories_state[todo_id] = sid
        time.sleep(0.15)
    else:
        print(f"    [dry-run] US [{todo_id}] {title[:70]} ({story.get('state')})")
    return sid


def seed(*, manifest_path: Path, state_path: Path, apply: bool, regenerate: bool) -> int:
    if regenerate or not manifest_path.exists():
        gen = HERE / "generate_manifest.py"
        subprocess.run(
            [sys.executable, str(gen), "-o", str(manifest_path)],
            check=True,
        )

    if shutil.which("az") is None:
        print("ERROR: az CLI not found", file=sys.stderr)
        return 2

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    state = load_json(state_path)

    features = manifest.get("features") or []
    n_stories = sum(len(f.get("stories") or []) for f in features)
    print(
        f"Manifest: {len(features)} features, {n_stories} stories "
        f"({'APPLY' if apply else 'DRY-RUN'})"
    )

    epic_id = ensure_epic(manifest=manifest, state=state, apply=apply)
    if apply:
        save_json(state_path, state)

    for feature in features:
        fid = ensure_feature(
            manifest=manifest,
            state=state,
            feature=feature,
            epic_id=epic_id,
            apply=apply,
        )
        if apply:
            save_json(state_path, state)
        for story in feature.get("stories") or []:
            ensure_story(
                manifest=manifest,
                state=state,
                feature=feature,
                story=story,
                feature_id=fid,
                apply=apply,
            )
            if apply:
                save_json(state_path, state)

    if apply:
        save_json(state_path, state)
        print(f"Wrote {state_path}")
        print(f"Epic AB#{state.get('epic_id')}")
    else:
        print("Dry-run complete. Re-run with --apply to create work items.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to platform_backlog.yaml",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE,
        help="Path to seed_state.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create/update Azure DevOps work items (default: dry-run)",
    )
    parser.add_argument(
        "--regenerate-manifest",
        action="store_true",
        help="Regenerate platform_backlog.yaml before seeding",
    )
    args = parser.parse_args()
    return seed(
        manifest_path=args.manifest,
        state_path=args.state,
        apply=args.apply,
        regenerate=args.regenerate_manifest,
    )


if __name__ == "__main__":
    raise SystemExit(main())

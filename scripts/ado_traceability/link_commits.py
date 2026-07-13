#!/usr/bin/env python3
"""Link Azure Repos commits to Features and User Stories (ArtifactLink).

Does not rewrite git history. Uses Azure DevOps JSON Patch
(\"Fixed in Commit\") via ``az rest``.

Heuristics
----------
* **Feature:** commits that touch the plan file and concrete ``code_anchors``
  (broad globs like ``packages/*`` are skipped).
* **User Story:** commits that (a) touch paths extracted from the todo title,
  and/or (b) mention the todo id in the commit subject/body.

Default is dry-run; pass ``--apply`` to write links.
"""

from __future__ import annotations

import argparse
import json
import re
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
DEFAULT_LINK_STATE = HERE / "link_state.json"

ORG = "https://dev.azure.com/EpiMethyl"
PROJECT = "Development"
ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"  # Azure DevOps first-party app

PATH_RE = re.compile(
    r"(?:`|\b)((?:packages|workers|workflow_engine|ci|scripts|schemas|contracts|deploy|docs)/[A-Za-z0-9_.${}*-]+(?:/[A-Za-z0-9_./${}*-]+)+)"
)

# Anchors that would attach nearly the whole repo
BROAD_ANCHOR_RE = re.compile(
    r"^(packages|workers|workflow_engine|docs|scripts|ci|schemas)(/\*)?$"
)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check)


def git_repo_ids() -> tuple[str, str]:
    raw = run(
        [
            "az",
            "repos",
            "show",
            "--repository",
            "MethylPipeline",
            "--org",
            ORG,
            "--project",
            PROJECT,
            "-o",
            "json",
        ]
    ).stdout
    data = json.loads(raw)
    return data["project"]["id"], data["id"]


def commit_url(project_id: str, repo_id: str, sha: str) -> str:
    return f"vstfs:///Git/Commit/{project_id}%2F{repo_id}%2F{sha}"


def is_broad_anchor(path: str) -> bool:
    p = path.strip().rstrip("/")
    if BROAD_ANCHOR_RE.match(p):
        return True
    # packages/foo/* at package root is ok; bare packages/* is not
    if p.endswith("/*") and p.count("/") <= 1:
        return True
    return False


def normalize_anchor(path: str) -> str | None:
    p = path.strip().rstrip(").,;`\"'")
    if not p or is_broad_anchor(p):
        return None
    return p


def commits_touching(paths: list[str], *, max_commits: int) -> list[str]:
    usable = [p for p in (normalize_anchor(x) for x in paths) if p]
    if not usable:
        return []
    # git pathspecs: pass as-is (supports globs)
    proc = run(
        ["git", "log", f"--max-count={max_commits}", "--format=%H", "--", *usable],
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def commits_mentioning(todo_id: str, *, max_commits: int) -> list[str]:
    """Commits whose message mentions the todo id (fixed string match)."""
    if not todo_id or len(todo_id) < 3:
        return []
    proc = run(
        [
            "git",
            "log",
            f"--max-count={max_commits}",
            "--format=%H",
            f"--grep={todo_id}",
            "-i",
            "--all-match",
        ],
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        # fallback without --all-match
        proc = run(
            [
                "git",
                "log",
                f"--max-count={max_commits}",
                "--format=%H",
                f"--grep={todo_id}",
                "-i",
            ],
            check=False,
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def paths_from_text(text: str) -> list[str]:
    found: list[str] = []
    for m in PATH_RE.finditer(text or ""):
        p = normalize_anchor(m.group(1))
        if p and p not in found:
            found.append(p)
    return found


def existing_commit_urls(work_item_id: int) -> set[str]:
    proc = run(
        [
            "az",
            "boards",
            "work-item",
            "show",
            "--id",
            str(work_item_id),
            "--org",
            ORG,
            "-o",
            "json",
        ],
        check=False,
    )
    if proc.returncode != 0:
        return set()
    data = json.loads(proc.stdout)
    urls: set[str] = set()
    for rel in data.get("relations") or []:
        if rel.get("rel") == "ArtifactLink" and "Git/Commit" in (rel.get("url") or ""):
            urls.add(rel["url"])
    return urls


def patch_commit_links(
    *,
    work_item_id: int,
    urls: list[str],
    apply: bool,
) -> int:
    if not urls:
        return 0
    ops = [
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "ArtifactLink",
                "url": u,
                "attributes": {"name": "Fixed in Commit"},
            },
        }
        for u in urls
    ]
    body = json.dumps(ops)
    if not apply:
        print(f"  [dry-run] WI {work_item_id}: link {len(urls)} commit(s)")
        return len(urls)
    proc = subprocess.run(
        [
            "az",
            "rest",
            "--method",
            "patch",
            "--url",
            f"{ORG}/{PROJECT}/_apis/wit/workitems/{work_item_id}?api-version=7.1",
            "--resource",
            ADO_RESOURCE,
            "--headers",
            "Content-Type=application/json-patch+json",
            "--body",
            body,
            "-o",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        # Retry one-by-one on batch failure (duplicate link, etc.)
        linked = 0
        for u in urls:
            one = json.dumps(
                [
                    {
                        "op": "add",
                        "path": "/relations/-",
                        "value": {
                            "rel": "ArtifactLink",
                            "url": u,
                            "attributes": {"name": "Fixed in Commit"},
                        },
                    }
                ]
            )
            p2 = subprocess.run(
                [
                    "az",
                    "rest",
                    "--method",
                    "patch",
                    "--url",
                    f"{ORG}/{PROJECT}/_apis/wit/workitems/{work_item_id}?api-version=7.1",
                    "--resource",
                    ADO_RESOURCE,
                    "--headers",
                    "Content-Type=application/json-patch+json",
                    "--body",
                    one,
                    "-o",
                    "none",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if p2.returncode == 0:
                linked += 1
            else:
                err = (p2.stderr or p2.stdout or "").strip()
                if "already exists" in err.lower() or "duplicate" in err.lower():
                    continue
                print(f"  WARN WI {work_item_id}: {err[:200]}", file=sys.stderr)
            time.sleep(0.05)
        return linked
    return len(urls)


def unique(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def link_work_item(
    *,
    work_item_id: int,
    shas: list[str],
    project_id: str,
    repo_id: str,
    apply: bool,
    link_state: dict[str, Any],
    max_per_item: int,
) -> int:
    shas = unique(shas)[:max_per_item]
    if not shas:
        return 0
    key = str(work_item_id)
    already = set(link_state.get("linked", {}).get(key, []))
    existing = already
    if apply:
        existing = existing | existing_commit_urls(work_item_id)
    wanted_urls = [commit_url(project_id, repo_id, s) for s in shas]
    to_add = [u for u in wanted_urls if u not in existing]
    if not to_add:
        print(f"  WI {work_item_id}: already linked ({len(wanted_urls)} candidates)")
        return 0
    n = patch_commit_links(work_item_id=work_item_id, urls=to_add, apply=apply)
    if apply and n:
        linked = link_state.setdefault("linked", {}).setdefault(key, [])
        for u in to_add[:n]:
            # store sha portion
            sha = u.rsplit("%2F", 1)[-1]
            if sha not in linked:
                linked.append(sha)
        print(f"  WI {work_item_id}: linked {n} commit(s)")
        time.sleep(0.15)
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--link-state", type=Path, default=DEFAULT_LINK_STATE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-commits", type=int, default=25)
    parser.add_argument(
        "--feature-stem",
        action="append",
        default=[],
        help="Limit to plan stem(s); default all",
    )
    args = parser.parse_args()

    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    state = json.loads(args.state.read_text(encoding="utf-8"))
    link_state: dict[str, Any] = {}
    if args.link_state.exists():
        link_state = json.loads(args.link_state.read_text(encoding="utf-8"))

    project_id, repo_id = git_repo_ids()
    print(f"Repo {repo_id} project {project_id} ({'APPLY' if args.apply else 'DRY-RUN'})")

    features_by_stem = {f["plan_stem"]: f for f in manifest["features"]}
    stems = args.feature_stem or list(state.get("features", {}).keys())

    total_links = 0
    for stem in stems:
        feat_state = state["features"].get(stem)
        feat_meta = features_by_stem.get(stem)
        if not feat_state or not feat_meta:
            print(f"SKIP {stem}: missing state/manifest")
            continue
        feature_id = int(feat_state["work_item_id"])
        plan_file = feat_meta["plan_file"]
        anchors = list(feat_meta.get("code_anchors") or [])
        feature_paths = [plan_file, *anchors]
        feature_shas = commits_touching(feature_paths, max_commits=args.max_commits)
        print(
            f"Feature {stem} AB#{feature_id}: {len(feature_shas)} commit candidate(s)"
        )
        total_links += link_work_item(
            work_item_id=feature_id,
            shas=feature_shas,
            project_id=project_id,
            repo_id=repo_id,
            apply=args.apply,
            link_state=link_state,
            max_per_item=args.max_commits,
        )
        if args.apply:
            args.link_state.write_text(
                json.dumps(link_state, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        stories_meta = {s["id"]: s for s in feat_meta.get("stories") or []}
        for todo_id, story_wid in (feat_state.get("stories") or {}).items():
            story = stories_meta.get(todo_id) or {"id": todo_id, "title": todo_id}
            title = story.get("title") or todo_id
            story_paths = paths_from_text(title)
            # Always include plan file lightly via message/path; prefer story paths
            shas = commits_touching(story_paths, max_commits=args.max_commits)
            shas += commits_mentioning(todo_id, max_commits=10)
            # If no path/message hits, fall back to plan-file commits only (shared)
            if not shas:
                shas = commits_touching([plan_file], max_commits=min(5, args.max_commits))
            shas = unique(shas)
            print(
                f"  Story [{todo_id}] AB#{story_wid}: "
                f"{len(shas)} candidate(s) paths={story_paths[:3]}"
            )
            total_links += link_work_item(
                work_item_id=int(story_wid),
                shas=shas,
                project_id=project_id,
                repo_id=repo_id,
                apply=args.apply,
                link_state=link_state,
                max_per_item=args.max_commits,
            )
            if args.apply:
                args.link_state.write_text(
                    json.dumps(link_state, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

    # Epic: commits for ado-traceability tooling
    epic_id = state.get("epic_id")
    if epic_id and not args.feature_stem:
        epic_shas = commits_touching(
            [
                "scripts/ado_traceability/",
                "docs/plans/ado-boards-traceability.plan.md",
                "docs/plans/README.md",
            ],
            max_commits=args.max_commits,
        )
        print(f"Epic AB#{epic_id}: {len(epic_shas)} candidate(s)")
        total_links += link_work_item(
            work_item_id=int(epic_id),
            shas=epic_shas,
            project_id=project_id,
            repo_id=repo_id,
            apply=args.apply,
            link_state=link_state,
            max_per_item=args.max_commits,
        )

    if args.apply:
        args.link_state.write_text(
            json.dumps(link_state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.link_state}")
    print(f"Done. Link operations: {total_links}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

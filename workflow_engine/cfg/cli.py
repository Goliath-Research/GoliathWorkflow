"""methyl-cfg: configuration registry CLI (import / upsert / materialize / publish)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_import_paths() -> None:
    root = _repo_root()
    we = root / "workflow_engine"
    for p in (str(root), str(we)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _default_store_dir() -> Path:
    env = os.environ.get("METHYL_CFG_STORE")
    if env:
        return Path(env)
    return Path(os.environ.get("METHYL_WORK_ROOT", "/work")) / "epimethyl" / "cfg-store"


def _open_store(store_dir: Optional[str] = None):
    from cfg.store import FileConfigStore

    return FileConfigStore(store_dir or _default_store_dir())


def _cmd_import_fs(args: argparse.Namespace) -> int:
    from cfg.import_fs import import_filesystem

    store = _open_store(args.store_dir)
    result = import_filesystem(
        store,
        repo_root=args.repo_root or _repo_root(),
        work_root=args.work_root,
        publish=not args.draft,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_upsert(args: argparse.Namespace) -> int:
    store = _open_store(args.store_dir)
    doc = json.loads(Path(args.file).read_text(encoding="utf-8"))
    secret = None
    extra = {}
    if args.kind == "credential":
        secret = doc
        extra = {
            "provider": args.provider or doc.get("provider") or "unknown",
        }
        doc = {
            "provider": extra["provider"],
            "authMode": doc.get("authMode", "unknown"),
        }
    if args.kind == "storage_endpoint" and args.credential_name:
        extra["credentialName"] = args.credential_name
        extra["provider"] = args.provider or doc.get("type") or "unknown"
    if args.kind == "study" and args.study_id:
        extra["studyId"] = args.study_id
    name = args.name or doc.get("name") or doc.get("pipelineProfile") or Path(args.file).stem
    rec = store.upsert(
        args.kind,
        name,
        doc,
        version=args.version,
        status="draft" if args.draft else "published",
        secret=secret,
        extra=extra or None,
    )
    if args.publish:
        rec = store.publish(args.kind, rec.name, rec.version)
    print(
        json.dumps(
            {
                "kind": rec.kind,
                "name": rec.name,
                "version": rec.version,
                "status": rec.status,
                "content_hash": rec.content_hash,
            },
            indent=2,
        )
    )
    return 0


def _cmd_materialize(args: argparse.Namespace) -> int:
    from cfg.materialize import materialize_store

    store = _open_store(args.store_dir)
    result = materialize_store(
        store,
        args.work_root,
        runtime_bundle_domain=args.runtime_bundle_domain,
        site_name=args.site_name,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_publish_program(args: argparse.Namespace) -> int:
    from cfg.publish_program import publish_program

    store = _open_store(args.store_dir)
    db = None
    if args.deploy_db:
        from rest import db_client

        db = db_client.connect()
    result = publish_program(
        store,
        args.name,
        version=args.version,
        repo_root=args.repo_root or _repo_root(),
        work_root=args.work_root,
        deploy_db=args.deploy_db,
        db=db,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def _cmd_sync_actions(args: argparse.Namespace) -> int:
    from cfg.sync_actions import (
        seed_wf_from_catalog,
        sync_actions_from_catalog,
        sync_actions_from_committed_json,
    )

    store = _open_store(args.store_dir)
    repo = args.repo_root or _repo_root()
    if args.from_json:
        result = sync_actions_from_committed_json(store, repo_root=repo, publish=not args.draft)
    else:
        result = sync_actions_from_catalog(store, repo_root=repo, publish=not args.draft)
    if args.seed_wf:
        result["wf_seed"] = seed_wf_from_catalog(repo_root=repo, use_db=True)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_scaffold_action(args: argparse.Namespace) -> int:
    from cfg.scaffold import scaffold_action, upsert_server_action

    store = _open_store(args.store_dir)
    if args.define:
        upsert_server_action(
            store,
            action_name=args.name,
            capability=args.capability or args.name.split(".")[0],
            publish=not args.draft,
        )
    result = scaffold_action(
        store,
        args.name,
        repo_root=args.repo_root or _repo_root(),
        version=args.version,
        force=args.force,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_provision(args: argparse.Namespace) -> int:
    from cfg.provision import (
        provision_all_published,
        provision_asset,
        provision_selected_from_site,
    )

    store = _open_store(args.store_dir)
    if args.selected_only:
        result = provision_selected_from_site(
            store,
            work_root=args.work_root,
            site_name=args.site,
            dry_run=args.dry_run,
        )
    elif args.name:
        result = provision_asset(
            store,
            args.name,
            work_root=args.work_root,
            version=args.version,
            dry_run=args.dry_run,
        )
    else:
        result = provision_all_published(store, args.work_root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_expand_endpoint(args: argparse.Namespace) -> int:
    from cfg.storage_expand import expand_storage_endpoint

    store = _open_store(args.store_dir)
    result = expand_storage_endpoint(
        store, args.name, prefix=args.prefix
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = _open_store(args.store_dir)
    rows = store.list(args.kind, published_only=args.published_only)
    print(
        json.dumps(
            [
                {
                    "name": r.name,
                    "version": r.version,
                    "status": r.status,
                    "content_hash": r.content_hash,
                }
                for r in rows
            ],
            indent=2,
        )
    )
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    store = _open_store(args.store_dir)
    rec = store.get(
        args.kind,
        args.name,
        version=args.version,
        include_secret=args.include_secret,
    )
    if rec is None:
        print(f"not found: {args.kind}/{args.name}", file=sys.stderr)
        return 1
    payload: dict[str, Any] = {
        "kind": rec.kind,
        "name": rec.name,
        "version": rec.version,
        "status": rec.status,
        "content_hash": rec.content_hash,
        "document": rec.document,
        "extra": rec.extra,
    }
    if args.include_secret and rec.secret is not None:
        payload["secret"] = rec.secret
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_set_study_group(args: argparse.Namespace) -> int:
    from cfg.study_membership import set_study_group

    store = _open_store(args.store_dir)
    result = set_study_group(
        store,
        args.study,
        role=args.role,
        label=args.label,
        list_filename=args.list_filename,
        version=args.version,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_set_study_group_members(args: argparse.Namespace) -> int:
    from cfg.study_membership import set_study_group_members

    store = _open_store(args.store_dir)
    members = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(members, dict):
        members = members.get("members") or members.get("items") or []
    result = set_study_group_members(
        store,
        args.study,
        role=args.role,
        label=args.label,
        members=members,
        version=args.version,
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_list_study_groups(args: argparse.Namespace) -> int:
    from cfg.study_membership import list_study_groups

    store = _open_store(args.store_dir)
    print(json.dumps(list_study_groups(store, args.study, version=args.version), indent=2))
    return 0


def _cmd_list_study_group_members(args: argparse.Namespace) -> int:
    from cfg.study_membership import list_study_group_members

    store = _open_store(args.store_dir)
    print(
        json.dumps(
            list_study_group_members(
                store,
                args.study,
                role=args.role,
                label=args.label,
                version=args.version,
            ),
            indent=2,
        )
    )
    return 0


def _cmd_materialize_study_lists(args: argparse.Namespace) -> int:
    from cfg.study_membership import materialize_study_membership

    store = _open_store(args.store_dir)
    result = materialize_study_membership(
        store, args.work_root, study_name=args.study
    )
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="methyl-cfg", description="Configuration registry CLI")
    p.add_argument(
        "--store-dir",
        default=None,
        help="File-backed cfg store (default: $METHYL_CFG_STORE or /work/epimethyl/cfg-store)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("import-fs", help="Import repo/work artifacts into cfg store")
    s.add_argument("--repo-root", default=None)
    s.add_argument("--work-root", default="/work")
    s.add_argument("--draft", action="store_true")
    s.set_defaults(func=_cmd_import_fs)

    s = sub.add_parser("upsert", help="Upsert a JSON document into cfg")
    s.add_argument("kind")
    s.add_argument("--file", required=True)
    s.add_argument("--name", default=None)
    s.add_argument("--version", default="1")
    s.add_argument("--draft", action="store_true")
    s.add_argument("--publish", action="store_true")
    s.add_argument("--credential-name", default=None)
    s.add_argument("--provider", default=None)
    s.add_argument("--study-id", default=None)
    s.set_defaults(func=_cmd_upsert)

    s = sub.add_parser("materialize", help="Write published cfg objects onto /work")
    s.add_argument("--work-root", default="/work")
    s.add_argument("--runtime-bundle-domain", default=None)
    s.add_argument("--site-name", default=None)
    s.set_defaults(func=_cmd_materialize)

    s = sub.add_parser("publish-program", help="Compile DomainProgram and materialize")
    s.add_argument("name")
    s.add_argument("--version", default="1")
    s.add_argument("--repo-root", default=None)
    s.add_argument("--work-root", default="/work")
    s.add_argument("--deploy-db", action="store_true")
    s.set_defaults(func=_cmd_publish_program)

    s = sub.add_parser("sync-actions", help="Sync action catalog into cfg (+ optional wf seed)")
    s.add_argument("--repo-root", default=None)
    s.add_argument("--from-json", action="store_true")
    s.add_argument("--seed-wf", action="store_true")
    s.add_argument("--draft", action="store_true")
    s.set_defaults(func=_cmd_sync_actions)

    s = sub.add_parser("scaffold-action", help="Scaffold client stubs from cfg action")
    s.add_argument("name")
    s.add_argument("--version", default="1")
    s.add_argument("--repo-root", default=None)
    s.add_argument("--define", action="store_true", help="Create scaffolded action_definition first")
    s.add_argument("--capability", default=None)
    s.add_argument("--force", action="store_true")
    s.add_argument("--draft", action="store_true")
    s.set_defaults(func=_cmd_scaffold_action)

    s = sub.add_parser("provision-assets", help="Run reference_asset provision recipes")
    s.add_argument("--name", default=None, help="Asset name (omit to provision all published)")
    s.add_argument("--version", default=None, help="Asset version (with --name)")
    s.add_argument(
        "--selected-only",
        action="store_true",
        help="Provision assets pinned by site reference_selection only",
    )
    s.add_argument("--site", default="default", help="Site name for --selected-only")
    s.add_argument("--work-root", default="/work")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=_cmd_provision)

    s = sub.add_parser("expand-endpoint", help="Expand storage endpoint + credential to wire JSON")
    s.add_argument("name")
    s.add_argument("--prefix", default=None)
    s.set_defaults(func=_cmd_expand_endpoint)

    s = sub.add_parser("list", help="List cfg objects of a kind")
    s.add_argument("kind")
    s.add_argument("--published-only", action="store_true")
    s.set_defaults(func=_cmd_list)

    s = sub.add_parser("get", help="Get one cfg object")
    s.add_argument("kind")
    s.add_argument("name")
    s.add_argument("--version", default=None)
    s.add_argument("--include-secret", action="store_true")
    s.set_defaults(func=_cmd_get)

    s = sub.add_parser(
        "set-study-group",
        help="Define a study analysis group (control/disease) and CSV list filename",
    )
    s.add_argument("study", help="cfg.study name")
    s.add_argument("--role", required=True, choices=["control", "disease"])
    s.add_argument("--label", required=True)
    s.add_argument("--list-filename", required=True, help="e.g. healthy_b.csv")
    s.add_argument("--version", default=None)
    s.set_defaults(func=_cmd_set_study_group)

    s = sub.add_parser(
        "set-study-group-members",
        help="Replace group members from portal.Samples (JSON array)",
    )
    s.add_argument("study")
    s.add_argument("--role", required=True, choices=["control", "disease"])
    s.add_argument("--label", required=True)
    s.add_argument(
        "--file",
        required=True,
        help='JSON array of {portalSampleId, labSampleId?, processingSampleKey?, ...}',
    )
    s.add_argument("--version", default=None)
    s.set_defaults(func=_cmd_set_study_group_members)

    s = sub.add_parser("list-study-groups", help="List analysis groups for a study")
    s.add_argument("study")
    s.add_argument("--version", default=None)
    s.set_defaults(func=_cmd_list_study_groups)

    s = sub.add_parser("list-study-group-members", help="List enrolled samples in a group")
    s.add_argument("study")
    s.add_argument("--role", required=True, choices=["control", "disease"])
    s.add_argument("--label", required=True)
    s.add_argument("--version", default=None)
    s.set_defaults(func=_cmd_list_study_group_members)

    s = sub.add_parser(
        "materialize-study-lists",
        help="Write membership CSVs and sync study sample_paths under /work",
    )
    s.add_argument("--work-root", default="/work")
    s.add_argument("--study", default=None, help="Limit to one study name")
    s.set_defaults(func=_cmd_materialize_study_lists)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    _ensure_import_paths()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

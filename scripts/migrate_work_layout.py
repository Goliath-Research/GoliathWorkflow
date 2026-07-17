#!/usr/bin/env python3
"""
Migrate /work study layout: /work/<disease>/ -> /work/projects/<disease>/.

Phases (operator-controlled):
  preflight (default)  — inventory + manifest, no writes
  --apply-fs           — rsync disease tree (via migrate_work_layout_fs.sh)
  --apply-config       — slim legacy manifests, merge site, archive stray programs/profiles
  --apply-remap        — path_remap study manifests + text artifacts under project tree
  --apply-db           — optional Postgres/MSSQL path REPLACE (requires connection env)
  --verify             — post-migration checks

See docs/deployment/work_layout_migration.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "packages" / "methylvalidation") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "methylvalidation"))

from methyl_validation.path_remap import (  # noqa: E402
    apply_path_remap_to_nested,
    remap_cohort_list_files_in_project,
    remap_path_string,
)

# Import migrate_project_config from scripts/
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from migrate_project_config import migrate_file as migrate_project_file, suggest_profile_name  # noqa: E402

TEXT_SUFFIXES = {".json", ".jsonl", ".csv"}
SKIP_SUFFIXES = {".h5", ".bam", ".fastq", ".fastq.gz", ".tar", ".gz", ".bak", ".legacy.bak"}
PLATFORM_DIRS = ("epimethyl", "samples", "genomes", "cache", "site", "projects")
NON_CANONICAL_CONFIG_GLOBS = ("*.program.json", "*.profile.json")
DEFAULT_GTF = "/work/genomes/annotation/gencode/v49/gencode.v49.annotation.gtf"
SITE_EXAMPLE = REPO_ROOT / "tools/methyl-config-editor/configs/site_grch38.example.json"


@dataclass
class MigrationConfig:
    work_root: Path = Path("/work")
    old_disease_root: Path = Path("/work/prostate-cancer")
    new_disease_root: Path = Path("/work/projects/prostate-cancer")
    site_manifest: Path = Path("/work/site/methyl_site.json")
    path_remap_old: str = "/work/prostate-cancer"
    path_remap_new: str = "/work/projects/prostate-cancer"
    methyl_site_config: str = "/work/site/methyl_site.json"
    worker_env: Path = Path("/work/epimethyl/env/worker.env")
    disease_slug: str = "prostate-cancer"

    def apply_disease_slug(self, slug: str) -> None:
        """Sync disease roots and path-remap prefixes (used by --disease CLI override)."""
        self.disease_slug = slug
        self.old_disease_root = self.work_root / slug
        self.new_disease_root = self.work_root / "projects" / slug
        self.path_remap_old = str(self.old_disease_root)
        self.path_remap_new = str(self.new_disease_root)

    @property
    def path_remap(self) -> Dict[str, str]:
        slug = self.disease_slug
        old = self.path_remap_old.rstrip("/")
        samples_root = str(self.work_root / "samples")
        return {
            old: self.path_remap_new,
            f"{old}/samples": samples_root,
            f"/lambda/nfs/Work/{slug}": self.path_remap_new,
            f"/lambda/nfs/Work/{slug}/samples": samples_root,
        }

    @classmethod
    def from_env_file(cls, path: Path) -> MigrationConfig:
        cfg = cls()
        if not path.is_file():
            return cfg
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key == "WORK_ROOT":
                cfg.work_root = Path(val)
            elif key == "OLD_DISEASE_ROOT":
                cfg.old_disease_root = Path(val)
            elif key == "NEW_DISEASE_ROOT":
                cfg.new_disease_root = Path(val)
            elif key == "SITE_MANIFEST":
                cfg.site_manifest = Path(val)
            elif key == "PATH_REMAP_OLD":
                cfg.path_remap_old = val
            elif key == "PATH_REMAP_NEW":
                cfg.path_remap_new = val
            elif key == "METHYL_SITE_CONFIG":
                cfg.methyl_site_config = val
            elif key == "WORKER_ENV":
                cfg.worker_env = Path(val)
        cfg.disease_slug = cfg.old_disease_root.name
        return cfg


@dataclass
class PreflightReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    config: Dict[str, str] = field(default_factory=dict)
    platform_dirs: Dict[str, bool] = field(default_factory=dict)
    site_manifest_exists: bool = False
    source_exists: bool = False
    dest_exists: bool = False
    source_children: List[str] = field(default_factory=list)
    source_bytes: int = 0
    legacy_step_config_projects: List[str] = field(default_factory=list)
    non_canonical_configs: List[str] = field(default_factory=list)
    files_with_old_prefix: int = 0
    disk_free_bytes: int = 0
    disk_ok: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _dir_size(path: Path, *, timeout_s: int = 120) -> int:
    try:
        out = subprocess.check_output(
            ["du", "-sb", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s,
        )
        return int(out.split()[0])
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError, subprocess.TimeoutExpired):
        return -1


def _count_old_prefix(root: Path, old: str, *, max_files: int = 50_000) -> int:
    try:
        out = subprocess.check_output(
            ["rg", "-l", "--glob", "*.json", "--glob", "*.jsonl", "--glob", "*.csv", old, str(root)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return len(lines)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    n = 0
    for p in _iter_text_files(root):
        try:
            if old in p.read_text(encoding="utf-8", errors="replace"):
                n += 1
        except OSError:
            pass
        if n >= max_files:
            break
    return n


def _disk_free(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def _iter_text_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        if p.suffix.lower() in TEXT_SUFFIXES or p.name.endswith(".legacy.bak"):
            if ".bak" in p.suffixes and p.suffix == ".bak":
                continue
            yield p


def run_preflight(cfg: MigrationConfig) -> PreflightReport:
    report = PreflightReport(
        config={
            "work_root": str(cfg.work_root),
            "old_disease_root": str(cfg.old_disease_root),
            "new_disease_root": str(cfg.new_disease_root),
            "site_manifest": str(cfg.site_manifest),
        }
    )

    for name in PLATFORM_DIRS:
        p = cfg.work_root / name
        report.platform_dirs[name] = p.exists()

    for name in ("epimethyl", "samples", "genomes", "cache"):
        if not report.platform_dirs.get(name):
            report.errors.append(f"missing platform dir: {cfg.work_root / name}")

    report.site_manifest_exists = cfg.site_manifest.is_file()
    report.source_exists = cfg.old_disease_root.is_dir()
    report.dest_exists = cfg.new_disease_root.is_dir()

    if not report.source_exists and not report.dest_exists:
        report.errors.append(f"neither source nor dest disease root exists: {cfg.old_disease_root}")

    scan_root = cfg.new_disease_root if report.dest_exists else cfg.old_disease_root
    if scan_root.is_dir():
        report.source_children = sorted(
            x.name for x in scan_root.iterdir() if x.name not in (".git", ".ipynb_checkpoints")
        )
        report.source_bytes = _dir_size(scan_root)
        configs = scan_root / "configs"
        if configs.is_dir():
            for proj in sorted(configs.glob("project_*.json")):
                if proj.name.endswith(".legacy.bak"):
                    continue
                try:
                    data = json.loads(proj.read_text(encoding="utf-8"))
                    if "step_config" in data:
                        report.legacy_step_config_projects.append(str(proj))
                except (json.JSONDecodeError, OSError):
                    report.warnings.append(f"could not parse {proj}")
            for pattern in NON_CANONICAL_CONFIG_GLOBS:
                for p in configs.glob(pattern):
                    report.non_canonical_configs.append(str(p))

        report.files_with_old_prefix = _count_old_prefix(scan_root, cfg.path_remap_old)

    report.disk_free_bytes = _disk_free(cfg.work_root)
    if report.source_bytes < 0:
        report.warnings.append("could not measure source tree size (du timeout); disk check skipped")
        report.disk_ok = True
    else:
        report.disk_ok = report.disk_free_bytes >= int(report.source_bytes * 1.1)
        if report.source_bytes and not report.disk_ok:
            report.warnings.append(
                f"disk free {report.disk_free_bytes} < 1.1x source size {report.source_bytes}"
            )

    return report


def write_manifest(report: PreflightReport, path: Path) -> None:
    path.write_text(json.dumps(report.__dict__, indent=2) + "\n", encoding="utf-8")


def ensure_site_manifest(cfg: MigrationConfig, *, dry_run: bool) -> List[str]:
    actions: List[str] = []
    if cfg.site_manifest.is_file():
        actions.append(f"site manifest exists: {cfg.site_manifest}")
        return actions

    actions.append(f"would create site manifest at {cfg.site_manifest}")
    if dry_run:
        return actions

    cfg.site_manifest.parent.mkdir(parents=True, exist_ok=True)
    if SITE_EXAMPLE.is_file():
        data = json.loads(SITE_EXAMPLE.read_text(encoding="utf-8"))
        if isinstance(data.get("annotation"), dict):
            data["annotation"]["gtf"] = DEFAULT_GTF
    else:
        data = {
            "reference_genome": {
                "fasta": "/work/genomes/linear/GRCh38/ensembl-114/Homo_sapiens.GRCh38.dna.primary_assembly.fa"
            },
            "annotation": {"gtf": DEFAULT_GTF},
            "methyl_mapper_home": "/work/cache/methyl_mapper",
            "caches": {"string_edges": "/work/cache/methylenricher/string_edges"},
            "actionConfig": {},
        }
    cfg.site_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    actions.append(f"created {cfg.site_manifest}")
    return actions


def apply_config_modernization(cfg: MigrationConfig, *, dry_run: bool) -> List[str]:
    actions: List[str] = []
    root = cfg.new_disease_root if cfg.new_disease_root.is_dir() else cfg.old_disease_root
    configs = root / "configs"
    if not configs.is_dir():
        actions.append(f"skip config: no configs dir at {configs}")
        return actions

    for proj in sorted(configs.glob("project_*.json")):
        if ".legacy.bak" in proj.name:
            continue
        if dry_run:
            try:
                data = json.loads(proj.read_text(encoding="utf-8"))
                if "step_config" in data:
                    actions.append(f"would migrate {proj}")
            except (json.JSONDecodeError, OSError):
                pass
            continue
        rep = migrate_project_file(proj, in_place=True, write_site=cfg.site_manifest)
        actions.append(json.dumps(rep))

    archive_dir = configs / "_archived_non_canonical"
    for pattern in NON_CANONICAL_CONFIG_GLOBS:
        for p in configs.glob(pattern):
            if dry_run:
                actions.append(f"would archive {p} -> {archive_dir}/")
                continue
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / p.name
            shutil.move(str(p), str(dest))
            actions.append(f"archived {p} -> {dest}")

    if not dry_run:
        actions.extend(ensure_worker_env_site_config(cfg, dry_run=False))
    return actions


def ensure_worker_env_site_config(cfg: MigrationConfig, *, dry_run: bool) -> List[str]:
    actions: List[str] = []
    line = f"METHYL_SITE_CONFIG={cfg.methyl_site_config}"
    if not cfg.worker_env.is_file():
        actions.append(f"worker env not found: {cfg.worker_env} (add {line} manually)")
        return actions
    text = cfg.worker_env.read_text(encoding="utf-8")
    if "METHYL_SITE_CONFIG=" in text:
        actions.append(f"worker env already has METHYL_SITE_CONFIG")
        return actions
    actions.append(f"would append {line} to {cfg.worker_env}")
    if dry_run:
        return actions
    if text and not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
    cfg.worker_env.write_text(text, encoding="utf-8")
    actions.append(f"updated {cfg.worker_env}")
    return actions


def _remap_file_content(text: str, path_remap: Dict[str, str]) -> Tuple[str, bool]:
    changed = False
    out = text
    for old, new in sorted(path_remap.items(), key=lambda x: -len(x[0])):
        if old in out:
            out = out.replace(old, new)
            changed = True
    return out, changed


def _should_skip_verify_content(path: Path, old_prefix: str) -> bool:
    if path.suffix == ".bak" or path.name.endswith(".legacy.bak"):
        return True
    if path.parent.name == "_archived_non_canonical":
        return True
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "path_remap" in data:
                pr = data["path_remap"]
                if isinstance(pr, dict) and old_prefix in pr:
                    return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def remap_study_manifests(cfg: MigrationConfig, *, dry_run: bool) -> List[str]:
    actions: List[str] = []
    root = cfg.new_disease_root
    configs = root / "configs"
    if not configs.is_dir():
        return [f"no configs at {configs}"]

    path_remap = cfg.path_remap
    for proj in sorted(configs.glob("project_*.json")):
        if ".legacy.bak" in proj.name:
            continue
        try:
            data = json.loads(proj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            actions.append(f"skip {proj}: {e}")
            continue

        data["output_base"] = str(cfg.new_disease_root)
        existing = data.get("path_remap") if isinstance(data.get("path_remap"), dict) else {}
        merged = dict(existing)
        merged.update(path_remap)
        data["path_remap"] = merged
        apply_path_remap_to_nested(data, path_remap)

        if dry_run:
            actions.append(f"would remap manifest {proj}")
            continue

        bak = proj.with_suffix(proj.suffix + ".pre_layout.bak")
        if not bak.is_file():
            bak.write_text(proj.read_text(encoding="utf-8"), encoding="utf-8")
        remap_cohort_list_files_in_project(data, path_remap, configs)
        proj.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        actions.append(f"remapped {proj}")

    return actions


def remap_artifacts(cfg: MigrationConfig, *, dry_run: bool) -> List[str]:
    actions: List[str] = []
    root = cfg.new_disease_root
    if not root.is_dir():
        return [f"no project root {root}"]

    path_remap = cfg.path_remap
    for p in _iter_text_files(root):
        if p.is_relative_to(root / "configs") and p.name.startswith("project_"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if cfg.path_remap_old not in text:
            continue
        new_text, changed = _remap_file_content(text, path_remap)
        if not changed:
            continue
        if dry_run:
            actions.append(f"would remap {p}")
            continue
        bak = p.with_suffix(p.suffix + ".bak")
        if not bak.is_file():
            bak.write_text(text, encoding="utf-8")
        p.write_text(new_text, encoding="utf-8")
        actions.append(f"remapped {p}")
    return actions


def run_verify(cfg: MigrationConfig) -> int:
    errors: List[str] = []
    root = cfg.new_disease_root
    if not root.is_dir():
        errors.append(f"missing {root}")

    if not cfg.site_manifest.is_file():
        errors.append(f"missing site manifest {cfg.site_manifest}")

    configs = root / "configs"
    if configs.is_dir():
        for proj in configs.glob("project_*.json"):
            if ".legacy.bak" in proj.name or ".pre_layout.bak" in proj.name:
                continue
            try:
                data = json.loads(proj.read_text(encoding="utf-8"))
                if "step_config" in data:
                    errors.append(f"step_config still present: {proj}")
            except (json.JSONDecodeError, OSError):
                errors.append(f"unreadable manifest: {proj}")
        for pattern in NON_CANONICAL_CONFIG_GLOBS:
            stray = list(configs.glob(pattern))
            if stray:
                errors.append(f"non-canonical configs remain: {stray}")

    stale: List[str] = []
    for p in _iter_text_files(root):
        if _should_skip_verify_content(p, cfg.path_remap_old):
            continue
        try:
            if cfg.path_remap_old in p.read_text(encoding="utf-8", errors="replace"):
                stale.append(str(p))
        except OSError:
            pass
    if stale:
        errors.append(f"{len(stale)} files still contain {cfg.path_remap_old} (first 5): {stale[:5]}")

    if errors:
        for e in errors:
            print(f"VERIFY FAIL: {e}", file=sys.stderr)
        return 1
    print("VERIFY OK")
    return 0


def apply_filesystem(cfg: MigrationConfig, *, dry_run: bool, symlink: bool) -> int:
    script = REPO_ROOT / "scripts" / "migrate_work_layout_fs.sh"
    if not script.is_file():
        print(f"missing {script}", file=sys.stderr)
        return 1
    cmd = [
        "bash",
        str(script),
        "--old-root",
        str(cfg.old_disease_root),
        "--new-root",
        str(cfg.new_disease_root),
        "--site-dir",
        str(cfg.site_manifest.parent),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if symlink:
        cmd.append("--symlink")
    return subprocess.call(cmd)


def apply_db(cfg: MigrationConfig, engine: str, *, dry_run: bool) -> int:
    if engine == "postgres":
        sql_path = REPO_ROOT / "workflow_engine/sql_pg/migrate_work_paths_prostate_cancer.sql"
        url = os.environ.get("GATEWAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not url:
            print("set GATEWAY_DATABASE_URL for postgres apply", file=sys.stderr)
            return 1
        if dry_run:
            print(f"would run {sql_path} against postgres (dry-run section only)")
            return 0
        try:
            import psycopg

            sql = sql_path.read_text(encoding="utf-8")
            apply_block = sql.split("-- APPLY")[1] if "-- APPLY" in sql else sql
            with psycopg.connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute(apply_block)
                conn.commit()
            print("postgres migration applied")
            return 0
        except ImportError:
            print("pip install psycopg for --apply-db postgres", file=sys.stderr)
            return 1
    if engine == "mssql":
        sql_path = REPO_ROOT / "workflow_engine/sql_mssql/migrate_work_paths_prostate_cancer.sql"
        print(f"MSSQL: run {sql_path} manually or via sqlcmd (see runbook)", file=sys.stderr)
        return 0 if dry_run else 1
    print(f"unknown engine {engine}", file=sys.stderr)
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disease", default="prostate-cancer", help="Disease slug (default: prostate-cancer)")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Operator env file (default: scripts/migrate_work_layout.env if present, else .example)",
    )
    parser.add_argument("--manifest-out", type=Path, default=Path("migrate_work_layout.manifest.json"))
    parser.add_argument("--verify", action="store_true", help="Post-migration verification only")
    parser.add_argument("--apply-fs", action="store_true", help="Rsync disease tree to /work/projects/...")
    parser.add_argument("--apply-config", action="store_true", help="Slim manifests, site merge, archive stray configs")
    parser.add_argument("--apply-remap", action="store_true", help="Path remap manifests and artifacts")
    parser.add_argument("--apply-db", choices=("postgres", "mssql"), help="Apply DB path migration")
    parser.add_argument("--symlink", action="store_true", help="With --apply-fs, create old->new symlink")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually write changes")
    args = parser.parse_args(argv)

    env_file = args.env_file
    if env_file is None:
        local_env = REPO_ROOT / "scripts/migrate_work_layout.env"
        env_file = local_env if local_env.is_file() else REPO_ROOT / "scripts/migrate_work_layout.env.example"

    cfg = MigrationConfig.from_env_file(env_file)
    if args.disease and cfg.disease_slug != args.disease:
        cfg.apply_disease_slug(args.disease)

    dry_run = not args.no_dry_run

    if args.verify:
        return run_verify(cfg)

    any_apply = args.apply_fs or args.apply_config or args.apply_remap or args.apply_db
    if not any_apply:
        report = run_preflight(cfg)
        write_manifest(report, args.manifest_out)
        print(json.dumps(report.__dict__, indent=2))
        if report.errors:
            return 1
        return 0

    if args.apply_fs:
        rc = apply_filesystem(cfg, dry_run=dry_run, symlink=args.symlink)
        if rc != 0:
            return rc

    if args.apply_config:
        ensure_site_manifest(cfg, dry_run=dry_run)
        for line in apply_config_modernization(cfg, dry_run=dry_run):
            print(line)

    if args.apply_remap:
        for line in remap_study_manifests(cfg, dry_run=dry_run):
            print(line)
        for line in remap_artifacts(cfg, dry_run=dry_run):
            print(line)

    if args.apply_db:
        return apply_db(cfg, args.apply_db, dry_run=dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

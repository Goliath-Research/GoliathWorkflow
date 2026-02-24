#!/usr/bin/env python3
"""
Upload folders listed in a paths file to a remote host via rsync.

Paths in the file are relative to a local base (e.g. /work/david-gladys).
Each line is one folder to sync; directory structure is preserved on the remote.
Resumes safely: re-run after interruption to continue where you left off.

Usage:
  python scripts/rsync_upload_paths.py
  python scripts/rsync_upload_paths.py --dry-run
  python scripts/rsync_upload_paths.py --paths configs/my_paths.txt --remote user@host:Work
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rsync folders from paths file to remote host with progress."
    )
    parser.add_argument(
        "--paths",
        type=Path,
        default=Path("configs/paths.txt"),
        help="File listing one folder path per line (relative to --base). Default: configs/paths.txt",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("/work/david-gladys"),
        help="Local base directory; paths in the file are relative to this. Default: /work/david-gladys",
    )
    parser.add_argument(
        "--remote",
        default="ubuntu@192.222.50.58:Work",
        help="Remote destination (user@host:path). Default: ubuntu@192.222.50.58:Work",
    )
    parser.add_argument(
        "--ssh-key",
        type=Path,
        default=None,
        help="SSH private key for rsync/ssh. Optional.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print rsync commands, do not run them.",
    )
    parser.add_argument(
        "--no-progress2",
        action="store_true",
        help="Disable rsync --info=progress2 (use if output is mangled).",
    )
    parser.add_argument(
        "--show-rsync-output",
        action="store_true",
        help="Let rsync print to terminal (progress bar may be overwritten).",
    )
    args = parser.parse_args()

    base = args.base.resolve()
    paths_file = args.paths.resolve()
    if not paths_file.is_file():
        print(f"Paths file not found: {paths_file}", file=sys.stderr)
        return 1

    # Read and normalize paths: strip whitespace, remove leading ./
    rel_paths: list[str] = []
    with open(paths_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("./"):
                line = line[2:]
            rel_paths.append(line)

    if not rel_paths:
        print("No paths to sync.", file=sys.stderr)
        return 0

    # Resolve full local paths and skip missing
    local_dirs: list[tuple[Path, str]] = []
    for rel in rel_paths:
        local_full = (base / rel).resolve()
        if not local_full.is_dir():
            print(f"Skip (not a directory): {local_full}", file=sys.stderr)
            continue
        local_dirs.append((local_full, rel))

    total = len(local_dirs)
    if total == 0:
        print("No valid directories to sync.", file=sys.stderr)
        return 1

    rsync_cmd_base = [
        "rsync",
        "-av",
        "--info=progress2" if not args.no_progress2 else None,
    ]
    rsync_cmd_base = [x for x in rsync_cmd_base if x is not None]

    ssh_cmd = None
    if args.ssh_key and args.ssh_key.is_file():
        ssh_cmd = f"ssh -i {args.ssh_key}"
    if args.dry_run:
        ssh_cmd = ssh_cmd or "ssh"

    if ssh_cmd:
        rsync_cmd_base.extend(["-e", ssh_cmd])

    failed: list[str] = []
    done = 0
    capture_output = not args.dry_run and not args.show_rsync_output

    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None

    # Use a manual progress bar so we can set suffix (current folder) and advance per folder
    pbar = (
        tqdm(
            total=total,
            desc="Folders",
            unit="folder",
            dynamic_ncols=True,
        )
        if tqdm
        else None
    )

    for i, (local_dir, rel) in enumerate(local_dirs, start=1):
        # Show current folder in progress bar suffix
        if pbar is not None:
            # Keep suffix short: use last path component if path is long
            suffix = Path(rel).name if len(rel) > 40 else rel
            pbar.set_postfix_str(suffix, refresh=True)

        # Remote parent dir so that rsync creates leaf folder there (no trailing slash on dest)
        remote_parent = str(Path(args.remote.rstrip("/")) / Path(rel).parent.as_posix())
        # Source without trailing slash so rsync copies the directory itself (preserves leaf name)
        cmd = rsync_cmd_base + [str(local_dir), f"{remote_parent}/"]

        if args.dry_run:
            done += 1
            if pbar is not None:
                pbar.update(1)
            continue

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
            )
            if result.returncode != 0:
                failed.append(rel)
            else:
                done += 1
            if pbar is not None:
                pbar.update(1)
        except Exception as e:
            print(f"  Error running rsync for {rel}: {e}", file=sys.stderr)
            failed.append(rel)
            if pbar is not None:
                pbar.update(1)

    if pbar is not None:
        pbar.close()

    if failed:
        print(f"\nFailed ({len(failed)}):", file=sys.stderr)
        for r in failed:
            print(f"  {r}", file=sys.stderr)
        return 1
    print(f"\nDone: {done}/{total} folders synced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

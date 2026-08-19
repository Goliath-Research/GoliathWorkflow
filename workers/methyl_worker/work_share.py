"""Make ``/work`` artifacts usable across fleet hosts with different numeric UIDs."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _docker_bin() -> str:
    return shutil.which("docker") or "docker"


def _share_work_path_via_docker(path: Path) -> bool:
    """chmod via Docker as root when the host uid cannot change ownership bits.

    Root-owned (or foreign-uid) artifacts on NFS return EPERM to ``ubuntu``;
    a one-shot ``docker run --user 0`` chmod still works and is how we open
    files for sisters that share the name ``ubuntu`` but not the same uid.
    """
    if not path.exists():
        return False
    mode_flag = "a+rwx" if path.is_dir() else "a+rw"
    parent = str(path.parent.resolve())
    target = str(path.resolve())
    image = (os.environ.get("METHYL_SHARE_CHMOD_IMAGE") or "").strip() or "alpine:3.20"
    cmd = [
        _docker_bin(),
        "run",
        "--rm",
        "--user",
        "0:0",
        "-v",
        f"{parent}:{parent}",
        image,
        "chmod",
        mode_flag,
        target,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("share_work_path docker chmod failed for %s: %s", path, exc)
        return False
    if proc.returncode != 0:
        logger.warning(
            "share_work_path docker chmod rc=%s for %s: %s",
            proc.returncode,
            path,
            (proc.stderr or proc.stdout or "").strip()[:300],
        )
        return False
    return True


def share_work_path(path: Path | str) -> None:
    """Make a ``/work`` artifact usable across fleet hosts with different UIDs.

    Sisters mount the same NFS tree as local users all named ``ubuntu`` but with
    distinct numeric uids. Mode ``0600`` / ``0700`` from one host is unreadable
    on another. Open group/other read-write (files) and rwx (dirs). Falls back
    to Docker-as-root chmod when the local uid cannot change mode.
    """
    p = Path(path)
    try:
        mode = p.stat().st_mode
    except OSError:
        return
    want = 0o777 if p.is_dir() else 0o666
    try:
        p.chmod(mode | want)
        return
    except OSError as exc:
        if _share_work_path_via_docker(p):
            return
        logger.warning("share_work_path chmod failed for %s: %s", p, exc)


def share_work_tree(root: Path | str, *, max_entries: int = 50_000) -> int:
    """``share_work_path`` over a directory tree. Returns number of paths touched."""
    root_p = Path(root)
    if not root_p.exists():
        return 0
    n = 0
    share_work_path(root_p)
    n += 1
    if not root_p.is_dir():
        return n
    for dirpath, dirnames, filenames in os.walk(root_p):
        for name in dirnames:
            share_work_path(Path(dirpath) / name)
            n += 1
            if n >= max_entries:
                return n
        for name in filenames:
            share_work_path(Path(dirpath) / name)
            n += 1
            if n >= max_entries:
                return n
    return n

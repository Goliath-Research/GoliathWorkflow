#!/usr/bin/env python3
"""Fail if any tracked path is invalid on Windows (blocks checkout on Windows clients)."""

from __future__ import annotations

import re
import subprocess
import sys

WIN_INVALID_CHARS = set('<>:"|?*\\')
WIN_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
    re.IGNORECASE,
)


def path_issues(path: str) -> list[str]:
    """Return human-readable issues for a repo-relative POSIX path."""
    issues: list[str] = []
    if any(ord(c) < 32 for c in path):
        issues.append("contains control characters")
    if any(c in WIN_INVALID_CHARS for c in path):
        issues.append('contains Windows-invalid characters (< > : " | ? * \\)')
    for segment in path.split("/"):
        if not segment:
            continue
        if segment.endswith(" ") or segment.endswith("."):
            issues.append(f"segment {segment!r} has trailing space or dot")
        if WIN_RESERVED.match(segment.split(".")[0]):
            issues.append(f"reserved Windows device name {segment!r}")
    return issues


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    raw = result.stdout.decode("utf-8", "surrogateescape")
    return [p for p in raw.split("\0") if p]


def main() -> int:
    paths = tracked_paths()
    violations: list[tuple[str, list[str]]] = []
    for path in paths:
        issues = path_issues(path)
        if issues:
            violations.append((path, issues))

    if violations:
        print("Windows path check failed:", file=sys.stderr)
        for path, issues in violations:
            display = path if path.isprintable() else repr(path)
            detail = "; ".join(issues)
            print(f"  {display}: {detail}", file=sys.stderr)
        print(
            f"\n{len(violations)} path(s) would break git checkout on Windows.",
            file=sys.stderr,
        )
        return 1

    print(f"Windows path check passed ({len(paths)} tracked paths).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail when package install metadata / packages.list can break pip or CI bootstrap.

Checks:
1. Declared README paths exist for every packages/*/pyproject.toml.
2. Poetry path-dependency keys canonicalize to the target package distribution name.
3. Local bare PEP 621 dependencies appear in scripts/packages.list before the dependent.
4. Required deploy/env example templates exist (doc-freshness companion).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"
PACKAGES_LIST = REPO_ROOT / "scripts" / "packages.list"
REQUIRED_ENV_EXAMPLES = (
    "deploy/env/gateway.postgres.env.example",
    "deploy/env/gateway.mssql.env.example",
    "deploy/env/worker.env.example",
)


def canonicalize_name(name: str) -> str:
    """PEP 503 / packaging canonicalize_name."""
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def _load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _dist_name(data: dict[str, Any], folder: str) -> str:
    poetry = (data.get("tool") or {}).get("poetry") or {}
    project = data.get("project") or {}
    return str(poetry.get("name") or project.get("name") or folder)


def _readme_rel(data: dict[str, Any]) -> str | None:
    poetry = (data.get("tool") or {}).get("poetry") or {}
    project = data.get("project") or {}
    readme = poetry.get("readme") or project.get("readme")
    if readme is None:
        return None
    if isinstance(readme, dict):
        return str(readme.get("file") or "") or None
    return str(readme)


def _poetry_path_deps(data: dict[str, Any]) -> list[tuple[str, str]]:
    poetry = (data.get("tool") or {}).get("poetry") or {}
    deps = poetry.get("dependencies") or {}
    out: list[tuple[str, str]] = []
    for key, val in deps.items():
        if key == "python" or not isinstance(val, dict):
            continue
        path = val.get("path")
        if path:
            out.append((str(key), str(path)))
    return out


def _pep621_bare_deps(data: dict[str, Any]) -> list[str]:
    project = data.get("project") or {}
    deps = project.get("dependencies") or []
    names: list[str] = []
    for dep in deps:
        if not isinstance(dep, str):
            continue
        # Strip PEP 508 extras/markers/versions and direct references.
        if "@" in dep:
            continue
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", dep)
        if m:
            names.append(m.group(1))
    return names


def load_packages_list(path: Path = PACKAGES_LIST) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def check_package_install_contract(root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    packages_dir = root / "packages"
    list_path = root / "scripts" / "packages.list"

    folder_to_dist: dict[str, str] = {}
    dist_canon_to_folder: dict[str, str] = {}
    pyprojects: dict[str, dict[str, Any]] = {}

    for pyproject in sorted(packages_dir.glob("*/pyproject.toml")):
        folder = pyproject.parent.name
        data = _load_toml(pyproject)
        pyprojects[folder] = data
        dist = _dist_name(data, folder)
        folder_to_dist[folder] = dist
        dist_canon_to_folder[canonicalize_name(dist)] = folder

        readme = _readme_rel(data)
        if readme:
            readme_path = pyproject.parent / readme
            if not readme_path.is_file():
                errors.append(f"{folder}: missing declared readme {readme!r}")

        for key, rel_path in _poetry_path_deps(data):
            target_dir = (pyproject.parent / rel_path).resolve()
            try:
                target_folder = target_dir.relative_to((root / "packages").resolve()).parts[0]
            except ValueError:
                # Path dep outside packages/ (unusual); skip name check.
                continue
            target_toml = root / "packages" / target_folder / "pyproject.toml"
            if not target_toml.is_file():
                errors.append(
                    f"{folder}: path dep {key!r} -> {rel_path!r} has no pyproject.toml"
                )
                continue
            target_dist = folder_to_dist.get(target_folder)
            if target_dist is None:
                target_dist = _dist_name(_load_toml(target_toml), target_folder)
                folder_to_dist[target_folder] = target_dist
                dist_canon_to_folder[canonicalize_name(target_dist)] = target_folder
            if canonicalize_name(key) != canonicalize_name(target_dist):
                errors.append(
                    f"{folder}: path-dep key {key!r} does not match target dist "
                    f"name {target_dist!r} (pip 26 rejects inconsistent names)"
                )

    if not list_path.is_file():
        errors.append("missing scripts/packages.list")
        return errors

    order = load_packages_list(list_path)
    order_index = {name: i for i, name in enumerate(order)}

    for folder, data in pyprojects.items():
        if folder not in order_index:
            # Not every package must be on the host install list (e.g. experimental),
            # but bare local deps below only apply when the dependent is listed.
            continue
        for dep_name in _pep621_bare_deps(data):
            dep_folder = dist_canon_to_folder.get(canonicalize_name(dep_name))
            if dep_folder is None or dep_folder == folder:
                continue
            if dep_folder not in order_index:
                errors.append(
                    f"{folder}: bare dep {dep_name!r} resolves to local package "
                    f"{dep_folder!r} which is not in packages.list"
                )
                continue
            if order_index[dep_folder] >= order_index[folder]:
                errors.append(
                    f"packages.list order: {dep_folder!r} (provides {dep_name!r}) "
                    f"must appear before {folder!r}"
                )

    for rel in REQUIRED_ENV_EXAMPLES:
        if not (root / rel).is_file():
            errors.append(f"missing required env example: {rel}")

    return errors


def main(argv: list[str] | None = None) -> int:
    del argv
    errors = check_package_install_contract()
    if not errors:
        print("Package install contract OK.")
        return 0
    print("Package install contract violations:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

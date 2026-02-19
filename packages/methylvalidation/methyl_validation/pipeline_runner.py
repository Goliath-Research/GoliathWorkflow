"""
Run pipeline steps (methyl-centroid, methyl-detector, methyl-classifier, methyl-validator) via subprocess.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def _find_cmd(name: str) -> Optional[str]:
    """Return path to CLI command if available."""
    return shutil.which(name)


def run_cmd(
    cmd: List[str],
    cwd: Optional[str | Path] = None,
    env: Optional[dict] = None,
) -> tuple[int, str, str]:
    """
    Run a command. Returns (returncode, stdout_str, stderr_str).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env={**(env or {})} if env else None,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except FileNotFoundError as e:
        return -1, "", str(e)
    except Exception as e:
        return -1, "", str(e)


def run_centroid(project_json: str | Path) -> tuple[int, str, str]:
    """Run methyl-centroid --project <project_json> --group all."""
    cmd = ["methyl-centroid", "--project", str(project_json), "--group", "all"]
    return run_cmd(cmd)


def run_detector(project_json: str | Path, per_cancer_group: bool = False) -> tuple[int, str, str]:
    """Run methyl-detector --project <project_json> [--per-cancer-group]. For binary single comparison, --per-cancer-group is optional."""
    cmd = ["methyl-detector", "--project", str(project_json)]
    if per_cancer_group:
        cmd.append("--per-cancer-group")
    return run_cmd(cmd)


def run_classifier(project_json: str | Path, per_cancer_group: bool = False) -> tuple[int, str, str]:
    """Run methyl-classifier --project <project_json> [--per-cancer-group]."""
    cmd = ["methyl-classifier", "--project", str(project_json)]
    if per_cancer_group:
        cmd.append("--per-cancer-group")
    return run_cmd(cmd)


def run_validator(
    project_json: str | Path,
    test_control_csv: str | Path,
    test_disease_csv: str | Path,
    output_dir: str | Path,
) -> tuple[int, str, str]:
    """Run methyl-validator with project and override test sets and output dir."""
    cmd = [
        "methyl-validator",
        "--project", str(project_json),
        "--test-control", str(test_control_csv),
        "--test-disease", str(test_disease_csv),
        "--output-dir", str(output_dir),
    ]
    return run_cmd(cmd)


def run_pipeline_for_iteration(
    project_json: Path,
    val_control_csv: Path,
    val_disease_csv: Path,
    validator_output_dir: Path,
    per_cancer_group: bool = False,
) -> tuple[bool, List[str]]:
    """
    Run centroid -> detector -> classifier -> validator in order.
    Returns (success, list of error messages).
    """
    errors: List[str] = []
    steps = [
        ("methyl-centroid", lambda: run_centroid(project_json)),
        ("methyl-detector", lambda: run_detector(project_json, per_cancer_group=per_cancer_group)),
        ("methyl-classifier", lambda: run_classifier(project_json, per_cancer_group=per_cancer_group)),
        (
            "methyl-validator",
            lambda: run_validator(
                project_json,
                val_control_csv,
                val_disease_csv,
                validator_output_dir,
            ),
        ),
    ]
    for step_name, run_fn in steps:
        rc, out, err = run_fn()
        if rc != 0:
            msg = f"{step_name} failed (exit {rc}). stderr: {err[:500] if err else 'none'}"
            errors.append(msg)
            return False, errors
    return True, []

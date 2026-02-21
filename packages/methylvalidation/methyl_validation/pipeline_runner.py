"""
Run pipeline steps (methyl-centroid, methyl-detector, methyl-classifier, methyl-predictor) via subprocess.
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional


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


def run_predictor(
    project_json: str | Path,
    test_control_csv: str | Path,
    test_disease_csv: str | Path,
    output_dir: str | Path,
) -> tuple[int, str, str]:
    """Run methyl-predictor with project and override test sets and output dir."""
    cmd = [
        "methyl-predictor",
        "--project", str(project_json),
        "--test-control", str(test_control_csv),
        "--test-disease", str(test_disease_csv),
        "--output-dir", str(output_dir),
    ]
    return run_cmd(cmd)


def _write_step_log(log_path: Path, stdout: str, stderr: str) -> None:
    """Write combined stdout and stderr to a single log file with delimiters."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== stdout ===\n")
        f.write(stdout)
        if stdout and not stdout.endswith("\n"):
            f.write("\n")
        f.write("\n=== stderr ===\n")
        f.write(stderr)
        if stderr and not stderr.endswith("\n"):
            f.write("\n")


def run_pipeline_for_iteration(
    project_json: Path,
    val_control_csv: Path,
    val_disease_csv: Path,
    predictor_output_dir: Path,
    per_cancer_group: bool = False,
    logs_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
) -> tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Run centroid -> detector -> classifier -> predictor in order.
    If logs_dir is set, create it and write each step's stdout+stderr to logs_dir/<step_name>.log,
    and write step_timings.csv to logs_dir.parent (run_dir).
    If progress_callback is set, call it with (step_index, step_name, "start") before each step
    and (step_index, step_name, "end") after each step.
    Returns (success, list of error messages, list of step timing dicts with step_name, duration_seconds, return_code).
    """
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
        ("methyl-centroid", lambda: run_centroid(project_json)),
        ("methyl-detector", lambda: run_detector(project_json, per_cancer_group=per_cancer_group)),
        ("methyl-classifier", lambda: run_classifier(project_json, per_cancer_group=per_cancer_group)),
        (
            "methyl-predictor",
            lambda: run_predictor(
                project_json,
                val_control_csv,
                val_disease_csv,
                predictor_output_dir,
            ),
        ),
    ]
    for step_index, (step_name, run_fn) in enumerate(steps):
        if progress_callback is not None:
            progress_callback(step_index, step_name, "start")
        t0 = time.perf_counter()
        rc, out, err = run_fn()
        duration_seconds = time.perf_counter() - t0
        if progress_callback is not None:
            progress_callback(step_index, step_name, "end")
        step_timings.append({
            "step_name": step_name,
            "duration_seconds": round(duration_seconds, 6),
            "return_code": rc,
        })
        if logs_dir is not None:
            log_path = logs_dir / f"{step_name}.log"
            _write_step_log(log_path, out, err)
        if rc != 0:
            msg = f"{step_name} failed (exit {rc}). stderr: {err[:500] if err else 'none'}"
            errors.append(msg)
            if logs_dir is not None:
                write_step_timings_csv(step_timings, logs_dir.parent / "step_timings.csv")
            return False, errors, step_timings
    if logs_dir is not None:
        write_step_timings_csv(step_timings, logs_dir.parent / "step_timings.csv")
    return True, [], step_timings

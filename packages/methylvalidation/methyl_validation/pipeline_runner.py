"""
Orchestrate pipeline CLIs via subprocess.

Monte Carlo iterations run **methyl-centroid** and **methyl-detector** only; **--freeze** runs
mapper/enricher; **--model** runs classifier then predictor.
"""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple


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


def run_centroid(
    project_json: str | Path,
    centroid_step_overrides: Optional[Dict[str, str | Path]] = None,
) -> tuple[int, str, str]:
    """
    Run methyl-centroid for one or both cohorts.

    When group-specific step overrides are provided, runs group1 and group2 separately so
    each cohort can receive its own samples/add_samples/remove_samples delta payload.
    """
    if not centroid_step_overrides:
        cmd = ["methyl-centroid", "--project", str(project_json), "--group", "all"]
        return run_cmd(cmd)

    stdout_parts: List[str] = []
    stderr_parts: List[str] = []
    for group in ("group1", "group2"):
        override = centroid_step_overrides.get(group)
        cmd = ["methyl-centroid", "--project", str(project_json), "--group", group]
        if override is not None:
            cmd.extend(["--step-override", str(override)])
        rc, out, err = run_cmd(cmd)
        stdout_parts.append(f"=== {group} stdout ===\n{out}")
        stderr_parts.append(f"=== {group} stderr ===\n{err}")
        if rc != 0:
            return rc, "\n".join(stdout_parts), "\n".join(stderr_parts)

    return 0, "\n".join(stdout_parts), "\n".join(stderr_parts)


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


def run_mapper(project_json: str | Path, per_cancer_group: bool = False) -> tuple[int, str, str]:
    """Run methyl-mapper --project <project_json> [--per-cancer-group]."""
    cmd = ["methyl-mapper", "--project", str(project_json)]
    if per_cancer_group:
        cmd.append("--per-cancer-group")
    return run_cmd(cmd)


def run_enricher(project_json: str | Path, per_cancer_group: bool = False) -> tuple[int, str, str]:
    """Run methyl-enricher --project <project_json> [--per-cancer-group]."""
    cmd = ["methyl-enricher", "--project", str(project_json)]
    if per_cancer_group:
        cmd.append("--per-cancer-group")
    return run_cmd(cmd)


def _progression_settings(project_json: str | Path) -> Dict[str, Any]:
    """Read progression step settings from project.json."""
    try:
        from methyl_utils import load_project
    except Exception:
        return {}
    try:
        project = load_project(project_json)
        return project.get_step_config("progression") or {}
    except Exception:
        return {}


def run_progression(project_json: str | Path) -> tuple[int, str, str]:
    """Run methyl-disease-progression --project <project_json> with optional step_config args."""
    cfg = _progression_settings(project_json)
    cmd = ["methyl-disease-progression", "--project", str(project_json)]
    out_dir = cfg.get("output_dir")
    if out_dir:
        cmd.extend(["--output-dir", str(out_dir)])
    ordered = cfg.get("ordered_comparison_labels") or cfg.get("ordered_disease_groups")
    if isinstance(ordered, list) and ordered:
        cmd.extend(["--ordered-comparison-labels", ",".join(str(x) for x in ordered)])
    if bool(cfg.get("strict_missing", False)):
        cmd.append("--strict-missing")
    if bool(cfg.get("report_md", False)):
        cmd.append("--report-md")
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


def run_predictor_multiclass(
    project_json: str | Path,
    test_groups_json: str | Path,
    output_dir: str | Path,
) -> tuple[int, str, str]:
    """Run methyl-predictor for flat multiclass: ``--test-groups`` JSON (list of {label, paths})."""
    cmd = [
        "methyl-predictor",
        "--project", str(project_json),
        "--test-groups", str(test_groups_json),
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
    centroid_step_overrides: Optional[Dict[str, Path]] = None,
    config: Optional[Any] = None,  # reserved; mapper/enricher belong to --freeze, not MC
) -> tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Monte Carlo stability iteration: methyl-centroid → methyl-detector only.

    Omits methyl-classifier and methyl-predictor (final model is ``--model`` after freeze).
    ``val_*`` and ``predictor_output_dir`` are kept for API compatibility with the CLI loop;
    they are not used by this runner.
    """
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
        (
            "methyl-centroid",
            lambda: run_centroid(project_json, centroid_step_overrides=centroid_step_overrides),
        ),
        ("methyl-detector", lambda: run_detector(project_json, per_cancer_group=per_cancer_group)),
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


def run_predictor_only_binary(
    project_json: Path,
    val_control_csv: Path,
    val_disease_csv: Path,
    predictor_output_dir: Path,
    logs_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
) -> tuple[bool, List[str], List[Dict[str, Any]]]:
    """Only methyl-predictor (frozen model paths must already be wired in project.json)."""
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
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


def run_predictor_only_multiclass(
    project_json: Path,
    test_groups_json: Path,
    predictor_output_dir: Path,
    logs_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
) -> tuple[bool, List[str], List[Dict[str, Any]]]:
    """Only methyl-predictor for multiclass (frozen model paths in project.json)."""
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
        (
            "methyl-predictor",
            lambda: run_predictor_multiclass(
                project_json,
                test_groups_json,
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


def run_pipeline_for_production(
    project_json: Path,
    logs_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
    config: Optional[Any] = None,
) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Production freeze build: centroid -> detector (fixed_dmp_panel) -> mapper -> enricher.
    Does not run methyl-classifier or methyl-predictor; use --model to run classifier and predictor sequentially.
    """
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
        ("methyl-centroid", lambda: run_centroid(project_json, centroid_step_overrides=None)),
        ("methyl-detector", lambda: run_detector(project_json, per_cancer_group=False)),
        ("methyl-mapper", lambda: run_mapper(project_json, per_cancer_group=False)),
    ]
    skip_enricher = config is not None and getattr(config, "skip_enricher", False)
    progression_cfg = _progression_settings(project_json)
    progression_enabled = bool(progression_cfg.get("enabled", False))
    if not skip_enricher:
        steps.append(
            ("methyl-enricher", lambda: run_enricher(project_json, per_cancer_group=False)),
        )
        if progression_enabled:
            steps.append(
                ("methyl-disease-progression", lambda: run_progression(project_json)),
            )

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


def run_pipeline_for_iteration_multiclass(
    project_json: Path,
    test_groups_json: Path,
    predictor_output_dir: Path,
    per_cancer_group: bool = False,
    logs_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
    config: Optional[Any] = None,
) -> tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Monte Carlo stability iteration (multiclass template): methyl-centroid → methyl-detector only.

    ``test_groups_json`` / ``predictor_output_dir`` are unused (kept for CLI compatibility).
    """
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps = [
        ("methyl-centroid", lambda: run_centroid(project_json, centroid_step_overrides=None)),
        ("methyl-detector", lambda: run_detector(project_json, per_cancer_group=per_cancer_group)),
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


def run_predictor_from_project(
    project_json: str | Path,
    output_dir: Optional[str | Path] = None,
) -> tuple[int, str, str]:
    """
    Run ``methyl-predictor --project`` using cohorts from ``step_config.predictor``.
    With control/disease comparisons, the predictor CLI auto-enables per-comparison runs.
    """
    cmd = ["methyl-predictor", "--project", str(project_json)]
    if output_dir is not None:
        cmd.extend(["--output-dir", str(output_dir)])
    return run_cmd(cmd)


def run_pipeline_for_model(
    project_json: Path,
    logs_dir: Optional[Path] = None,
    predictor_output_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, str, Literal["start", "end"]], None]] = None,
    per_cancer_group: bool = False,
) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Production model step after freeze: methyl-classifier → methyl-predictor.

    Predictor resolves test sets from the production ``project.json`` (and optional
    ``--output-dir`` when ``predictor_output_dir`` is set).
    """
    from .validator_metrics import write_step_timings_csv

    errors: List[str] = []
    step_timings: List[Dict[str, Any]] = []
    steps: List[Tuple[str, Callable[[], tuple[int, str, str]]]] = [
        ("methyl-classifier", lambda: run_classifier(project_json, per_cancer_group=per_cancer_group)),
        (
            "methyl-predictor",
            lambda: run_predictor_from_project(project_json, predictor_output_dir),
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

"""Packaging and import-path tests for methyl-study-start admin CLI."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

WF_ENGINE = Path(__file__).resolve().parents[1]


def test_admin_package_importable_from_workflow_engine_on_path():
    if str(WF_ENGINE) not in sys.path:
        sys.path.insert(0, str(WF_ENGINE))
    mod = importlib.import_module("admin.study_start")
    assert callable(mod.main)


def test_plan_iterations_imports_methyl_domain_without_pip_install(monkeypatch):
    """ensure_import_paths must expose methyl_domain before workflow_planner import."""
    for key in list(sys.modules):
        if key.startswith("methyl_validation") or key.startswith("methyl_domain"):
            monkeypatch.delitem(sys.modules, key, raising=False)

    if str(WF_ENGINE) not in sys.path:
        sys.path.insert(0, str(WF_ENGINE))

    from admin._paths import ensure_import_paths

    ensure_import_paths()
    import methyl_validation.workflow_planner  # noqa: F401


def test_cmd_compile_stdout_and_file_emit_same_raw_spec(tmp_path: Path, monkeypatch):
    """Stdout and -o must both write the raw compiled spec (not {"spec": ...})."""
    if str(WF_ENGINE) not in sys.path:
        sys.path.insert(0, str(WF_ENGINE))

    from admin.study_start import cmd_compile

    fake_spec = {"name": "Demo", "root_node_key": "root", "nodes": []}
    out_file = tmp_path / "compiled.json"
    program = tmp_path / "demo.program.json"
    program.write_text("{}", encoding="utf-8")

    with patch("ops.study_lifecycle.compile_program_spec", return_value=fake_spec):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        assert cmd_compile(Namespace(program=str(program), project_path=None, output=None)) == 0
        stdout_payload = json.loads(buf.getvalue())

        assert cmd_compile(
            Namespace(program=str(program), project_path=None, output=str(out_file))
        ) == 0
        file_payload = json.loads(out_file.read_text(encoding="utf-8"))

    assert stdout_payload == fake_spec
    assert file_payload == fake_spec
    assert "spec" not in stdout_payload or stdout_payload.get("name") == "Demo"


def test_built_wheel_includes_admin_and_ops_packages(tmp_path: Path):
    build = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(WF_ENGINE), "-w", str(tmp_path), "--no-deps"],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr

    wheels = list(tmp_path.glob("methyl_gateway-*.whl"))
    assert wheels, "expected methyl-gateway wheel"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = set(zf.namelist())
    assert "admin/study_start.py" in names
    assert "admin/study_lifecycle.py" in names
    assert "admin/sample_lifecycle.py" in names
    assert "ops/study_lifecycle.py" in names
    assert "ops/workflow_deploy.py" in names

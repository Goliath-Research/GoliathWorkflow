"""Platform deploy script contracts (DB twins, gateway, worker provision)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bash_n(name: str) -> None:
    path = REPO_ROOT / "scripts" / name
    subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)


def test_platform_deploy_scripts_bash_syntax() -> None:
    for name in (
        "bootstrap_distributed_workers.sh",
        "provision_gateway_node.sh",
        "provision_worker_node.sh",
        "install_gateway_systemd.sh",
        "install_reclaim_leases_timer.sh",
        "verify_e2e_node.sh",
        "write_worker_env.sh",
    ):
        _bash_n(name)


def test_bootstrap_rejects_worker_register() -> None:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/bootstrap_distributed_workers.sh"), "--register-worker"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "not part of database bootstrap" in proc.stderr


def test_provision_worker_rejects_sql_register_flag() -> None:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/provision_worker_node.sh"), "--register-worker"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "not allowed" in proc.stderr


def test_bootstrap_is_privileged_host_only() -> None:
    text = (REPO_ROOT / "scripts/bootstrap_distributed_workers.sh").read_text(
        encoding="utf-8"
    )
    assert "init_work_layout.sh" not in text
    assert "sync_cfg_profiles_and_action_catalog.py" in text
    assert "sync-library-presets" in text
    assert "deploy_process_pack_catalog.sh" in text
    assert "POSTGRES_DB:-${PGDATABASE:-goliath}" in text or "goliath" in text


def test_provision_worker_auto_detects_join_mode() -> None:
    text = (REPO_ROOT / "scripts/provision_worker_node.sh").read_text(encoding="utf-8")
    assert 'JOIN_MODE="auto"' in text
    assert "Auto-detected join-mode=" in text
    assert "register_worker.sh" not in text
    assert "--skip-parabricks-pull" in text
    assert "venv-$ARCH" in text
    assert "init_work_layout.sh" in text
    assert "live_api_base" in text
    join_idx = text.rfind('if [[ "$JOIN_MODE" == "join" ]]; then')
    assert join_idx > 0
    join_body = text[join_idx : text.find("else", join_idx)]
    assert join_body.find("do_host_and_docker") < join_body.find("do_enroll")
    layout_idx = text.find("=== Shared /work layout (first worker) ===")
    preflight_idx = text.find("=== Preflight ===")
    assert 0 < layout_idx < preflight_idx


def test_register_worker_sql_is_opt_in() -> None:
    text = (REPO_ROOT / "scripts/register_worker.py").read_text(encoding="utf-8")
    assert "METHYL_ALLOW_WORKER_SQL" in text
    assert "Direct-DB register is disabled on GPU workers" in text


def test_gateway_installers_reject_work_share() -> None:
    gw = (REPO_ROOT / "scripts/install_gateway_systemd.sh").read_text(encoding="utf-8")
    reclaim = (REPO_ROOT / "scripts/install_reclaim_leases_timer.sh").read_text(
        encoding="utf-8"
    )
    provision = (REPO_ROOT / "scripts/provision_gateway_node.sh").read_text(
        encoding="utf-8"
    )
    needle = 'ROOT" == /work'
    assert needle in gw and needle in reclaim and needle in provision


def test_gateway_provision_has_no_work_share() -> None:
    text = (REPO_ROOT / "scripts/provision_gateway_node.sh").read_text(encoding="utf-8")
    assert "/opt/methyl-gateway" in text
    assert "Does not mount or write /work" in text
    assert "parabricks" not in text.lower()
    unit = (REPO_ROOT / "deploy/systemd/methyl-gateway.service").read_text(encoding="utf-8")
    assert "__GOLIATH_ROOT__" in unit
    assert "/work/goliath" not in unit


def test_write_worker_env_omits_placeholder_api_base() -> None:
    text = (REPO_ROOT / "scripts/write_worker_env.sh").read_text(encoding="utf-8")
    assert "gateway.example.com" not in text
    assert "read_existing_worker_api_base" in text
    assert 'WORKER_API_BASE="${WORKER_API_BASE:-}"' in text


def test_worker_units_create_samtools_tmpdir() -> None:
    for rel in (
        "deploy/systemd/methyl-worker.service",
        "deploy/systemd/methyl-worker@.service",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "ExecStartPre=/bin/mkdir -p /var/tmp/methyl-samtools" in text
    setup = (REPO_ROOT / "scripts/setup_host.sh").read_text(encoding="utf-8")
    assert "/var/tmp/methyl-samtools" in setup


def test_preflight_allows_missing_samples_when_current_optional(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    root = work / "goliath"
    root.mkdir(parents=True)
    proc = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts/preflight_worker_join.sh"),
            "--work",
            str(work),
            "--root",
            str(root),
            "--allow-missing-current",
            "--skip-writable-probe",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Samples root missing" in proc.stdout or "Samples root missing" in proc.stderr

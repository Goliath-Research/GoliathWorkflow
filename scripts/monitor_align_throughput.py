#!/usr/bin/env python3
"""Running average of successful WGBS Align wall times + fleet sizing estimate.

Reads Azure SQL via /work/goliath/env/gateway.env. Persists state so the
average converges as SUCCEEDED Aligns complete.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymssql
except ImportError:
    print("pymssql required", file=sys.stderr)
    sys.exit(2)

STATE_PATH = Path(
    os.environ.get(
        "METHYL_ALIGN_MONITOR_STATE",
        "/work/goliath/images/align_throughput_monitor.json",
    )
)
ACTION = "sample.methylgrapher_wgbs_align"
# Ignore tiny durations (crash loops); Align science is hours-scale.
MIN_HOURS = float(os.environ.get("METHYL_ALIGN_MIN_HOURS", "0.25"))
DEFAULT_INSTANCE = int(os.environ.get("METHYL_ALIGN_INSTANCE_ID", "59"))
DEFAULT_N_SAMPLES = int(os.environ.get("METHYL_ALIGN_FLEET_N", "300"))
DEFAULT_DEADLINE_H = float(os.environ.get("METHYL_ALIGN_FLEET_DEADLINE_H", "48"))


@dataclass
class CompletedAlign:
    ne_id: int
    sample_id: str
    hours: float
    started_at: str
    ended_at: str
    attempt_no: int


@dataclass
class MonitorState:
    updated_at_utc: str
    instance_id: int
    completed: List[Dict[str, Any]] = field(default_factory=list)
    running_avg_hours: Optional[float] = None
    n_completed: int = 0
    # Welford
    mean: float = 0.0
    m2: float = 0.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_env() -> None:
    env_path = Path("/work/goliath/env/gateway.env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _connect():
    server = os.environ["AZURE_SQL_SERVER"].replace("tcp:", "").split(",")[0]
    return pymssql.connect(
        server=server,
        user=os.environ["AZURE_SQL_USER"],
        password=os.environ["AZURE_SQL_PASSWORD"],
        database=os.environ["AZURE_SQL_DB"],
        login_timeout=30,
        timeout=60,
    )


def _sample_id(inp: Any) -> str:
    if not isinstance(inp, dict):
        return "?"
    return str(inp.get("sampleId") or inp.get("sample_id") or "?")


def fetch_aligns(instance_id: int) -> Tuple[List[CompletedAlign], List[Dict[str, Any]]]:
    conn = _connect()
    cur = conn.cursor(as_dict=True)
    cur.execute(
        """
        SELECT ne.id, ne.status, ne.result_code, ne.attempt_no,
               ne.started_at_utc, ne.ended_at_utc,
               CONVERT(nvarchar(max), ne.input_json) AS input_json
        FROM wf.node_execution ne
        JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
        JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
        WHERE wa.action_name = %s
          AND ne.workflow_instance_id = %s
        ORDER BY ne.id
        """,
        (ACTION, instance_id),
    )
    completed: List[CompletedAlign] = []
    running: List[Dict[str, Any]] = []
    now = _utcnow()
    for r in cur.fetchall():
        try:
            inp = json.loads(r["input_json"] or "{}")
        except Exception:
            inp = {}
        sid = _sample_id(inp)
        st = str(r["status"] or "")
        if st == "SUCCEEDED" and r["started_at_utc"] and r["ended_at_utc"]:
            hours = (_aware(r["ended_at_utc"]) - _aware(r["started_at_utc"])).total_seconds() / 3600.0
            if hours >= MIN_HOURS:
                completed.append(
                    CompletedAlign(
                        ne_id=int(r["id"]),
                        sample_id=sid,
                        hours=hours,
                        started_at=_aware(r["started_at_utc"]).isoformat(),
                        ended_at=_aware(r["ended_at_utc"]).isoformat(),
                        attempt_no=int(r["attempt_no"] or 1),
                    )
                )
        elif st == "RUNNING" and r["started_at_utc"]:
            hours = (now - _aware(r["started_at_utc"])).total_seconds() / 3600.0
            running.append(
                {
                    "ne_id": int(r["id"]),
                    "sample_id": sid,
                    "elapsed_hours": round(hours, 3),
                    "attempt_no": int(r["attempt_no"] or 1),
                    "started_at": _aware(r["started_at_utc"]).isoformat(),
                }
            )
    conn.close()
    return completed, running


def welford_from(completed: List[CompletedAlign]) -> Tuple[float, float, float]:
    """Return mean, sample_stdev, n."""
    n = 0
    mean = 0.0
    m2 = 0.0
    for c in completed:
        n += 1
        delta = c.hours - mean
        mean += delta / n
        delta2 = c.hours - mean
        m2 += delta * delta2
    stdev = math.sqrt(m2 / (n - 1)) if n > 1 else 0.0
    return mean, stdev, float(n)


def machines_needed(n_samples: int, hours_per_sample: float, deadline_h: float, parallel: int = 1) -> int:
    """GPUs needed if each machine runs ``parallel`` Aligns (default 1 — GPU flock)."""
    if hours_per_sample <= 0 or deadline_h <= 0:
        return 0
    throughput_per_gpu = parallel / hours_per_sample  # samples / hour / GPU
    need = n_samples / (throughput_per_gpu * deadline_h)
    return max(1, int(math.ceil(need)))


def report(
    instance_id: int = DEFAULT_INSTANCE,
    n_samples: int = DEFAULT_N_SAMPLES,
    deadline_h: float = DEFAULT_DEADLINE_H,
) -> str:
    completed, running = fetch_aligns(instance_id)
    # Prefer Mojo-era completes (post fleet cutover). Pre-cutover SUCCEEDED
    # (~6.2h vg) is baseline only — not mixed into the converging Mojo average.
    cutover = datetime(2026, 8, 9, 13, 0, tzinfo=timezone.utc)
    mojo_era = [c for c in completed if datetime.fromisoformat(c.ended_at) >= cutover]
    legacy = [c for c in completed if datetime.fromisoformat(c.ended_at) < cutover]
    if mojo_era:
        avg, sd, n_use = welford_from(mojo_era)
        avg_label = "Mojo-era SUCCEEDED"
        cohort = mojo_era
        provisional = False
    else:
        avg, sd, n_use = 0.0, 0.0, 0.0
        avg_label = "Mojo-era SUCCEEDED (none yet)"
        cohort = []
        provisional = True

    legacy_avg = welford_from(legacy)[0] if legacy else None
    # Until Mojo SUCCEEDED exist, expose longest in-flight elapsed as a lower bound only.
    lower_bound = max((r["elapsed_hours"] for r in running), default=None)

    m48 = machines_needed(n_samples, avg, deadline_h) if n_use else None
    m24 = machines_needed(n_samples, avg, 24.0) if n_use else None
    wall_4 = (n_samples / 4.0) * avg if n_use else None  # current 4-GPU fleet

    state = {
        "updated_at_utc": _utcnow().isoformat(),
        "instance_id": instance_id,
        "avg_label": avg_label,
        "n_completed_in_avg": int(n_use),
        "running_avg_hours": round(avg, 4) if n_use else None,
        "stdev_hours": round(sd, 4) if n_use else None,
        "provisional": provisional,
        "lower_bound_inflight_hours": lower_bound,
        "legacy_vg_avg_hours": round(legacy_avg, 4) if legacy_avg is not None else None,
        "completed": [asdict(c) for c in cohort],
        "legacy_completed": [asdict(c) for c in legacy],
        "running": running,
        "fleet": {
            "n_samples": n_samples,
            "deadline_h": deadline_h,
            "gpus_for_deadline": m48,
            "gpus_for_24h": m24,
            "wall_hours_on_4_gpus": round(wall_4, 2) if wall_4 is not None else None,
            "assumes_one_align_per_gpu": True,
        },
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"Align throughput monitor @ {state['updated_at_utc']}",
        f"instance={instance_id} action={ACTION}",
        f"RUNNING ({len(running)}):",
    ]
    for r in sorted(running, key=lambda x: -x["elapsed_hours"]):
        lines.append(
            f"  ne={r['ne_id']} {r['sample_id']} elapsed={r['elapsed_hours']:.3f}h "
            f"attempt={r['attempt_no']}"
        )
    if not running:
        lines.append("  (none)")
    lines.append(f"SUCCEEDED in average ({avg_label}): n={int(n_use)}")
    for c in cohort:
        lines.append(
            f"  ne={c.ne_id} {c.sample_id} wall={c.hours:.3f}h attempt={c.attempt_no}"
        )
    if legacy:
        lines.append(
            f"Legacy vg baseline (excluded from Mojo avg): "
            + ", ".join(f"{c.sample_id}={c.hours:.3f}h" for c in legacy)
        )
    if n_use:
        lines.append(
            f"RUNNING AVERAGE = {avg:.3f} h/sample  (stdev={sd:.3f}, n={int(n_use)})"
        )
        lines.append(
            f"Fleet estimate (1 Align/GPU): {n_samples} samples → "
            f"{m48} GPUs for {deadline_h:g}h deadline; "
            f"{m24} GPUs for 24h; "
            f"~{wall_4:.1f}h wall on 4 GPUs"
        )
    else:
        lines.append(
            "RUNNING AVERAGE = pending — no Mojo-era SUCCEEDED yet "
            f"(min wall ≥ {MIN_HOURS}h). Average starts when the first finishes."
        )
        if lower_bound is not None:
            lines.append(
                f"In-flight lower bound (not averaged): longest elapsed = {lower_bound:.3f}h"
            )
    lines.append(f"state: {STATE_PATH}")
    text = "\n".join(lines)
    print(text)
    return text


if __name__ == "__main__":
    _load_env()
    report()

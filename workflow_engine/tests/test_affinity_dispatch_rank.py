"""Pure-Python ranking that mirrors soft affinity ORDER BY in sp_worker_request_task."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReadyRow:
    id: int
    affinity_key: Optional[str]
    prefer_continue_group: bool
    prefer_previous_worker: bool
    available_at: str


@dataclass(frozen=True)
class SucceededRow:
    affinity_key: str
    completed_by_worker_id: int
    ended_at: str


def rank_key(
    row: ReadyRow,
    *,
    worker_id: int,
    succeeded: list[SucceededRow],
) -> tuple[int, int, str, int]:
    """Return a sort key equivalent to the claim SP ORDER BY arms."""
    continue_rank = 1
    if (
        row.prefer_continue_group
        and row.affinity_key is not None
        and any(s.affinity_key == row.affinity_key for s in succeeded)
    ):
        continue_rank = 0

    sticky_rank = 1
    if row.prefer_previous_worker and row.affinity_key is not None:
        peers = [s for s in succeeded if s.affinity_key == row.affinity_key]
        if peers:
            latest = max(peers, key=lambda s: s.ended_at)
            if latest.completed_by_worker_id == worker_id:
                sticky_rank = 0

    return (continue_rank, sticky_rank, row.available_at, row.id)


def pick(
    rows: list[ReadyRow],
    *,
    worker_id: int,
    succeeded: list[SucceededRow],
) -> ReadyRow:
    return sorted(rows, key=lambda r: rank_key(r, worker_id=worker_id, succeeded=succeeded))[0]


def test_continue_group_outranks_fresh_affinity_key() -> None:
    rows = [
        ReadyRow(10, "sample-B", True, True, "2026-08-09T19:00:00"),  # fresh align
        ReadyRow(20, "sample-A", True, True, "2026-08-10T12:00:00"),  # QC after align
    ]
    succeeded = [SucceededRow("sample-A", completed_by_worker_id=1, ended_at="2026-08-10T11:00:00")]
    assert pick(rows, worker_id=2, succeeded=succeeded).id == 20


def test_sticky_worker_preferred_when_idle() -> None:
    rows = [
        ReadyRow(20, "sample-A", True, True, "2026-08-10T12:00:00"),
        ReadyRow(21, "sample-A", True, True, "2026-08-10T12:01:00"),
    ]
    succeeded = [SucceededRow("sample-A", completed_by_worker_id=7, ended_at="2026-08-10T11:00:00")]
    assert pick(rows, worker_id=7, succeeded=succeeded).id == 20
    # Different worker: sticky arm is 1 for both; FIFO by available_at/id still holds.
    assert pick(rows, worker_id=3, succeeded=succeeded).id == 20


def test_fallback_when_preferred_worker_busy_other_worker_can_claim() -> None:
    """Soft preference: non-preferred worker still sees the continue-group row first."""
    rows = [
        ReadyRow(10, "sample-B", True, True, "2026-08-09T19:00:00"),
        ReadyRow(20, "sample-A", True, True, "2026-08-10T12:00:00"),
    ]
    succeeded = [SucceededRow("sample-A", completed_by_worker_id=1, ended_at="2026-08-10T11:00:00")]
    # Worker 2 is not sticky for sample-A, but continue-group still wins over sample-B.
    assert pick(rows, worker_id=2, succeeded=succeeded).affinity_key == "sample-A"


def test_no_affinity_flags_keep_fifo() -> None:
    rows = [
        ReadyRow(10, None, False, False, "2026-08-09T19:00:00"),
        ReadyRow(20, "sample-A", False, False, "2026-08-10T12:00:00"),
    ]
    succeeded = [SucceededRow("sample-A", completed_by_worker_id=1, ended_at="2026-08-10T11:00:00")]
    assert pick(rows, worker_id=1, succeeded=succeeded).id == 10


def test_action_dispatch_sample_affinity_export() -> None:
    from methyl_worker.action_catalog import (
        DISPATCH_EXCLUSIVE_ONE,
        DISPATCH_SAMPLE_AFFINITY,
        ACTION_CATALOG,
    )

    d = DISPATCH_SAMPLE_AFFINITY.to_dict()
    assert d["affinity_key_field"] == "sampleId"
    assert d["prefer_previous_worker"] is True
    assert d["prefer_continue_group"] is True

    excl = DISPATCH_EXCLUSIVE_ONE.to_dict()
    assert excl["max_per_worker"] == 1
    assert excl["exclusive_worker"] is True
    assert excl["affinity_key_field"] == "sampleId"

    qc = next(a for a in ACTION_CATALOG if a.action_name == "sample.methyl_qc")
    assert qc.dispatch.affinity_key_field == "sampleId"
    align = next(a for a in ACTION_CATALOG if a.action_name == "sample.methylgrapher_wgbs_align")
    assert align.dispatch.exclusive_worker is True
    assert align.dispatch.affinity_key_field == "sampleId"

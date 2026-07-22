"""Unit tests for the multi-instance hyperparameter grid expander and scorer."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_WE = Path(__file__).resolve().parents[1]
if str(_WE) not in sys.path:
    sys.path.insert(0, str(_WE))

from ops import hyperparam_grid as hg  # noqa: E402


def test_set_by_path_nested() -> None:
    d: dict = {}
    hg.set_by_path(d, "validation.stability_dmp_freq", 0.7)
    hg.set_by_path(d, "validation.max_genes", 200)
    hg.set_by_path(d, "top", 1)
    assert d == {"validation": {"stability_dmp_freq": 0.7, "max_genes": 200}, "top": 1}


def test_apply_overlay_does_not_mutate_base() -> None:
    base = {"validation": {"stability_dmp_freq": 0.5}}
    merged = hg.apply_overlay(base, {"validation.max_genes": 100})
    assert merged == {"validation": {"stability_dmp_freq": 0.5, "max_genes": 100}}
    assert base == {"validation": {"stability_dmp_freq": 0.5}}


def test_apply_overlay_null_deletes_key() -> None:
    base = {"validation": {"stability_gene_featurecuts_max_dmps": 1000, "n_iterations": 50}}
    merged = hg.apply_overlay(base, {"validation.stability_gene_featurecuts_max_dmps": None})
    assert "stability_gene_featurecuts_max_dmps" not in merged["validation"]
    assert merged["validation"]["n_iterations"] == 50


def test_start_scenario_trial_starts_one_instance(monkeypatch) -> None:
    _install_fakes(monkeypatch, scope_ids=["scope-scenario"])

    db = _FakeDb()
    started: list = []

    def create_def(_db, _spec):
        return {"workflow_version_id": 7}

    def create_inst(_db, version_id, context):
        assert context["trialIndex"] == 0
        assert context["executionScopeName"] == "ba-target-0.85"
        assert context["actionConfig"]["validation"]["stability_target_balanced_accuracy"] == 0.85
        return 42

    def start_inst(_db, instance_id):
        started.append(instance_id)

    monkeypatch.setattr(hg, "resolve_workflow_version_id", lambda *a, **k: 7)

    result = hg.start_scenario_trial(
        db,
        {
            "project_path": "/work/projects/x/configs/project.json",
            "display_name": "ba-target-0.85",
            "overrides": {"validation.stability_target_balanced_accuracy": 0.85},
        },
        create_workflow_definition=create_def,
        create_workflow_instance=create_inst,
        start_workflow_instance=start_inst,
        ledger=hg.DbTrialLedger(db),
    )

    assert len(result.trials) == 1
    assert result.trials[0].workflow_instance_id == 42
    assert result.trials[0].execution_scope_key == "scope-scenario"
    assert started == [42]
    assert result.search_id == 1
    assert len(db.trials) == 1


class _FakeDb:
    def __init__(self) -> None:
        self.applied: list = []
        self.trials: list = []
        self.scores: list = []
        self._search_seq = 0
        self._rows: list = []

    def apply_execution_scope(self, instance_id, **kwargs):
        self.applied.append((instance_id, kwargs["set_key"]))

    def start_hyperparam_search(self, **kwargs):
        self._search_seq += 1
        return self._search_seq

    def add_hyperparam_trial(self, **kwargs):
        self.trials.append(kwargs)

    def get_hyperparam_search(self, search_id):
        return self._rows

    def score_hyperparam_trial(self, **kwargs):
        self.scores.append(kwargs)


def _install_fakes(monkeypatch, *, scope_ids):
    import workflow_context
    import rest.execution_scope as es
    from methyl_validation import workflow_planner

    def fake_plan(payload):
        return SimpleNamespace(model_dump=lambda mode="json": {
            "projectPath": payload["projectPath"],
            "actionConfig": {"validation": {"stability_dmp_freq": 0.5}},
        })

    seq = iter(scope_ids)

    def fake_finalize(ctx):
        out = dict(ctx)
        out["executionScopeId"] = next(seq)
        return out

    monkeypatch.setattr(workflow_planner, "plan_validation_context", fake_plan)
    monkeypatch.setattr(workflow_context, "finalize_instance_context", fake_finalize)
    # extract payload just needs executionScopeId + resolvedConfig slices
    monkeypatch.setattr(
        es,
        "extract_execution_scope_payload",
        lambda ctx: {"set_key": ctx.get("executionScopeId"), "display_name": None, "config_json": {}},
    )


def test_expand_and_start_grid_starts_one_instance_per_point(monkeypatch) -> None:
    _install_fakes(monkeypatch, scope_ids=["scope-0", "scope-1", "scope-2", "scope-3"])

    db = _FakeDb()
    started: list = []

    def create_def(_db, _spec):
        return {"workflow_version_id": 42}

    def create_inst(_db, version_id, context):
        idx = context["trialIndex"]
        return 1000 + idx

    def start_inst(_db, instance_id):
        started.append(instance_id)

    # patch version resolution to avoid compiling a real program; must run once for N trials
    resolve_calls: list = []

    def fake_resolve(db, body, **kw):
        resolve_calls.append(body)
        return 42

    monkeypatch.setattr(hg, "resolve_workflow_version_id", fake_resolve)

    request = {
        "project_path": "/work/projects/x/configs/project.json",
        "display_name": "sweep",
        "grid": {"axes": {"validation.stability_dmp_freq": [0.6, 0.7], "validation.max_genes": [100, 200]}},
    }

    ledger = hg.DbTrialLedger(db)
    result = hg.expand_and_start_grid(
        db,
        request,
        create_workflow_definition=create_def,
        create_workflow_instance=create_inst,
        start_workflow_instance=start_inst,
        ledger=ledger,
    )

    assert len(result.trials) == 4
    assert len(resolve_calls) == 1
    # distinct scope ids per trial
    assert sorted(t.execution_scope_key for t in result.trials) == ["scope-0", "scope-1", "scope-2", "scope-3"]
    # all instances started + registered scope + ledger rows
    assert len(started) == 4
    assert len(db.applied) == 4
    assert len(db.trials) == 4
    assert result.search_id == 1


def test_score_grid_picks_best_feasible(monkeypatch) -> None:
    from methyl_validation import optimization

    db = _FakeDb()
    db._rows = [
        {"trial_index": 0, "overrides_json": {"a": 1}, "feasible": None, "objective": None},
        {"trial_index": 1, "overrides_json": {"a": 2}, "feasible": None, "objective": None},
    ]

    def fake_obj(mc, weights, constraints=None):
        value = 0.9 if "trial_1" in str(mc) else 0.3
        return SimpleNamespace(
            value=value,
            feasible=True,
            reason="ok",
            to_json_friendly=lambda: {"value": value},
        )

    monkeypatch.setattr(optimization, "objective_from_monte_carlo_artifacts", fake_obj)

    summary = hg.score_grid(
        db,
        7,
        {},
        {0: "/tmp/trial_0/mc", 1: "/tmp/trial_1/mc"},
    )

    assert summary["best_trial_index"] == 1
    assert len(db.scores) == 2


def test_winner_overlay_returns_best_feasible() -> None:
    db = _FakeDb()
    db._rows = [
        {"trial_index": 0, "overrides_json": {"a": 1}, "feasible": True, "objective": 0.3, "execution_scope_key": "s0"},
        {"trial_index": 1, "overrides_json": {"a": 2}, "feasible": True, "objective": 0.8, "execution_scope_key": "s1"},
        {"trial_index": 2, "overrides_json": {"a": 3}, "feasible": False, "objective": 0.99, "execution_scope_key": "s2"},
    ]
    win = hg.winner_overlay(db, 7)
    assert win is not None
    assert win["trial_index"] == 1
    assert win["overrides"] == {"a": 2}

"""Unit tests for scripts/gen_config_schema_seed_sql.py.

The seed is executed by hand in SSMS against Azure SQL, so a body that survives
generation but not the round trip through T-SQL literals would only surface as a
failed batch on an operator's screen. These tests reassemble what the script
emits and compare it with the repo schemas.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "gen_config_schema_seed_sql.py"

_LITERAL = re.compile(r"^SET @doc = @doc \+ N'(.*)';$", re.M)
_BLOCK = re.compile(r"^-- (\S+) \(\d+ chars\)$", re.M)


def _load_mod():
    spec = importlib.util.spec_from_file_location("gen_config_schema_seed_sql", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen_mod():
    return _load_mod()


@pytest.fixture(scope="module")
def seed(gen_mod):
    return gen_mod.emit(gen_mod.schema_items())


def _bodies(sql: str) -> dict:
    """Reassemble each emitted body the way T-SQL concatenation would."""
    parts = _BLOCK.split(sql)[1:]
    return {
        key: "".join(lit.replace("''", "'") for lit in _LITERAL.findall(block))
        for key, block in zip(parts[0::2], parts[1::2])
    }


def test_every_repo_schema_round_trips_through_the_literals(gen_mod, seed):
    emitted = _bodies(seed)
    assert emitted, "no schema blocks emitted"
    for key, body in gen_mod.schema_items():
        assert json.loads(emitted[key]) == json.loads(body)


def test_one_published_upsert_per_key(gen_mod, seed):
    keys = [key for key, _ in gen_mod.schema_items()]
    assert seed.count("EXEC cfg.cfg_repo_upsert") == len(keys)
    for key in keys:
        assert f"@name = N'{key}', @version = N'1', @status = 'published'" in seed


def test_literals_stay_under_the_nvarchar_literal_limit(seed):
    assert all(len(lit) < 4000 for lit in _LITERAL.findall(seed))


def test_exec_arguments_are_variables_or_literals(seed):
    """EXEC rejects expressions, so the json cast has to happen beforehand."""
    for line in seed.splitlines():
        if "EXEC cfg.cfg_repo_upsert" in line:
            assert "CAST(" not in line
    assert "SET @docj = CAST(@doc AS json);" in seed


def test_print_counts_through_a_variable(seed):
    """PRINT takes no subquery."""
    for line in seed.splitlines():
        if line.startswith("PRINT"):
            assert "SELECT" not in line


def test_seed_is_ascii_so_ssms_cannot_mangle_it(seed):
    seed.encode("ascii")

"""Static policy: MSSQL gateway must never bind JSON proc params without CAST(? AS json)."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

MSSQL_PATH = Path(__file__).resolve().parents[1] / "rest" / "db" / "mssql.py"

# Proc parameters that are typed sql json in the wf contract.
_JSON_PARAM_PATTERN = re.compile(
    r"@(?P<name>(?:\w*json\w*|spec))=(?P<binding>\?|\{_JSON_CAST\}|CAST\(\? AS json\))",
    re.IGNORECASE,
)

# Bare ? binding on a JSON param (forbidden).
_BARE_JSON_BINDING = re.compile(
    r"@(?:\w*json\w*|spec)=\?(?!\s*[,)])",
    re.IGNORECASE,
)

class MssqlJsonBindingPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MSSQL_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_mssql_module_defines_json_cast_constant(self) -> None:
        self.assertIn('_JSON_CAST = "CAST(? AS json)"', self.source)

    def test_no_bare_json_parameter_bindings_in_source(self) -> None:
        violations = _BARE_JSON_BINDING.findall(self.source)
        self.assertEqual(
            violations,
            [],
            "mssql.py binds JSON proc params with bare '?' (pyodbc sends NTEXT/NVARCHAR). "
            "Use DECLARE @__json_* json = CAST(? AS json) batches instead. "
            f"Matches: {violations}",
        )

    def test_all_json_proc_params_use_declare_json_helper(self) -> None:
        self.assertIn("def _declare_json(", self.source)
        declare_calls = self.source.count("_declare_json(")
        # helper definition + one call site per JSON proc path
        self.assertGreaterEqual(
            declare_calls,
            6,
            "expected _declare_json() for each JSON ODBC binding (helper + >=5 call sites)",
        )
        self.assertIn(f"json = {{_JSON_CAST}}", self.source)

    def test_json_dumps_only_in_json_text_helper(self) -> None:
        dumps_sites: list[int] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "dumps":
                if isinstance(func.value, ast.Name) and func.value.id == "json":
                    dumps_sites.append(node.lineno)

        json_text_def = next(
            n
            for n in self.tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_json_text"
        )
        helper_start = json_text_def.lineno
        helper_end = getattr(json_text_def, "end_lineno", helper_start)

        outside = [line for line in dumps_sites if line < helper_start or line > helper_end]
        self.assertEqual(
            outside,
            [],
            "json.dumps must only appear inside _json_text(); serialize via _json_text() elsewhere",
        )


if __name__ == "__main__":
    unittest.main()

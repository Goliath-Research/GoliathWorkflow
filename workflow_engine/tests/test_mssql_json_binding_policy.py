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
            f"Use {{_JSON_CAST}} instead. Matches: {violations}",
        )

    def test_all_json_proc_params_use_json_cast(self) -> None:
        bindings: list[tuple[str, str]] = []
        for match in _JSON_PARAM_PATTERN.finditer(self.source):
            bindings.append((match.group("name").lower(), match.group("binding")))

        self.assertGreater(
            len(bindings),
            0,
            "expected at least one JSON proc parameter binding in mssql.py",
        )

        bad = [
            f"@{name}={binding}"
            for name, binding in bindings
            if binding == "?"
        ]
        self.assertEqual(
            bad,
            [],
            "JSON proc parameters must use {_JSON_CAST} or CAST(? AS json), not bare ?",
        )

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

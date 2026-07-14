"""Unit tests for worker enroll helpers and CLI token write."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "workers"))

from methyl_worker.__main__ import _run_enroll_cli, _write_token_file  # noqa: E402
from methyl_worker.client import WorkflowRestClient  # noqa: E402


class TokenFileTests(unittest.TestCase):
    def test_write_token_file_mode_600(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "worker-token"
            _write_token_file(path, 7, "abc123")
            text = path.read_text(encoding="utf-8")
            self.assertIn("WORKER_ID=7", text)
            self.assertIn("WORKER_TOKEN=abc123", text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class EnrollClientTests(unittest.TestCase):
    def test_enroll_posts_expected_body(self) -> None:
        client = WorkflowRestClient("http://gateway/v1", arc_resource_id="")
        with patch.object(client, "_post_json", return_value={"worker_id": 1, "worker_token": "t"}) as post:
            out = client.enroll("lambda", "vm-1", capabilities=["methyl-qc"])
        post.assert_called_once_with(
            "/workers/enroll",
            {
                "cluster_key": "lambda",
                "external_worker_key": "vm-1",
                "capabilities": ["methyl-qc"],
            },
        )
        self.assertEqual(out["worker_id"], 1)


class EnrollCliTests(unittest.TestCase):
    def test_enroll_cli_writes_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "token"
            args = MagicMock(
                cluster_key="lambda",
                external_worker_key="vm-1",
                api_base="http://gw/v1",
                capabilities_json="",
                token_file=str(token_path),
                env_file="",
            )
            with patch("methyl_worker.__main__.WorkflowRestClient") as cls:
                cls.return_value.enroll.return_value = {
                    "worker_id": 3,
                    "worker_token": "secret",
                    "cluster_key": "lambda",
                    "external_worker_key": "vm-1",
                }
                rc = _run_enroll_cli(args)
            self.assertEqual(rc, 0)
            self.assertEqual(
                token_path.read_text(encoding="utf-8"),
                "WORKER_ID=3\nWORKER_TOKEN=secret\n",
            )


if __name__ == "__main__":
    unittest.main()

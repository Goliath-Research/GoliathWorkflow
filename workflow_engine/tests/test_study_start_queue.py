"""Study start daemon claims a queue row and bakes before SQL create."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ops.study_start_queue import _build_body, drain_requests, process_one_request


class StudyStartQueueTests(unittest.TestCase):
    def test_build_body_requires_project_path(self) -> None:
        with self.assertRaises(ValueError):
            _build_body(
                {
                    "workflow_version_id": 1,
                    "study_row_id": 2,
                    "request_json": {"stage": "sample_prep"},
                },
                {},
            )

    def test_build_body_applies_overlay(self) -> None:
        body = _build_body(
            {
                "workflow_version_id": 9,
                "study_row_id": 3,
                "request_json": {
                    "projectPath": "/work/projects/x/configs/project_x.json",
                    "pipelineProfile": "samd_research",
                },
            },
            {"alignment_qc": {"min_pf_reads": 1}},
        )
        self.assertEqual(body["workflow_version_id"], 9)
        self.assertEqual(body["actionConfig"]["alignment_qc"]["min_pf_reads"], 1)

    def test_process_one_uses_portal_create_not_double_start(self) -> None:
        db = MagicMock()
        db.backend = "postgres"
        db._fetch_one.side_effect = [
            {"action_config_overlay": "{}"},
            {"id": 77},
        ]
        row = {
            "request_id": 5,
            "study_row_id": 3,
            "stage": "sample_prep",
            "workflow_version_id": 9,
            "request_json": {
                "projectPath": "/work/projects/x/configs/project_x.json"
            },
        }
        with patch(
            "ops.sample_lifecycle.plan_sample_prep_instance_context",
            return_value={"resolvedConfig__alignment_qc": {}},
        ) as plan:
            payload = process_one_request(db, row)
        plan.assert_called_once()
        self.assertEqual(payload["instance_id"], 77)
        sql = db._fetch_one.call_args_list[-1][0][0]
        self.assertIn("sp_create_and_start_instance", sql)

    def test_drain_marks_failure(self) -> None:
        db = MagicMock()
        db.backend = "postgres"
        db._fetch_one.return_value = {
            "request_id": 1,
            "study_row_id": 3,
            "stage": "nope",
            "workflow_version_id": 9,
            "request_json": {"projectPath": "/work/projects/x/configs/project_x.json"},
        }
        results = drain_requests(db, claimed_by="test", limit=1)
        self.assertEqual(results[0]["status"], "failed")
        db._exec_proc.assert_called()
        self.assertIn("sp_fail_study_start_request", db._exec_proc.call_args[0][0])

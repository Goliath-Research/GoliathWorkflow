"""Tests for methyl_worker REST client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from methyl_worker.client import WorkflowRestClient


def test_request_task_empty() -> None:
    client = WorkflowRestClient("http://test/v1")
    with patch.object(client, "_post_json", return_value={"has_task": False}):
        assert client.request_task(1, "tok", "methyl-centroid") is None


def test_request_task_claim() -> None:
    client = WorkflowRestClient("http://test/v1")
    body = {
        "has_task": True,
        "node_execution_id": 42,
        "workflow_instance_id": 7,
        "action_name": "pipeline.centroid",
        "capability": "methyl-centroid",
        "node_key": "centroid_g1",
        "input_json": {"project": "/p.json", "tool": "MethylCentroid"},
    }
    with patch.object(client, "_post_json", return_value=body):
        claim = client.request_task(1, "tok")
    assert claim is not None
    assert claim.node_execution_id == 42
    assert claim.input_json["project"] == "/p.json"


def test_submit_result() -> None:
    client = WorkflowRestClient("http://test/v1")
    with patch.object(
        client,
        "_post_json",
        return_value={"accepted": True, "instance_status": "RUNNING", "next_ready_count": 3},
    ) as mock_post:
        ack = client.submit_result(42, 1, "tok", 0, {"status": "ok"})

    mock_post.assert_called_once()
    path, payload = mock_post.call_args[0]
    assert path == "/workers/tasks/42/submit"
    assert payload["result_code"] == 0
    assert payload["output_json"] == {"status": "ok"}
    assert ack.accepted is True
    assert ack.next_ready_count == 3


def test_post_json_http_error() -> None:
    client = WorkflowRestClient("http://test/v1")
    err = MagicMock()
    err.code = 401
    err.read.return_value = b"unauthorized"

    with patch("methyl_worker.client.urlopen") as mock_urlopen:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError("http://x", 401, "nope", {}, err)
        with pytest.raises(RuntimeError, match="HTTP 401"):
            client.authenticate(1, "bad")

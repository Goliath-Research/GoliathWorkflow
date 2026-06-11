"""Poll loop: claim tasks, execute handlers, submit results."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .client import TaskClaim, WorkflowRestClient
from .handlers import execute_task
from .task_validation import (
    TASK_VALIDATION_ERROR_CODE,
    TaskValidationError,
    validate_task_input,
    validate_task_output,
)

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(
        self,
        client: WorkflowRestClient,
        worker_id: int,
        worker_token: str,
        capability: Optional[str] = None,
        *,
        poll_seconds: float = 5.0,
        heartbeat_seconds: float = 60.0,
    ) -> None:
        self.client = client
        self.worker_id = worker_id
        self.worker_token = worker_token
        self.capability = capability
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> bool:
        """Poll once; return True if a task was processed."""
        claim = self.client.request_task(self.worker_id, self.worker_token, self.capability)
        if claim is None:
            return False
        self._process_claim(claim)
        return True

    def run_forever(self) -> None:
        while True:
            if not self.run_once():
                time.sleep(self.poll_seconds)

    def _process_claim(self, claim: TaskClaim) -> None:
        ne_id = claim.node_execution_id
        stop = threading.Event()

        def heartbeat_loop() -> None:
            while not stop.wait(self.heartbeat_seconds):
                try:
                    self.client.heartbeat(ne_id, self.worker_id, self.worker_token)
                except Exception:
                    logger.exception("Heartbeat failed for task %s", ne_id)

        self.client.heartbeat(ne_id, self.worker_id, self.worker_token)
        hb_thread = threading.Thread(target=heartbeat_loop, name=f"hb-{ne_id}", daemon=True)
        hb_thread.start()

        try:
            validate_task_input(claim.action_name, claim.capability, claim.input_json)
            output = execute_task(claim.capability, claim.action_name, claim.input_json)
            validate_task_output(claim.action_name, claim.capability, output)
            ack = self.client.submit_result(
                ne_id, self.worker_id, self.worker_token, 0, output
            )
            logger.info(
                "Submitted task %s (%s) accepted=%s instance=%s ready=%s",
                ne_id,
                claim.capability,
                ack.accepted,
                ack.instance_status,
                ack.next_ready_count,
            )
        except TaskValidationError as exc:
            logger.error("Task %s schema validation failed: %s", ne_id, exc)
            self.client.fail_task(
                ne_id,
                self.worker_id,
                self.worker_token,
                TASK_VALIDATION_ERROR_CODE,
                str(exc),
            )
        except Exception as exc:
            logger.exception("Task %s failed", ne_id)
            self.client.submit_result(
                ne_id,
                self.worker_id,
                self.worker_token,
                -1,
                {"error": str(exc), "capability": claim.capability},
            )
        finally:
            stop.set()
            hb_thread.join(timeout=1.0)

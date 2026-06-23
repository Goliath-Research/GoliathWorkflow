"""HTTP client for admin-tier gateway routes (catalog seed, workflow deploy)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


def admin_bearer_token() -> Optional[str]:
    token = os.environ.get("GATEWAY_ADMIN_BEARER_TOKEN", "").strip()
    if token:
        return token
    return os.environ.get("GATEWAY_ENTRA_BEARER_TOKEN", "").strip() or None


def admin_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    api_base: Optional[str] = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    base = (api_base or os.environ.get("WORKER_API_BASE") or "http://localhost:8080/v1").rstrip("/")
    url = f"{base}{path}"
    headers = {"Content-Type": "application/json"}
    token = admin_bearer_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed HTTP {exc.code}: {detail}") from exc


def load_catalog_seed_payload(
    catalog_path: Path,
    tasks_dir: Path,
) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    schemas: list[dict[str, Any]] = []

    from methyl_worker.task_schema_registry import list_task_schema_specs

    for spec in list_task_schema_specs():
        for direction, filename in (
            ("input", spec.input_filename),
            ("output", spec.output_filename),
        ):
            path = tasks_dir / filename
            if not path.is_file():
                continue
            schemas.append(
                {
                    "action_name": spec.action_name,
                    "direction": direction,
                    "schema_json": json.loads(path.read_text(encoding="utf-8")),
                    "schema_id": spec.schema_id,
                }
            )

    return {"catalog": catalog, "schemas": schemas}

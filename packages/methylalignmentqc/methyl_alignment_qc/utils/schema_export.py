"""Export versioned JSON Schema for AlignmentQC sample payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from methyl_alignment_qc.models.sample_qc import ExportedSampleQCPayload


def generate_schema_dict() -> dict:
    """Generate JSON Schema from strict Pydantic model."""
    schema = ExportedSampleQCPayload.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema.setdefault("title", "ExportedSampleQCPayload")
    return schema


def write_schema(output_path: Path) -> Path:
    """Write schema JSON to output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = generate_schema_dict()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _default_schema_output_path() -> Path:
    """Repository-relative default schema destination."""
    pkg_root = Path(__file__).resolve().parents[2]
    return pkg_root / "schemas" / "exported_sample_qc.schema.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export JSON Schema for exported AlignmentQC payload.")
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_schema_output_path(),
        help="Output JSON schema path (default: packages/methylalignmentqc/schemas/exported_sample_qc.schema.json)",
    )
    args = parser.parse_args()

    path = write_schema(args.output)
    print(f"Wrote schema: {path}")


if __name__ == "__main__":
    main()

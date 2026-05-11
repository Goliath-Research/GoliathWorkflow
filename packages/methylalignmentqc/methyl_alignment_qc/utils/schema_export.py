"""Export versioned JSON Schema for AlignmentQC sample payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from methyl_alignment_qc.models.sample_qc import ExportedSampleQCPayload
from methyl_alignment_qc.models.sample_qc_v2 import ExportedSampleQCV2Payload


def generate_schema_dict_v1() -> dict:
    """Generate JSON Schema from strict Pydantic model (V1 columnar export)."""
    schema = ExportedSampleQCPayload.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema.setdefault("title", "ExportedSampleQCPayload")
    return schema


def generate_schema_dict_v2() -> dict:
    """Generate JSON Schema from strict Pydantic model (V2 row-oriented export)."""
    schema = ExportedSampleQCV2Payload.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema.setdefault("title", "ExportedSampleQCV2Payload")
    return schema


def write_schema_v1(output_path: Path) -> Path:
    """Write V1 schema JSON to output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = generate_schema_dict_v1()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_schema_v2(output_path: Path) -> Path:
    """Write V2 schema JSON to output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = generate_schema_dict_v2()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _default_schema_output_path(variant: str) -> Path:
    """Repository-relative default schema destination."""
    pkg_root = Path(__file__).resolve().parents[2]
    if variant == "v2":
        return pkg_root / "schemas" / "exported_sample_qc_v2.schema.json"
    return pkg_root / "schemas" / "exported_sample_qc.schema.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export JSON Schema for exported AlignmentQC payload.")
    parser.add_argument(
        "--variant",
        choices=["v1", "v2"],
        default="v1",
        help="Schema variant: v1 columnar export or v2 row-oriented export (default: v1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON schema path (default depends on --variant)",
    )
    args = parser.parse_args()

    out = args.output if args.output is not None else _default_schema_output_path(args.variant)
    if args.variant == "v2":
        path = write_schema_v2(out)
    else:
        path = write_schema_v1(out)
    print(f"Wrote schema ({args.variant}): {path}")


if __name__ == "__main__":
    main()

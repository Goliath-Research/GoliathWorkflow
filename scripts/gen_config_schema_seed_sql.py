#!/usr/bin/env python3
"""Emit an SSMS-runnable seed for ``cfg.config_schema`` from ``schemas/config/``.

``sync_cfg_profiles_and_action_catalog.py --only-config-schemas`` is the canonical
loader, but it needs pyodbc plus cluster credentials. Operators working from a
Windows workstation usually have SSMS and a live connection and nothing else, so
this writes the very same rows as one T-SQL batch of ``cfg.cfg_repo_upsert``
calls they can execute there.

Bodies are compacted and ASCII-escaped, then split into literals short enough to
stay well under the 4000-character limit for an ``nvarchar`` literal, and
concatenated into an ``nvarchar(max)`` variable.

Usage::

  source .venv/bin/activate
  python scripts/gen_config_schema_seed_sql.py            # sibling DB repo
  python scripts/gen_config_schema_seed_sql.py --out seed.sql
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO / "schemas" / "config"
DEFAULT_OUT = REPO.parents[2] / "DB" / "MethylpipelineCloud" / "Scripts" / "Seed_ConfigSchemas.sql"

CHUNK = 3000


def schema_items() -> List[Tuple[str, str]]:
    """Return (actionConfig key, compact body) for every repo config schema."""
    items: List[Tuple[str, str]] = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        key = path.name[: -len(".schema.json")]
        items.append((key, json.dumps(doc, separators=(",", ":"), sort_keys=False)))
    return items


def literals(body: str) -> Iterator[str]:
    """Split a body into T-SQL literal payloads, quotes doubled per chunk."""
    for start in range(0, len(body), CHUNK):
        yield body[start : start + CHUNK].replace("'", "''")


def emit(items: Sequence[Tuple[str, str]]) -> str:
    out: List[str] = []
    add = out.append

    add(f"""/* ============================================================================
   Seed_ConfigSchemas.sql   -- GENERATED, do not edit by hand

   actionConfig JSON Schema bodies for cfg.config_schema, so the portal can
   render each pipeline profile actionConfig.<key> as a typed grid instead of
   raw JSON. One row per schemas/config/<key>.schema.json in the MethylPipeline
   repo, published at version 1 through cfg.cfg_repo_upsert (which hashes the
   body, so re-running is idempotent and only touches changed keys).

   Run Deploy_ConfigSchemas.sql first: it creates the table and the procs.

   Regenerate after editing any schema:
     source .venv/bin/activate
     python scripts/gen_config_schema_seed_sql.py

   On a machine with database credentials the equivalent, and canonical, path is
     python scripts/sync_cfg_profiles_and_action_catalog.py \\
       --backend mssql --only-config-schemas

   HOW TO RUN: open in SSMS with the target database selected and Execute.
   Keys: {len(items)}
   ============================================================================ */

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'cfg.config_schema', N'U') IS NULL
    THROW 50000, N'cfg.config_schema missing - run Deploy_ConfigSchemas.sql first.', 1;
GO

/* cfg_repo_upsert returns the row id; capture it so SSMS shows one grid, not one
   per key. Single batch: the variables must outlive every upsert below. @docj
   exists because EXEC takes only constants and variables, never an expression,
   so the nvarchar(max) body cannot be cast to json in the argument list. */
DECLARE @ids table (id bigint);
DECLARE @doc nvarchar(max);
DECLARE @docj json;
""")

    for key, body in items:
        add(f"\n-- {key} ({len(body)} chars)")
        add("SET @doc = N'';")
        for chunk in literals(body):
            add(f"SET @doc = @doc + N'{chunk}';")
        add("SET @docj = CAST(@doc AS json);")
        add(
            "INSERT INTO @ids EXEC cfg.cfg_repo_upsert "
            f"@kind = N'config_schema', @name = N'{key}', @version = N'1', "
            "@status = 'published', @document_json = @docj;"
        )

    add(f"""
-- PRINT takes no subquery, so count into a variable first.
DECLARE @seeded int = (SELECT COUNT(*) FROM @ids);
PRINT 'Seed_ConfigSchemas: upserted ' + CAST(@seeded AS varchar(20)) + ' key(s).';
GO

PRINT '== Verification ==';
GO
EXEC portal.sp_list_config_schemas @published_only = 0;
GO

/* actionConfig keys still without a schema row: these stay on the JSON view.
   OPENJSON hands keys back as Latin1_General_BIN2, so the join against a
   database-collated column needs COLLATE to avoid a collation conflict. */
SELECT k.[key] COLLATE DATABASE_DEFAULT AS action_config_key,
       COUNT(DISTINCT p.id) AS profiles
FROM cfg.pipeline_profile p
CROSS APPLY OPENJSON(CAST(p.document_json AS nvarchar(max)), N'$.actionConfig') k
WHERE NOT EXISTS (
    SELECT 1 FROM cfg.config_schema s
    WHERE s.name = k.[key] COLLATE DATABASE_DEFAULT
)
GROUP BY k.[key] COLLATE DATABASE_DEFAULT
ORDER BY profiles DESC, action_config_key;
GO

PRINT 'Seed_ConfigSchemas: done.';
GO
""")

    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    items = schema_items()
    if not items:
        raise SystemExit(f"no schemas under {SCHEMA_DIR}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # json.dumps escapes non-ASCII, so the whole script is ASCII and SSMS cannot
    # mangle it whichever encoding it guesses.
    args.out.write_text(emit(items), encoding="ascii")
    print(f"wrote {args.out} ({args.out.stat().st_size:,} bytes, {len(items)} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

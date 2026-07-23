# FOREACH Node Type

**Status:** Implemented in [`wf_sql_foreach_support.sql`](wf_sql_foreach_support.sql).  
**Goal:** Express data-driven fan-out over JSON collections without static node explosion.

**CAAS iteration-bundle short-circuit (PG parity):** see `workflow_engine/sql_pg/08_foreach_support.sql` — table `wf.foreach_bundle_entry` (PK by `content_key`) and `wf_foreach_caas_try_skip_body`. Local engine uses `{project_root}/.caas/foreach_bundle/` with nested parent ancestry in the key. Gateway must mirror the same `content_key` (node + item + ancestry fingerprint); skip-by-(node, iteration_index) alone is unsafe for nested FOREACH. When `content_key` is not supplied, DB skip is a no-op.

---

## Problem

Milestone 1 (`PCaTwoGroupFlow`) uses **122 workflow nodes** for 24 chromosomes × 2 groups. Full PCa3 scale:

- 3 groups × 2 comparisons × 24 chromosomes × 1 context ≈ **hundreds of ACTION nodes** if statically generated.
- Placeholders cannot index arrays: `${var.chromosomes[i]}` is unsupported.
- Only `REPEAT` (fixed count) and `WHILE` (condition) exist today.

---

## Proposed node type: `FOREACH`

### Definition table changes

Extend `wf.workflow_node` CHECK constraint:

```sql
CONSTRAINT CK_wn_node_type CHECK (node_type IN (
  N'ACTION', N'SEQUENCE', N'PARALLEL', N'IF', N'SWITCH', N'REPEAT', N'WHILE', N'FOREACH'
))
```

New columns (additive migration):

| Column | Type | Purpose |
|--------|------|---------|
| `foreach_collection_var` | `nvarchar(128)` | Scope variable name holding JSON array |
| `foreach_item_var` | `nvarchar(128)` | Loop item variable written each iteration (default `item`) |
| `foreach_index_var` | `nvarchar(128)` | Optional index variable (default `index`) |

Single **BODY** child edge (same as REPEAT/WHILE).

### Runtime behavior

1. On `FOREACH` activation, read `foreach_collection_var` from scope as JSON array.
2. Parse length `N`. If `N = 0`, complete FOREACH immediately.
3. Insert `wf.loop_state` row (reuse table) with `repeat_target_count = N`, `current_iteration = 0`.
4. For iteration `k` in `1..N`:
   - Set scope variables:
     - `foreach_item_var` → `JSON_QUERY(array, '$[k-1]')`
     - `foreach_index_var` → `k-1` (integer JSON)
   - Seed `ctx.iterationNo = k` (consistent with REPEAT).
   - Activate BODY child once per iteration **sequentially** (like REPEAT), or optionally fan-out in parallel (config flag — default sequential for predictable scope).

5. On BODY complete: increment iteration; if `< N`, re-enter BODY; else complete FOREACH.

Alternative **parallel FOREACH** mode: activate `N` BODY subtrees under a synthetic inner PARALLEL (future).

### Placeholder enhancements

Extend `wf.wf_resolve_token`:

| Token | Meaning |
|-------|---------|
| `${var.name}` | Existing scope lookup |
| `${var.name[0]}` | `JSON_QUERY` index into array/object scope value |
| `${ctx.item}` | Shorthand for current FOREACH item (also stored as scope var) |
| `${ctx.index}` | FOREACH zero-based index |

Reject general expressions; allow **only** `var.<ident>[<integer>]` as an extension of existing token grammar.

---

## Example compact workflow (future)

```text
SEQUENCE pca_full
└─ FOREACH comparisons (var: mc.comparisons)
   └─ SEQUENCE one_comparison
      └─ FOREACH chromosomes (var: mc.chromosomes)
         └─ SEQUENCE one_chr
            ├─ PARALLEL centroids
            │  ├─ ACTION centroid_g1  (templates use ${ctx.item.chr}, ${var.comparison.controlDir})
            │  └─ ACTION centroid_g2
            └─ ACTION detect
```

Instance `context_json` seeds:

```json
{
  "projectPath": ".../project_PCa3.json",
  "context": "CG",
  "mc": {
    "chromosomes": ["1","2",...,"Y"],
    "comparisons": [
      {"label":"PCa_Low","centroid1Dir":"...","centroid2Dir":"...","detectOutDir":"..."},
      {"label":"PCa_High", "...": "..."}
    ]
  }
}
```

Node count: **O(comparisons + chromosomes)** composite nodes, not **O(comparisons × chromosomes × actions)**.

---

## Stored procedures to add/change

| Object | Change |
|--------|--------|
| `wf.wf_engine_activate` | `FOREACH` branch: init loop_state, bind item/index scope vars, activate BODY |
| `wf.wf_foreach_continue` | New proc (mirror `wf_repeat_continue`) |
| `wf.wf_engine_on_action_complete` | Route parent `FOREACH` → `wf_foreach_continue` |
| `wf.wf_resolve_token` | Parse `var.x[n]` and `ctx.item` / `ctx.index` |
| `wf.wf_open_scope` | No change (FOREACH is composite, opens scope like REPEAT) |

---

## Migration path

1. Ship milestone 1 with static `PCaTwoGroupFlow` (validates worker contracts + SQL write-path).
2. Ship milestone 2 with static `PCaOvrFlow` ([deprecated/wf_pca_ovr_seed.sql](deprecated/wf_pca_ovr_seed.sql)) — parallel `control_vs_each_disease` comparisons + post mapper/enricher/progression for [project_PCa3.json](/work/projects/prostate-cancer/configs/project_PCa3.json).
3. Implement FOREACH + indexing in SQL parity scripts (milestone 3 — **done**).
4. Validation / MC via **ValidationPipeline** + `context_json.iterations[]` ([wf_validation_pipeline_seed.sql](wf_validation_pipeline_seed.sql)); see [validation_planner_capabilities.md](../contract/validation_planner_capabilities.md).

---

## Open questions

1. **Parallel vs sequential FOREACH:** Should each iteration run concurrently? Sequential matches REPEAT semantics and simplifies scope; parallel requires isolated scope per iteration (like PARALLEL children).
2. **Nested FOREACH scope:** Item variables shadow outer loop names via scope chain walk (existing `wf_get_scope_variable_json` behavior).
3. **JSON Schema validation:** Optional future table `wf.workflow_action_payload_schema` storing JSON Schema documents validated at claim time.

---

## References

- Static milestone: [wf_pca_two_group_seed.sql](wf_pca_two_group_seed.sql)
- Capability check: [../CAPABILITY_CHECK.md](../CAPABILITY_CHECK.md)
- SQL scope write-path parity: `wf_sql_scope_writepath_parity.sql` / `sql_pg/06_scope_writepath_parity.sql`

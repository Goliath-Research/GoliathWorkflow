---
name: MethylMapper Enrichment Speedup
overview: Accelerate MethylMapper’s gene-enrichment phase by targeting the BEDTOOLS path where Grok/Open Targets/DisGeNET are called serially, cache reuse is effectively disabled by default, and the same genes are enriched multiple times per run.
todos:
  - id: parallelize-enrichment-io
    content: Add bounded concurrency for Grok/Open Targets/DisGeNET in GeneDiseaseEnricher while preserving output compatibility.
    status: pending
  - id: fix-cache-semantics
    content: Refactor enrichment caching to support same-run reuse, source-specific TTLs, and Open Targets target-ID caching.
    status: pending
  - id: dedupe-run-level-enrichment
    content: Change BedtoolsMapper to enrich unique genes once per run and merge results back into per-file and combined outputs.
    status: pending
  - id: add-enrichment-tests
    content: Add mocked regression/performance tests covering concurrency, cache reuse, and duplicate-query elimination.
    status: pending
isProject: false
---

# Accelerate MethylMapper Enrichment

## Scope

Focus on the BEDTOOLS mapper path in [packages/methylmapper/methyl_mapper/bedtools_mapper.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py) and the shared enrichment client in [packages/methylmapper/methyl_mapper/gene_disease_enricher.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/gene_disease_enricher.py). The SQL stored-procedure path in [packages/methylmapper/methyl_mapper/mapper.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/mapper.py) does not call Grok/Open Targets/DisGeNET, so API parallelization should be implemented only in the BEDTOOLS/enricher stack.

## Key Findings

The current enrichment flow is fully serial across sources:

```898:905:/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/gene_disease_enricher.py
if self.use_grok:
    grok_results = self.query_grok_api(unique_genes, disease_term)

if self.use_open_targets:
    open_targets_results = self.query_open_targets(unique_genes, disease_term)

if self.use_disgenet:
    disgenet_results = self.query_disgenet(unique_genes, disease_term)
```

Cache reuse is also effectively disabled by default because both the CLI and `BedtoolsMapper` default `cache_ttl_days` to `0`, and TTL `0` is treated as always stale:

```1231:1235:/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/gene_disease_enricher.py
def _is_cache_valid(self, ts: Optional[float]) -> bool:
    if ts is None:
        return True
    if self.cache_ttl_days == 0:
        return False
```

The mapper also enriches per-file results and then enriches the combined result again, which repeats the same genes in one run:

```1049:1057:/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py
if self.enrich_disease and group_by in ['gene_name', 'gene_id']:
    if self.disease_enricher:
        aggregated = self.disease_enricher.enrich_gene_dataframe(
            aggregated,
            gene_column=group_by,
            disease_term=self.disease_enricher.disease_term
        )
```

```1181:1206:/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py
if self.enrich_disease and group_by in ['gene_name', 'gene_id']:
    if self.disease_enricher:
        combined = self.disease_enricher.enrich_gene_dataframe(
            combined,
            gene_column=group_by,
            disease_term=disease_term
        )
```

## Implementation Plan

### 1. Add bounded concurrency to enrichment calls

Update [packages/methylmapper/methyl_mapper/gene_disease_enricher.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/gene_disease_enricher.py) to support thread-based parallel I/O with configurable limits.

- Run enabled sources in parallel inside `enrich_gene_dataframe()` so Grok, Open Targets, and DisGeNET no longer add latency sequentially.
- Parallelize Grok across independent gene batches instead of iterating batch-by-batch in a single loop.
- Parallelize Open Targets and DisGeNET per uncached gene with bounded worker pools.
- Keep retries/backoff per task and centralize result merging so the output schema stays unchanged.
- Avoid sharing a mutable `requests.Session` unsafely across worker threads; use per-worker sessions or a session factory.

### 2. Fix caching so repeated genes do not trigger repeat network calls

Refactor [packages/methylmapper/methyl_mapper/gene_disease_enricher.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/gene_disease_enricher.py) cache behavior.

- Separate same-process memoization from disk-cache TTL so results fetched earlier in the same run are always reusable.
- Introduce source-specific cache controls, at minimum preserving stricter freshness for Grok while allowing Open Targets/DisGeNET reuse by default.
- Add missing Open Targets target-ID caching; disease IDs are cached today, but target IDs are resolved repeatedly.
- Replace row-by-row pandas cache updates/lookups with a simpler dict-backed in-memory index and batched disk flushes.
- Change CLI defaults in [packages/methylmapper/methyl_mapper/cli.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/cli.py) and constructor defaults in [packages/methylmapper/methyl_mapper/bedtools_mapper.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py) so cache reuse is on by default instead of effectively off.

### 3. Remove duplicate enrichment work inside one mapping run

Restructure [packages/methylmapper/methyl_mapper/bedtools_mapper.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py) so enrichment is performed once per unique gene set, not once per file plus once again for the combined output.

- Build the union of unique `gene_name`/`gene_id` values across per-file aggregates.
- Enrich that union once, then merge the resulting enrichment columns back into each per-file DataFrame and the final combined DataFrame.
- In the optimization flow, batch newly discovered genes before enrichment instead of issuing many tiny calls during Phase 3.

### 4. Address secondary local hotspots after API latency is fixed

Tighten local BEDTOOLS-path preprocessing in [packages/methylmapper/methyl_mapper/bedtools_mapper.py](/home/ubuntu/MethylPipeline/packages/methylmapper/methyl_mapper/bedtools_mapper.py).

- Vectorize `csv_to_bed()` instead of building BED rows with `iterrows()`.
- Replace full-stdout parsing in `intersect_with_features()` with a streamed temp-file or chunked parse path if large inputs make memory a factor.
- Vectorize `_join_with_dmp_weights()` DMP-name parsing and avoid mutating the original `dmp_df` in place during merges.

### 5. Add regression and performance coverage

Create focused tests under [packages/methylmapper](/home/ubuntu/MethylPipeline/packages/methylmapper) for the new behavior.

- Verify one-run deduplication: the same gene should not be re-queried when it appears in multiple chromosome outputs and the combined output.
- Verify concurrency-limited Grok batching and Open Targets worker behavior with mocked HTTP calls.
- Verify cache semantics for `cache_ttl_days=0`, positive TTLs, and same-process reuse.
- Add a small benchmark or request-count test to prove reduced API calls and lower wall-clock time on a representative gene set.

## Expected Outcome

This should cut end-to-end runtime mainly by: (1) overlapping Grok/Open Targets/DisGeNET latency, (2) parallelizing independent Grok/Open Targets requests with safe limits, and (3) eliminating duplicate enrichment of the same genes within a run. The biggest practical gain is likely a combination of source-level parallelism plus fixing the current no-cache-by-default behavior.
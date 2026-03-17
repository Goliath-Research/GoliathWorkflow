"""
Gene-disease association enrichment using Grok API and biomedical databases.

This module enriches gene mapping results with disease associations, particularly
focused on cancer types like early-stage prostate cancer.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock, local
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .secure_credentials import SecureCredentialManager

logger = logging.getLogger(__name__)

# Cache format version (3 = dict-backed runtime index + persisted records)
CACHE_VERSION = 3
CACHE_COLUMNS = ["source", "gene", "disease_term", "ts", "value_json"]
DISEASE_CACHE_COLUMNS = ["disease_term", "ts", "disease_id"]
TARGET_CACHE_COLUMNS = ["gene_name", "ts", "target_id"]

DEFAULT_CACHE_TTL_DAYS = 7
DEFAULT_GROK_CACHE_TTL_DAYS = 7
DEFAULT_GROK_BATCH_SIZE = 20
DEFAULT_GROK_MAX_WORKERS = 8
DEFAULT_OPEN_TARGETS_MAX_WORKERS = 8
DEFAULT_DISGENET_MAX_WORKERS = 8
DEFAULT_SOURCE_MAX_WORKERS = 3
NULL_CACHE_VALUE = "__NULL__"

# Evidence level ordering for thresholding
EVIDENCE_LEVEL_ORDER = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3
}

# Enrichment profiles for quick testing
ENRICHMENT_PROFILES = {
    "strict": {
        "min_evidence_level": "high",
        "min_publications": 2,
        "min_disgenet_score": 0.5,
        "min_open_targets_score": 0.3,
        "allow_predicted": False
    },
    "balanced": {
        "min_evidence_level": "medium",
        "min_publications": 0,
        "min_disgenet_score": 0.3,
        "min_open_targets_score": 0.1,
        "allow_predicted": False
    },
    "permissive": {
        "min_evidence_level": "low",
        "min_publications": 0,
        "min_disgenet_score": 0.0,
        "min_open_targets_score": 0.0,
        "allow_predicted": True
    }
}


def _apply_enrichment_profile(
    enrichment_profile: Optional[str],
    min_evidence_level: Optional[str],
    min_publications: Optional[int],
    min_disgenet_score: Optional[float],
    min_open_targets_score: Optional[float],
    allow_predicted: Optional[bool]
) -> Dict[str, Union[str, int, float, bool]]:
    """Apply profile defaults for enrichment thresholds."""
    if enrichment_profile:
        profile_key = enrichment_profile.lower()
        if profile_key not in ENRICHMENT_PROFILES:
            raise ValueError(
                f"Unknown enrichment_profile '{enrichment_profile}'. "
                f"Valid options: {list(ENRICHMENT_PROFILES.keys())}"
            )
        profile = ENRICHMENT_PROFILES[profile_key]
        if min_evidence_level is None:
            min_evidence_level = profile["min_evidence_level"]
        if min_publications is None:
            min_publications = profile["min_publications"]
        if min_disgenet_score is None:
            min_disgenet_score = profile["min_disgenet_score"]
        if min_open_targets_score is None:
            min_open_targets_score = profile["min_open_targets_score"]
        if allow_predicted is None:
            allow_predicted = profile["allow_predicted"]

    # Fallback defaults
    if min_evidence_level is None:
        min_evidence_level = "medium"
    if min_publications is None:
        min_publications = 0
    if min_disgenet_score is None:
        min_disgenet_score = 0.0
    if min_open_targets_score is None:
        min_open_targets_score = 0.0
    if allow_predicted is None:
        allow_predicted = False

    return {
        "min_evidence_level": min_evidence_level,
        "min_publications": min_publications,
        "min_disgenet_score": min_disgenet_score,
        "min_open_targets_score": min_open_targets_score,
        "allow_predicted": allow_predicted
    }


class ProgressIndicator:
    """
    Simple progress indicator for API queries.
    """

    def __init__(self, total: int, description: str = "Processing", update_interval: int = 10):
        self.total = total
        self.current = 0
        self.description = description
        self.update_interval = update_interval
        self.start_time = time.time()
        self.success_count = 0
        self.error_count = 0
        self.last_update = 0

    def update(self, success: bool = True):
        """Update progress counter."""
        self.current += 1
        if success:
            self.success_count += 1
        else:
            self.error_count += 1

        # Only print progress updates at intervals to avoid spam
        if self.current % self.update_interval == 0 or self.current == self.total:
            self._print_progress()

    def _print_progress(self):
        """Print current progress."""
        elapsed = time.time() - self.start_time
        rate = self.current / elapsed if elapsed > 0 else 0

        if self.current < self.total:
            eta = (self.total - self.current) / rate if rate > 0 else 0
            eta_str = f"{eta:.0f}s" if eta < 60 else f"{eta/60:.1f}m"
        else:
            eta_str = "complete"

        percent = (self.current / self.total) * 100
        status = f"{self.success_count}✓/{self.error_count}✗" if self.error_count > 0 else f"{self.success_count}✓"

        print(f"\r{self.description}: {self.current}/{self.total} ({percent:.1f}%) | {status} | ETA: {eta_str}", end="", flush=True)

        if self.current == self.total:
            print()  # New line at completion


class GeneDiseaseEnricher:
    """
    Enrich genes with disease associations using Grok API and biomedical databases.
    
    Supports:
    - Grok API queries for gene-disease associations
    - Open Targets database (default)
    - DisGeNET database (optional)
    - NCBI Gene database (fallback)
    """
    
    def __init__(
        self,
        grok_api_key: Optional[str] = None,
        disgenet_api_key: Optional[str] = None,
        grok_api_url: str = "https://api.x.ai/v1/chat/completions",
        open_targets_api_url: str = "https://api.platform.opentargets.org/api/v4/graphql",
        disease_term: str = "early-stage prostate cancer",
        use_grok: bool = True,
        use_disgenet: bool = True,
        use_open_targets: bool = True,
        enrichment_profile: Optional[str] = None,
        min_evidence_level: Optional[str] = None,
        min_publications: Optional[int] = None,
        min_disgenet_score: Optional[float] = None,
        min_open_targets_score: Optional[float] = None,
        allow_predicted: Optional[bool] = None,
        cache_enabled: bool = True,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: Optional[int] = DEFAULT_CACHE_TTL_DAYS,
        grok_cache_ttl_days: Optional[int] = DEFAULT_GROK_CACHE_TTL_DAYS,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
        source_max_workers: int = DEFAULT_SOURCE_MAX_WORKERS,
        grok_batch_size: int = DEFAULT_GROK_BATCH_SIZE,
        grok_max_workers: int = DEFAULT_GROK_MAX_WORKERS,
        open_targets_max_workers: int = DEFAULT_OPEN_TARGETS_MAX_WORKERS,
        disgenet_max_workers: int = DEFAULT_DISGENET_MAX_WORKERS,
        azure_key_vault_url: Optional[str] = None,
        azure_secret_name: Optional[str] = None,
        encrypted_file_path: Optional[Path] = None
    ):
        """
        Initialize GeneDiseaseEnricher.

        Args:
            grok_api_key: Grok API key (optional, will use secure storage if not provided)
            disgenet_api_key: DisGeNET API key (optional, will use secure storage if not provided)
            grok_api_url: Grok API endpoint URL
            open_targets_api_url: Open Targets GraphQL endpoint URL
            disease_term: Disease term to search for (e.g., "early-stage prostate cancer")
            use_grok: Whether to use Grok API for enrichment
            use_disgenet: Whether to use DisGeNET database for enrichment
            use_open_targets: Whether to use Open Targets database for enrichment
            enrichment_profile: Preset threshold profile (strict, balanced, permissive)
            min_evidence_level: Minimum evidence level to count as disease-associated
                                (none, low, medium, high)
            min_publications: Minimum number of publications required
            min_disgenet_score: Minimum DisGeNET score required (0.0-1.0)
            min_open_targets_score: Minimum Open Targets score required (0.0-1.0)
            allow_predicted: Whether to allow "predicted" associations
            cache_enabled: Whether to persist cache to disk
            cache_dir: Directory for disk cache (default: ~/.methyl_mapper/cache)
            cache_ttl_days: Disk cache TTL in days for Open Targets / DisGeNET and metadata caches
            grok_cache_ttl_days: Disk cache TTL in days for Grok results (default: 7; set 0 to refresh each run)
            rate_limit_delay: Delay between Grok batch requests (seconds)
            max_retries: Maximum retry attempts for API calls
            source_max_workers: Max workers when querying multiple sources in parallel
            grok_batch_size: Number of genes per Grok batch request
            grok_max_workers: Max concurrent Grok batch requests
            open_targets_max_workers: Max concurrent Open Targets gene requests
            disgenet_max_workers: Max concurrent DisGeNET gene requests
            azure_key_vault_url: Azure Key Vault URL (or set AZURE_KEY_VAULT_URL env var)
            azure_secret_name: Azure Key Vault secret name (or set AZURE_SECRET_NAME env var)
            encrypted_file_path: Path to encrypted credential file (optional)
        """
        # Initialize secure credential managers
        self.grok_credential_manager = SecureCredentialManager(
            credential_name="grok_api_key",
            azure_key_vault_url=azure_key_vault_url,
            azure_secret_name=azure_secret_name or "grok_api_key",
            encrypted_file_path=encrypted_file_path,
            env_var_name="GROK_API_KEY"
        ) if use_grok else None

        self.disgenet_credential_manager = SecureCredentialManager(
            credential_name="disgenet_api_key",
            azure_key_vault_url=azure_key_vault_url,
            azure_secret_name=azure_secret_name or "disgenet_api_key",
            encrypted_file_path=encrypted_file_path,
            env_var_name="DISGENET_API_KEY"
        ) if use_disgenet else None

        # Get credentials using secure managers
        self.grok_api_key = self.grok_credential_manager.get_credential(explicit_key=grok_api_key) if self.grok_credential_manager else None
        self.disgenet_api_key = self.disgenet_credential_manager.get_credential(explicit_key=disgenet_api_key) if self.disgenet_credential_manager else None
        thresholds = _apply_enrichment_profile(
            enrichment_profile=enrichment_profile,
            min_evidence_level=min_evidence_level,
            min_publications=min_publications,
            min_disgenet_score=min_disgenet_score,
            min_open_targets_score=min_open_targets_score,
            allow_predicted=allow_predicted
        )

        self.grok_api_url = grok_api_url
        self.open_targets_api_url = open_targets_api_url
        self.disease_term = disease_term
        self.use_grok = use_grok
        self.use_disgenet = use_disgenet
        self.use_open_targets = use_open_targets
        self.enrichment_profile = enrichment_profile
        self.min_evidence_level = thresholds["min_evidence_level"].lower()
        self.min_publications = max(0, int(thresholds["min_publications"]))
        self.min_disgenet_score = float(thresholds["min_disgenet_score"])
        self.min_open_targets_score = float(thresholds["min_open_targets_score"])
        self.allow_predicted = bool(thresholds["allow_predicted"])
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.source_max_workers = max(1, int(source_max_workers))
        self.grok_batch_size = max(1, int(grok_batch_size))
        self.grok_max_workers = max(1, int(grok_max_workers))
        self.open_targets_max_workers = max(1, int(open_targets_max_workers))
        self.disgenet_max_workers = max(1, int(disgenet_max_workers))

        self.cache_enabled = cache_enabled
        self.cache_ttl_days = None if cache_ttl_days is None else int(cache_ttl_days)
        self.grok_cache_ttl_days = None if grok_cache_ttl_days is None else int(grok_cache_ttl_days)
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else (Path.home() / ".methyl_mapper" / "cache")
        self.cache_file = self.cache_dir / "gene_disease_cache.json"

        if self.min_evidence_level not in EVIDENCE_LEVEL_ORDER:
            raise ValueError(
                f"min_evidence_level must be one of {list(EVIDENCE_LEVEL_ORDER.keys())}, "
                f"got '{min_evidence_level}'"
            )
        if self.min_disgenet_score < 0.0 or self.min_disgenet_score > 1.0:
            raise ValueError("min_disgenet_score must be between 0.0 and 1.0")
        if self.min_open_targets_score < 0.0 or self.min_open_targets_score > 1.0:
            raise ValueError("min_open_targets_score must be between 0.0 and 1.0")
        
        self._thread_local = local()
        self._cache_lock = Lock()
        self._association_runtime_cache: Dict[str, Dict] = {}
        self._association_disk_cache: Dict[str, Dict[str, Union[float, Dict]]] = {}
        self._disease_runtime_cache: Dict[str, Optional[str]] = {}
        self._disease_disk_cache: Dict[str, Dict[str, Optional[Union[str, float]]]] = {}
        self._target_runtime_cache: Dict[str, Optional[str]] = {}
        self._target_disk_cache: Dict[str, Dict[str, Optional[Union[str, float]]]] = {}
        self._cache_dirty = False
        self._load_disk_cache()

    def _create_session(self) -> requests.Session:
        """Create a requests session configured for retryable API traffic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=None,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _get_session(self) -> requests.Session:
        """Return a per-thread session so concurrent requests do not share mutable state."""
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._create_session()
            self._thread_local.session = session
        return session

    def _cache_ttl_for_source(self, source: str) -> Optional[int]:
        """Resolve disk TTL for the given cache source."""
        if source == "grok":
            return self.grok_cache_ttl_days
        return self.cache_ttl_days

    @staticmethod
    def _dedupe_gene_names(gene_names: List[str]) -> List[str]:
        """Normalize and deduplicate gene names while preserving input order."""
        deduped: List[str] = []
        seen = set()
        for gene in gene_names:
            normalized = str(gene).strip()
            if not normalized:
                continue
            gene_upper = normalized.upper()
            if gene_upper in seen:
                continue
            seen.add(gene_upper)
            deduped.append(normalized)
        return deduped

    def _build_enrichment_payload(
        self,
        gene_names: List[str],
        disease_term: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """Fetch enrichment results once for a set of genes and return reusable payload."""
        disease_term = disease_term or self.disease_term
        unique_genes = self._dedupe_gene_names(gene_names)
        if not unique_genes:
            return {
                "genes": [],
                "hyperlinks": {},
                "grok": {},
                "open_targets": {},
                "disgenet": {},
                "merged": {},
            }

        logger.info(f"Enriching {len(unique_genes)} unique genes with disease associations...")
        source_results = self._query_enabled_sources(unique_genes, disease_term)
        hyperlinks = self._generate_gene_hyperlinks(unique_genes)
        merged_results = self._merge_results(
            source_results.get("grok", {}),
            source_results.get("open_targets", {}),
            source_results.get("disgenet", {}),
            unique_genes,
        )
        # Diagnostic: counts per source (raw) and after thresholds
        n_grok_raw = sum(1 for g in unique_genes if source_results.get("grok", {}).get(g.upper(), {}).get("associated"))
        n_ot_raw = sum(1 for g in unique_genes if source_results.get("open_targets", {}).get(g.upper(), {}).get("associated"))
        n_merged_pass = sum(1 for g in unique_genes if self._association_meets_thresholds(merged_results.get(g.upper(), {})))
        logger.info(f"Disease enrichment: Grok raw={n_grok_raw}, Open Targets raw={n_ot_raw}, merged (pass thresholds)={n_merged_pass} genes")
        if n_merged_pass == 0 and (n_grok_raw > 0 or n_ot_raw > 0):
            logger.warning(
                "All genes have disease_associated=False after thresholds. Associations were found (Grok/Open Targets) but filtered out. "
                "Use --enrich-profile permissive or lower min_evidence_level / allow_predicted to include them."
            )
        elif n_merged_pass == 0 and len(unique_genes) > 0:
            logger.warning(
                "No disease associations returned from any source. Check disease_term, Grok API key (GROK_API_KEY), and Open Targets connectivity."
            )
        return {
            "genes": unique_genes,
            "hyperlinks": hyperlinks,
            "grok": source_results.get("grok", {}),
            "open_targets": source_results.get("open_targets", {}),
            "disgenet": source_results.get("disgenet", {}),
            "merged": merged_results,
        }

    def _query_enabled_sources(
        self,
        gene_names: List[str],
        disease_term: str,
    ) -> Dict[str, Dict[str, Dict]]:
        """Run enabled enrichment sources, overlapping network I/O when possible."""
        tasks = []
        if self.use_grok:
            tasks.append(("grok", self.query_grok_api))
        if self.use_open_targets:
            tasks.append(("open_targets", self.query_open_targets))
        if self.use_disgenet:
            tasks.append(("disgenet", self.query_disgenet))

        results: Dict[str, Dict[str, Dict]] = {
            "grok": {},
            "open_targets": {},
            "disgenet": {},
        }
        if not tasks:
            return results

        if len(tasks) == 1:
            name, func = tasks[0]
            results[name] = func(gene_names, disease_term)
            return results

        max_workers = min(self.source_max_workers, len(tasks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_name = {
                executor.submit(func, gene_names, disease_term): name
                for name, func in tasks
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    logger.warning(f"{name} enrichment failed: {exc}")
                    results[name] = {}

        return results

    def _apply_enrichment_payload(
        self,
        df: pd.DataFrame,
        gene_column: str,
        payload: Dict[str, Dict],
        separate_sources: bool = False,
    ) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """Apply a pre-fetched enrichment payload to one or more dataframes."""
        hyperlinks = payload.get("hyperlinks", {})
        sources_enabled = {
            "grok": self.use_grok,
            "open_targets": self.use_open_targets,
            "disgenet": self.use_disgenet,
        }
        sources_enabled = {k: v for k, v in sources_enabled.items() if v}

        if separate_sources and len(sources_enabled) > 1:
            logger.info("Returning separate results for each source...")
            result_dfs: Dict[str, pd.DataFrame] = {}
            for source_name in ("grok", "open_targets", "disgenet"):
                if source_name in sources_enabled:
                    source_df = df.copy()
                    source_df = self._add_enrichment_columns(
                        source_df,
                        payload.get(source_name, {}),
                        gene_column,
                        source_name,
                        hyperlinks,
                    )
                    result_dfs[source_name] = source_df

            merged_df = df.copy()
            merged_df = self._add_enrichment_columns(
                merged_df,
                payload.get("merged", {}),
                gene_column,
                "merged",
                hyperlinks,
            )
            result_dfs["merged"] = merged_df
            return result_dfs

        enriched_df = df.copy()
        enriched_df = self._add_enrichment_columns(
            enriched_df,
            payload.get("merged", {}),
            gene_column,
            "merged",
            hyperlinks,
        )
        return enriched_df
    
    def query_grok_api(
        self,
        gene_names: List[str],
        disease_term: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Query Grok API for gene-disease associations.
        
        Args:
            gene_names: List of gene symbols to query
            disease_term: Disease term (defaults to self.disease_term)
            
        Returns:
            Dictionary mapping gene_name -> association info
        """
        if not self.grok_api_key:
            logger.warning("Grok API key not provided. Skipping Grok API queries.")
            return {}
        
        disease_term = disease_term or self.disease_term
        gene_names = self._dedupe_gene_names(gene_names)
        
        cached_results = self._cache_get_batch("grok", gene_names, disease_term)
        uncached_genes = [g for g in gene_names if g.upper() not in cached_results]
        
        if cached_results:
            logger.info(f"Using cache for {len(cached_results)} genes (querying Grok for {len(uncached_genes)} new)")
        
        if not uncached_genes:
            logger.info(f"✅ Retrieved all {len(cached_results)} genes from cache")
            return cached_results
        
        logger.info(f"Querying Grok API for {len(uncached_genes)} genes associated with '{disease_term}'...")

        results = cached_results.copy()
        batches = [
            uncached_genes[i:i + self.grok_batch_size]
            for i in range(0, len(uncached_genes), self.grok_batch_size)
        ]
        total_batches = len(batches)
        progress = ProgressIndicator(total_batches, "Grok API batches", update_interval=1)

        if self.grok_max_workers == 1 or total_batches == 1:
            for batch_num, batch in enumerate(batches, start=1):
                batch_results, success = self._query_grok_batch(batch, disease_term, batch_num)
                results.update(batch_results)
                progress.update(success=success)
                if self.rate_limit_delay > 0 and batch_num < total_batches:
                    time.sleep(self.rate_limit_delay)
        else:
            with ThreadPoolExecutor(max_workers=min(self.grok_max_workers, total_batches)) as executor:
                future_to_batch_num = {
                    executor.submit(self._query_grok_batch, batch, disease_term, batch_num): batch_num
                    for batch_num, batch in enumerate(batches, start=1)
                }
                for future in as_completed(future_to_batch_num):
                    try:
                        batch_results, success = future.result()
                    except Exception as exc:
                        logger.warning(f"Grok API batch failed unexpectedly: {exc}")
                        batch_results, success = {}, False
                    results.update(batch_results)
                    progress.update(success=success)

        logger.info(f"✅ Retrieved disease associations for {len(results)} genes from Grok API ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results

    def _query_grok_batch(
        self,
        batch: List[str],
        disease_term: str,
        batch_num: int,
    ) -> Tuple[Dict[str, Dict], bool]:
        """Query one Grok batch with retries and batch-local caching."""
        prompt = self._create_grok_prompt(batch, disease_term)
        last_error = None
        base_timeout = 60
        per_gene_timeout = 20

        for attempt in range(self.max_retries):
            try:
                timeout = max(base_timeout, base_timeout + len(batch) * per_gene_timeout)
                if attempt > 0:
                    timeout = int(timeout * (1.5 ** attempt))
                logger.debug(
                    f"Querying batch {batch_num} with {len(batch)} genes "
                    f"(timeout: {timeout}s, attempt {attempt + 1}/{self.max_retries})"
                )
                response = self._call_grok_api(prompt, timeout=timeout)
                batch_results = self._parse_grok_response(response, batch)
                for gene_name, association_info in batch_results.items():
                    self._cache_set(self._cache_key("grok", gene_name, disease_term), association_info)
                return batch_results, True
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    delay = (2 ** attempt) * 5
                    logger.warning(
                        f"Grok API query failed for batch {batch_num} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {exc}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)

        logger.warning(
            f"Grok API query failed for batch {batch_num} after {self.max_retries} attempts: {last_error}"
        )
        return {}, False
    
    def _create_grok_prompt(self, gene_names: List[str], disease_term: str) -> str:
        """Create a prompt for Grok API."""
        genes_str = ", ".join(gene_names)
        disease_lower = disease_term.lower()
        cancer_instruction = ""
        if "cancer" in disease_lower or "carcinoma" in disease_lower or "tumor" in disease_lower:
            cancer_instruction = (
                " For cancer (e.g. prostate cancer): mark associated: true for genes that are biomarkers, "
                "in relevant pathways (e.g. androgen signaling, cell cycle, DNA repair), therapeutic targets, "
                "or that appear in cancer literature—most cancer-related gene sets will have many associations."
            )
        
        prompt = f"""You are a biomedical expert. For each of the following genes: {genes_str}

Provide their association with "{disease_term}" in JSON format. Use a PERMISSIVE interpretation: mark a gene as associated (associated: true) if there is ANY reported or suspected link in the literature—including direct, indirect, predicted, or emerging evidence. Do not mark genes as unrelated (associated: false) when they have known or plausible roles in {disease_term}; when in doubt, prefer associated: true with an appropriate evidence_level.{cancer_instruction}

For each gene provide:
1. "gene_name": The gene symbol (exactly as in the list above)
2. "associated": true or false (boolean). Use true if any reported/suspected association exists; prefer true when evidence exists.
3. "association_type": One of ["direct", "indirect", "predicted", "none"]
4. "evidence_level": One of ["high", "medium", "low", "none"]
5. "description": A brief description of the association (or null if none)
6. "publications": Number of publications mentioning this association (or 0)
7. "functional_role": Brief description of the gene's role in {disease_term} (or null)
8. "gene_basic_description": One-sentence summary of the gene's general biological function (or null)

Return ONLY a valid JSON array—no other text. Example:
[
  {{"gene_name": "GENE1", "associated": true, "association_type": "direct", "evidence_level": "high", "description": "...", "publications": 15, "functional_role": "...", "gene_basic_description": "Encodes a tumor suppressor protein involved in DNA repair."}},
  {{"gene_name": "GENE2", "associated": false, "association_type": "none", "evidence_level": "none", "description": null, "publications": 0, "functional_role": null, "gene_basic_description": null}}
]
"""
        return prompt
    
    def _call_grok_api(self, prompt: str, timeout: int = 30) -> Dict:
        """
        Call Grok API and return response.
        
        Args:
            prompt: The prompt to send to the API
            timeout: Request timeout in seconds (default: 30)
        """
        headers = {
            "Authorization": f"Bearer {self.grok_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "grok-4-latest",  # Updated to latest Grok model
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Low temperature for factual responses
            "max_tokens": 2000,
            "stream": False
        }
        
        logger.debug(f"Calling Grok API with timeout={timeout}s for prompt length={len(prompt)}")
        response = self._get_session().post(
            self.grok_api_url,
            headers=headers,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        
        return response.json()
    
    def _normalize_associated(self, value: Union[bool, str, int, None]) -> bool:
        """Normalize Grok's 'associated' field to bool (handles string 'true'/'yes'/'1' etc.)."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        s = str(value).strip().lower()
        if s in ("true", "yes", "1", "y"):
            return True
        if s in ("false", "no", "0", "n", "none", ""):
            return False
        # Any other non-empty string that suggests association
        return len(s) > 0 and s not in ("no association", "not associated", "unrelated")

    def _extract_json_array_from_content(self, content: str) -> List[Dict]:
        """Extract a JSON array from API response (handles markdown, object wrapper, raw array)."""
        import re
        # Strip markdown code blocks (```json ... ``` or ``` ... ```)
        stripped = content.strip()
        if stripped.startswith("```json"):
            stripped = stripped[7:].lstrip()
        elif stripped.startswith("```"):
            stripped = stripped[3:].lstrip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
        stripped = stripped.strip()
        # Try parse full content as JSON
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("genes", "associations", "results", "data", "items"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                # Any first list value
                for v in parsed.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            pass
        # Find first top-level JSON array by bracket matching
        start = stripped.find("[")
        if start == -1:
            raise ValueError("No JSON array found in response")
        depth = 0
        in_string = None
        escape = False
        for i, c in enumerate(stripped[start:], start=start):
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if in_string:
                if c == in_string:
                    in_string = None
                continue
            if c in ('"', "'"):
                in_string = c
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    json_str = stripped[start : i + 1]
                    return json.loads(json_str)
        raise ValueError("Unclosed JSON array in response")

    def _parse_grok_response(self, response: Dict, gene_names: List[str]) -> Dict[str, Dict]:
        """Parse Grok API response into gene-disease associations."""
        import re
        
        results = {}
        
        try:
            # Extract content from response
            # Grok API response format: {'choices': [{'message': {'content': '...'}}]}
            content = ""
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0].get('message', {}).get('content', '')
            elif 'content' in response:
                content = response['content']
            else:
                logger.warning(f"Unexpected Grok API response format: {list(response.keys())}")
                content = str(response)
            
            if not content:
                raise ValueError("Empty response from Grok API")
            
            try:
                associations = self._extract_json_array_from_content(content)
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Could not extract JSON array from Grok response: {e}")
                # Fallback: infer from text
                associations = []
                content_upper = content.upper()
                for gene in gene_names:
                    gene_upper = gene.upper()
                    if gene_upper in content_upper:
                        associations.append({
                            'gene_name': gene_upper,
                            'associated': True,
                            'association_type': 'predicted',
                            'evidence_level': 'low',
                            'description': "Mentioned in context of disease",
                            'publications': 0,
                            'functional_role': None,
                            'gene_basic_description': None
                        })
                    else:
                        associations.append({
                            'gene_name': gene_upper,
                            'associated': False,
                            'association_type': 'none',
                            'evidence_level': 'none',
                            'description': None,
                            'publications': 0,
                            'functional_role': None,
                            'gene_basic_description': None
                        })
            
            if not isinstance(associations, list):
                associations = []
            
            # Convert to dictionary keyed by gene_name; normalize 'associated' (Grok may return string)
            for assoc in associations:
                if not isinstance(assoc, dict):
                    continue
                gene_name = str(assoc.get('gene_name', assoc.get('gene', ''))).strip().upper()
                if not gene_name:
                    continue
                raw_associated = assoc.get('associated', assoc.get('is_associated', assoc.get('has_association', False)))
                results[gene_name] = {
                    'associated': self._normalize_associated(raw_associated),
                    'association_type': str(assoc.get('association_type', 'none')).lower() or 'none',
                    'evidence_level': str(assoc.get('evidence_level', 'none')).lower() or 'none',
                    'description': assoc.get('description'),
                    'publications': int(assoc.get('publications', 0)) if assoc.get('publications') is not None else 0,
                    'functional_role': assoc.get('functional_role'),
                    'gene_basic_description': assoc.get('gene_basic_description'),
                    'source': 'grok_api'
                }
            
            # Fill in missing genes as "not associated"
            for gene in gene_names:
                gene_upper = gene.upper()
                if gene_upper not in results:
                    results[gene_upper] = {
                        'associated': False,
                        'association_type': 'none',
                        'evidence_level': 'none',
                        'description': None,
                        'publications': 0,
                        'functional_role': None,
                        'gene_basic_description': None,
                        'source': 'grok_api'
                    }
            
            n_associated = sum(1 for r in results.values() if r.get('associated'))
            logger.info(f"Grok API parse: {n_associated}/{len(results)} genes marked associated with disease")
                    
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse Grok API response: {e}")
            if 'content' in locals():
                logger.debug(f"Response content (first 500 chars): {content[:500]}")
            for gene in gene_names:
                results[gene.upper()] = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'gene_basic_description': None,
                    'source': 'grok_api_parse_error'
                }
        
        return results
    
    def query_disgenet(
        self,
        gene_names: List[str],
        disease_term: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Query DisGeNET database for gene-disease associations (fallback).
        
        Args:
            gene_names: List of gene symbols
            disease_term: Disease term (used for filtering)
            
        Returns:
            Dictionary mapping gene_name -> association info
        """
        if not self.use_disgenet or not self.disgenet_api_key:
            if not self.use_disgenet:
                logger.debug("DisGeNET queries disabled")
            else:
                logger.warning("DisGeNET API key not available")
            return {}

        disease_term = disease_term or self.disease_term
        gene_names = self._dedupe_gene_names(gene_names)

        cached_results = self._cache_get_batch("disgenet", gene_names, disease_term)
        uncached_genes = [g for g in gene_names if g.upper() not in cached_results]

        if cached_results:
            logger.debug(f"Found {len(cached_results)} genes in cache")

        if not uncached_genes:
            logger.info(f"✅ Retrieved all {len(cached_results)} genes from cache")
            return cached_results

        logger.info(f"Querying DisGeNET for {len(uncached_genes)} genes...")

        disgenet_api_key = self.disgenet_api_key

        results = cached_results.copy()
        progress = ProgressIndicator(len(uncached_genes), "DisGeNET genes", update_interval=50)

        if self.disgenet_max_workers == 1 or len(uncached_genes) == 1:
            for gene in uncached_genes:
                gene_upper, association_info, success = self._query_disgenet_gene(gene, disease_term, disgenet_api_key)
                results[gene_upper] = association_info
                progress.update(success=success)
        else:
            with ThreadPoolExecutor(max_workers=min(self.disgenet_max_workers, len(uncached_genes))) as executor:
                future_to_gene = {
                    executor.submit(self._query_disgenet_gene, gene, disease_term, disgenet_api_key): gene
                    for gene in uncached_genes
                }
                for future in as_completed(future_to_gene):
                    gene = future_to_gene[future]
                    try:
                        gene_upper, association_info, success = future.result()
                    except Exception as exc:
                        logger.debug(f"DisGeNET query failed for {gene}: {exc}")
                        gene_upper = gene.upper()
                        association_info = {
                            'associated': False,
                            'association_type': 'none',
                            'evidence_level': 'none',
                            'description': None,
                            'publications': 0,
                            'functional_role': None,
                            'source': 'disgenet_error'
                        }
                        self._cache_set(self._cache_key("disgenet", gene, disease_term), association_info)
                        success = False
                    results[gene_upper] = association_info
                    progress.update(success=success)
        
        logger.info(f"✅ Retrieved associations for {len(results)} genes from DisGeNET ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results

    def _query_disgenet_gene(
        self,
        gene: str,
        disease_term: str,
        disgenet_api_key: str,
    ) -> Tuple[str, Dict, bool]:
        """Query DisGeNET for one gene symbol."""
        gene_upper = gene.upper()
        base_url = "https://api.disgenet.com/api/v1/gda/gene/"
        try:
            url = f"{base_url}{gene}"
            headers = {"Authorization": f"Bearer {disgenet_api_key}"}
            response = self._get_session().get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if disease_term:
                disease_lower = disease_term.lower()
                relevant_associations = [
                    entry for entry in data
                    if disease_lower in entry.get('disease_name', '').lower()
                    or disease_lower in entry.get('disease_class', '').lower()
                ]
            else:
                relevant_associations = data

            if relevant_associations:
                best = max(relevant_associations, key=lambda x: x.get('score', 0))
                association_info = {
                    'associated': True,
                    'association_type': 'database',
                    'evidence_level': 'high' if best.get('score', 0) > 0.5 else 'medium',
                    'description': best.get('disease_name'),
                    'publications': best.get('nof_pmids', 0),
                    'functional_role': best.get('disease_class'),
                    'source': 'disgenet',
                    'score': best.get('score', 0),
                }
            else:
                association_info = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'disgenet',
                }
            self._cache_set(self._cache_key("disgenet", gene, disease_term), association_info)
            return gene_upper, association_info, True
        except Exception as exc:
            logger.debug(f"DisGeNET query failed for {gene}: {exc}")
            association_info = {
                'associated': False,
                'association_type': 'none',
                'evidence_level': 'none',
                'description': None,
                'publications': 0,
                'functional_role': None,
                'source': 'disgenet_error'
            }
            self._cache_set(self._cache_key("disgenet", gene, disease_term), association_info)
            return gene_upper, association_info, False

    def query_open_targets(
        self,
        gene_names: List[str],
        disease_term: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Query Open Targets for gene-disease associations.
        """
        if not self.use_open_targets:
            logger.debug("Open Targets queries disabled")
            return {}

        disease_term = disease_term or self.disease_term
        gene_names = self._dedupe_gene_names(gene_names)

        # Resolve disease ID once per call
        disease_id = self._resolve_open_targets_disease_id(disease_term)
        if not disease_id:
            logger.warning(f"Open Targets: no disease match for '{disease_term}'")
            return {}

        cached_results = self._cache_get_batch("open_targets", gene_names, disease_term)
        uncached_genes = [g for g in gene_names if g.upper() not in cached_results]

        if cached_results:
            logger.debug(f"Found {len(cached_results)} Open Targets genes in cache")

        if not uncached_genes:
            logger.info(f"✅ Retrieved all {len(cached_results)} genes from Open Targets cache")
            return cached_results

        logger.info(f"Querying Open Targets for {len(uncached_genes)} genes...")
        results = cached_results.copy()

        progress = ProgressIndicator(len(uncached_genes), "Open Targets genes", update_interval=50)

        if self.open_targets_max_workers == 1 or len(uncached_genes) == 1:
            for gene in uncached_genes:
                gene_upper, association_info, success = self._query_open_targets_gene(gene, disease_term, disease_id)
                results[gene_upper] = association_info
                progress.update(success=success)
        else:
            with ThreadPoolExecutor(max_workers=min(self.open_targets_max_workers, len(uncached_genes))) as executor:
                future_to_gene = {
                    executor.submit(self._query_open_targets_gene, gene, disease_term, disease_id): gene
                    for gene in uncached_genes
                }
                for future in as_completed(future_to_gene):
                    gene = future_to_gene[future]
                    try:
                        gene_upper, association_info, success = future.result()
                    except Exception as exc:
                        logger.debug(f"Open Targets query failed for {gene}: {exc}")
                        gene_upper = gene.upper()
                        association_info = {
                            'associated': False,
                            'association_type': 'none',
                            'evidence_level': 'none',
                            'description': None,
                            'publications': 0,
                            'functional_role': None,
                            'source': 'open_targets_error'
                        }
                        self._cache_set(self._cache_key("open_targets", gene, disease_term), association_info)
                        success = False
                    results[gene_upper] = association_info
                    progress.update(success=success)

        logger.info(f"✅ Retrieved associations for {len(results)} genes from Open Targets ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results

    def _query_open_targets_gene(
        self,
        gene: str,
        disease_term: str,
        disease_id: str,
    ) -> Tuple[str, Dict, bool]:
        """Query Open Targets for one gene symbol."""
        gene_upper = gene.upper()
        try:
            target_id = self._resolve_open_targets_target_id(gene)
            if not target_id:
                association_info = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'open_targets'
                }
            else:
                assoc = self._fetch_open_targets_association(target_id, disease_id)
                association_info = assoc or {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'open_targets'
                }
            self._cache_set(self._cache_key("open_targets", gene, disease_term), association_info)
            return gene_upper, association_info, True
        except Exception as exc:
            logger.debug(f"Open Targets query failed for {gene}: {exc}")
            association_info = {
                'associated': False,
                'association_type': 'none',
                'evidence_level': 'none',
                'description': None,
                'publications': 0,
                'functional_role': None,
                'source': 'open_targets_error'
            }
            self._cache_set(self._cache_key("open_targets", gene, disease_term), association_info)
            return gene_upper, association_info, False
    
    def enrich_gene_dataframe(
        self,
        df: pd.DataFrame,
        gene_column: str = 'gene_name',
        disease_term: Optional[str] = None,
        separate_sources: bool = False
    ) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        Enrich a DataFrame with disease associations.

        Args:
            df: DataFrame with gene information
            gene_column: Column name containing gene symbols
            disease_term: Disease term to search for
            separate_sources: If True and both sources enabled, return dict with separate DataFrames

        Returns:
            DataFrame with added disease association columns, or dict of DataFrames if separate_sources=True
        """
        if gene_column not in df.columns:
            raise ValueError(f"Column '{gene_column}' not found in DataFrame")
        
        unique_genes = self._dedupe_gene_names(df[gene_column].dropna().unique().tolist())
        
        if not unique_genes:
            logger.warning("No genes found in DataFrame; adding disease columns with empty values.")
            payload = self._build_enrichment_payload([])
            return self._apply_enrichment_payload(df.copy(), gene_column, payload, separate_sources=False)

        payload = self._build_enrichment_payload(unique_genes, disease_term)
        enriched_df = self._apply_enrichment_payload(df.copy(), gene_column, payload, separate_sources=separate_sources)
        if isinstance(enriched_df, dict):
            merged_df = enriched_df['merged']
            n_associated = merged_df['disease_associated'].sum()
            logger.info(
                f"✅ Enriched DataFrame: {n_associated}/{len(merged_df)} genes associated with "
                f"'{disease_term or self.disease_term}'"
            )
            return enriched_df

        # Log summary
        n_associated = enriched_df['disease_associated'].sum()
        logger.info(f"✅ Enriched DataFrame: {n_associated}/{len(enriched_df)} genes associated with '{disease_term or self.disease_term}'")

        return enriched_df

    def _merge_results(
        self,
        grok_results: Dict[str, Dict],
        open_targets_results: Dict[str, Dict],
        disgenet_results: Dict[str, Dict],
        unique_genes: List[str]
    ) -> Dict[str, Dict]:
        """Merge results from multiple sources with priority logic."""
        merged_results = {}
        for gene in unique_genes:
            gene_upper = gene.upper()
            grok_entry = grok_results.get(gene_upper, {})

            # Priority: Associated results first, then any available results
            if gene_upper in grok_results and self._association_meets_thresholds(grok_results[gene_upper]):
                merged_results[gene_upper] = dict(grok_results[gene_upper])
            elif gene_upper in open_targets_results and self._association_meets_thresholds(open_targets_results[gene_upper]):
                merged_results[gene_upper] = dict(open_targets_results[gene_upper])
            elif gene_upper in disgenet_results and self._association_meets_thresholds(disgenet_results[gene_upper]):
                merged_results[gene_upper] = dict(disgenet_results[gene_upper])
            elif gene_upper in grok_results:
                merged_results[gene_upper] = dict(grok_results[gene_upper])
            elif gene_upper in open_targets_results:
                merged_results[gene_upper] = dict(open_targets_results[gene_upper])
            elif gene_upper in disgenet_results:
                merged_results[gene_upper] = dict(disgenet_results[gene_upper])
            else:
                merged_results[gene_upper] = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'gene_basic_description': grok_entry.get('gene_basic_description'),
                    'source': 'none',
                    'score': 0.0,
                }

            # gene_basic_description only comes from Grok; inject when we chose another source
            if merged_results[gene_upper].get('gene_basic_description') is None and grok_entry.get('gene_basic_description'):
                merged_results[gene_upper]['gene_basic_description'] = grok_entry['gene_basic_description']

            # score comes from Open Targets (or DisGeNET); Grok does not return it — inject when missing
            if merged_results[gene_upper].get('score') is None or merged_results[gene_upper].get('score') == 0:
                ot_score = open_targets_results.get(gene_upper, {}).get('score')
                if ot_score is not None and float(ot_score) != 0:
                    merged_results[gene_upper]['score'] = float(ot_score)
                elif merged_results[gene_upper].get('score') is None:
                    merged_results[gene_upper]['score'] = 0.0
        return merged_results

    def _association_meets_thresholds(self, assoc: Dict) -> bool:
        """Determine if association meets evidence thresholds."""
        if not assoc or not assoc.get('associated', False):
            return False

        assoc_type = str(assoc.get('association_type', 'none')).lower()
        if not self.allow_predicted and assoc_type == 'predicted':
            return False

        evidence_level = str(assoc.get('evidence_level', 'none')).lower()
        if EVIDENCE_LEVEL_ORDER.get(evidence_level, 0) < EVIDENCE_LEVEL_ORDER[self.min_evidence_level]:
            return False

        publications = assoc.get('publications', 0) or 0
        if publications < self.min_publications:
            return False

        if assoc.get('source') == 'disgenet':
            score = assoc.get('score', 0.0) or 0.0
            if score < self.min_disgenet_score:
                return False
        if assoc.get('source') == 'open_targets':
            score = assoc.get('score', 0.0) or 0.0
            if score < self.min_open_targets_score:
                return False

        return True

    def _add_enrichment_columns(self, df: pd.DataFrame, results: Dict[str, Dict], gene_column: str, source_prefix: str, hyperlinks: Dict[str, Dict]) -> pd.DataFrame:
        """Add enrichment columns to DataFrame with hyperlinks."""
        # Disease association columns
        df['disease_associated_raw'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('associated', False) if pd.notna(x) else False
        )
        df['disease_associated'] = df[gene_column].str.upper().map(
            lambda x: self._association_meets_thresholds(results.get(x, {})) if pd.notna(x) else False
        )
        df['disease_association_type'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('association_type', 'none') if pd.notna(x) else 'none'
        )
        df['disease_evidence_level'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('evidence_level', 'none') if pd.notna(x) else 'none'
        )
        df['disease_description'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('description') if pd.notna(x) else None
        )
        df['disease_publications'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('publications', 0) if pd.notna(x) else 0
        )
        df['disease_functional_role'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('functional_role') if pd.notna(x) else None
        )
        df['disease_source'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('source', 'none') if pd.notna(x) else 'none'
        )
        df['disease_score'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('score', 0.0) if pd.notna(x) else 0.0
        )

        # Add hyperlinks
        df['gene_ncbi_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('ncbi', '') if pd.notna(x) else ''
        )
        df['gene_ensembl_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('ensembl', '') if pd.notna(x) else ''
        )
        df['gene_uniprot_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('uniprot', '') if pd.notna(x) else ''
        )
        df['gene_omim_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('omim', '') if pd.notna(x) else ''
        )

        # gene_basic_description: only from Grok (Open Targets does not provide it)
        df['gene_basic_description'] = df[gene_column].str.upper().map(
            lambda x: (results.get(x, {}).get('gene_basic_description') or '') if pd.notna(x) else ''
        )
        # If no gene has a description (all empty or NaN), remove the column from export
        if 'gene_basic_description' in df.columns:
            filled = df['gene_basic_description'].fillna('').astype(str).str.strip()
            if (filled == '').all():
                df.drop(columns=['gene_basic_description'], inplace=True)

        return df

    def _generate_gene_hyperlinks(self, gene_names: List[str]) -> Dict[str, Dict]:
        """Generate hyperlinks for gene databases (NCBI, Ensembl, UniProt, OMIM)."""
        hyperlinks = {}
        for gene in gene_names:
            gene_upper = gene.upper()
            hyperlinks[gene_upper] = {
                'ncbi': f'https://www.ncbi.nlm.nih.gov/gene/?term={gene}',
                'ensembl': f'https://www.ensembl.org/id/{gene}',
                'uniprot': f'https://www.uniprot.org/uniprotkb?query={gene}',
                'omim': f'https://www.omim.org/search?search={gene}',
            }
        return hyperlinks

    def _cache_key(self, source: str, gene_name: str, disease_term: str) -> str:
        """Build a cache key with source separation."""
        return f"{source}:{gene_name.upper()}:{disease_term}"

    def _cache_parse_key(self, key: str) -> tuple:
        """Parse cache key into (source, gene, disease_term)."""
        parts = key.split(":", 2)
        if len(parts) != 3:
            return ("", "", "")
        return (parts[0], parts[1].upper(), parts[2])

    def _cache_get(self, key: str) -> Optional[Dict]:
        """Retrieve a cached association, honoring TTL."""
        source, gene, disease_term = self._cache_parse_key(key)
        if not source:
            return None
        return self._cache_get_batch(source, [gene], disease_term).get(gene)

    def _cache_get_batch(
        self, source: str, gene_names: List[str], disease_term: str
    ) -> Dict[str, Dict]:
        """Batch lookup with same-run memoization plus optional disk-backed reuse."""
        if not gene_names:
            return {}
        result = {}
        with self._cache_lock:
            for gene_name in gene_names:
                gene_upper = str(gene_name).strip().upper()
                if not gene_upper or gene_upper in result:
                    continue
                key = self._cache_key(source, gene_upper, disease_term)

                runtime_value = self._association_runtime_cache.get(key)
                if isinstance(runtime_value, dict):
                    result[gene_upper] = runtime_value
                    continue

                disk_entry = self._association_disk_cache.get(key)
                if not disk_entry:
                    continue

                ts = disk_entry.get("ts")
                ts = float(ts) if ts is not None else None
                if not self._is_cache_valid(ts, source):
                    self._association_disk_cache.pop(key, None)
                    self._cache_dirty = True
                    continue

                value = disk_entry.get("value")
                if isinstance(value, dict):
                    result[gene_upper] = value
                    self._association_runtime_cache[key] = value
        return result

    def _cache_set(self, key: str, value: Dict) -> None:
        """Store a cached association in runtime cache and, when enabled, on disk."""
        source, gene, disease_term = self._cache_parse_key(key)
        if not source:
            return
        ts = time.time()
        with self._cache_lock:
            self._association_runtime_cache[key] = value
            ttl = self._cache_ttl_for_source(source)
            if self.cache_enabled and ttl != 0:
                self._association_disk_cache[key] = {"ts": ts, "value": value}
                self._cache_dirty = True
            elif key in self._association_disk_cache:
                self._association_disk_cache.pop(key, None)
                self._cache_dirty = True

    def _disease_cache_get(self, key: str) -> Optional[str]:
        with self._cache_lock:
            if key in self._disease_runtime_cache:
                value = self._disease_runtime_cache[key]
                return None if value == NULL_CACHE_VALUE else value
            entry = self._disease_disk_cache.get(key)
            if not entry:
                return None
            ts = entry.get("ts")
            ts = float(ts) if ts is not None else None
            if not self._is_cache_valid(ts, "open_targets_disease"):
                self._disease_disk_cache.pop(key, None)
                self._cache_dirty = True
                return None
            value = entry.get("value")
            resolved = str(value) if value is not None else NULL_CACHE_VALUE
            self._disease_runtime_cache[key] = resolved
            return None if resolved == NULL_CACHE_VALUE else resolved

    def _disease_cache_set(self, key: str, value: Optional[str]) -> None:
        stored_value = value if value is not None else NULL_CACHE_VALUE
        with self._cache_lock:
            self._disease_runtime_cache[key] = stored_value
            ttl = self._cache_ttl_for_source("open_targets_disease")
            if self.cache_enabled and ttl != 0:
                self._disease_disk_cache[key] = {"ts": time.time(), "value": stored_value}
                self._cache_dirty = True
            elif key in self._disease_disk_cache:
                self._disease_disk_cache.pop(key, None)
                self._cache_dirty = True

    def _target_cache_get(self, gene_name: str) -> Optional[str]:
        key = str(gene_name).strip().upper()
        with self._cache_lock:
            if key in self._target_runtime_cache:
                value = self._target_runtime_cache[key]
                return None if value == NULL_CACHE_VALUE else value
            entry = self._target_disk_cache.get(key)
            if not entry:
                return None
            ts = entry.get("ts")
            ts = float(ts) if ts is not None else None
            if not self._is_cache_valid(ts, "open_targets_target"):
                self._target_disk_cache.pop(key, None)
                self._cache_dirty = True
                return None
            value = entry.get("value")
            resolved = str(value) if value is not None else NULL_CACHE_VALUE
            self._target_runtime_cache[key] = resolved
            return None if resolved == NULL_CACHE_VALUE else resolved

    def _target_cache_set(self, gene_name: str, target_id: Optional[str]) -> None:
        key = str(gene_name).strip().upper()
        stored_value = target_id if target_id is not None else NULL_CACHE_VALUE
        with self._cache_lock:
            self._target_runtime_cache[key] = stored_value
            ttl = self._cache_ttl_for_source("open_targets_target")
            if self.cache_enabled and ttl != 0:
                self._target_disk_cache[key] = {"ts": time.time(), "value": stored_value}
                self._cache_dirty = True
            elif key in self._target_disk_cache:
                self._target_disk_cache.pop(key, None)
                self._cache_dirty = True

    def _is_cache_valid(self, ts: Optional[float], source: str) -> bool:
        if ts is None:
            return True
        ttl = self._cache_ttl_for_source(source)
        if ttl == 0:
            return False
        if ttl is None:
            return True
        return (time.time() - ts) <= (ttl * 86400)

    def _prune_disk_cache_locked(self) -> None:
        """Drop expired persisted cache entries. Caller must hold `_cache_lock`."""
        stale_associations = [
            key for key, entry in self._association_disk_cache.items()
            if not self._is_cache_valid(
                float(entry.get("ts")) if entry.get("ts") is not None else None,
                self._cache_parse_key(key)[0],
            )
        ]
        for key in stale_associations:
            self._association_disk_cache.pop(key, None)

        stale_diseases = [
            key for key, entry in self._disease_disk_cache.items()
            if not self._is_cache_valid(
                float(entry.get("ts")) if entry.get("ts") is not None else None,
                "open_targets_disease",
            )
        ]
        for key in stale_diseases:
            self._disease_disk_cache.pop(key, None)

        stale_targets = [
            key for key, entry in self._target_disk_cache.items()
            if not self._is_cache_valid(
                float(entry.get("ts")) if entry.get("ts") is not None else None,
                "open_targets_target",
            )
        ]
        for key in stale_targets:
            self._target_disk_cache.pop(key, None)

    def _load_disk_cache(self) -> None:
        if not self.cache_enabled:
            return
        try:
            if not self.cache_file.exists():
                logger.info(f"Enrichment cache: none found (will use {self.cache_file} for new entries)")
                return
            with open(self.cache_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            version = data.get("version", 1)
            associations = data.get("associations") or {}
            disease_ids = data.get("disease_ids") or {}
            target_ids = data.get("target_ids") or {}

            with self._cache_lock:
                self._association_disk_cache = {}
                self._disease_disk_cache = {}
                self._target_disk_cache = {}

                if isinstance(associations, list):
                    for row in associations:
                        source = str(row.get("source", "")).strip()
                        gene = str(row.get("gene", "")).strip().upper()
                        disease_term = str(row.get("disease_term", "")).strip()
                        if not source or not gene or not disease_term:
                            continue
                        try:
                            value = row.get("value")
                            if value is None:
                                value = json.loads(row.get("value_json", "{}"))
                        except (TypeError, ValueError):
                            continue
                        self._association_disk_cache[self._cache_key(source, gene, disease_term)] = {
                            "ts": float(row.get("ts")) if row.get("ts") is not None else time.time(),
                            "value": value,
                        }
                else:
                    for key, entry in (associations or {}).items():
                        if isinstance(entry, dict) and "value" in entry:
                            value = entry.get("value")
                            ts = entry.get("ts", time.time())
                        else:
                            value = entry
                            ts = time.time()
                        source, gene, disease_term = self._cache_parse_key(key)
                        if not source:
                            continue
                        self._association_disk_cache[self._cache_key(source, gene, disease_term)] = {
                            "ts": float(ts) if ts is not None else time.time(),
                            "value": value if isinstance(value, dict) else {},
                        }

                if isinstance(disease_ids, list):
                    for row in disease_ids:
                        term = str(row.get("disease_term", "")).strip()
                        if not term:
                            continue
                        self._disease_disk_cache[term] = {
                            "ts": float(row.get("ts")) if row.get("ts") is not None else time.time(),
                            "value": row.get("disease_id"),
                        }
                else:
                    for term, entry in (disease_ids or {}).items():
                        if isinstance(entry, dict) and "value" in entry:
                            value = entry.get("value")
                            ts = entry.get("ts", time.time())
                        else:
                            value = entry
                            ts = time.time()
                        self._disease_disk_cache[str(term)] = {
                            "ts": float(ts) if ts is not None else time.time(),
                            "value": value,
                        }

                if isinstance(target_ids, list):
                    for row in target_ids:
                        gene_name = str(row.get("gene_name", "")).strip().upper()
                        if not gene_name:
                            continue
                        self._target_disk_cache[gene_name] = {
                            "ts": float(row.get("ts")) if row.get("ts") is not None else time.time(),
                            "value": row.get("target_id"),
                        }
                else:
                    for gene_name, entry in (target_ids or {}).items():
                        if isinstance(entry, dict) and "value" in entry:
                            value = entry.get("value")
                            ts = entry.get("ts", time.time())
                        else:
                            value = entry
                            ts = time.time()
                        self._target_disk_cache[str(gene_name).upper()] = {
                            "ts": float(ts) if ts is not None else time.time(),
                            "value": value,
                        }

                self._prune_disk_cache_locked()
                self._cache_dirty = False
                n = len(self._association_disk_cache)
            logger.info(f"Enrichment cache: loaded {n} gene-disease associations from {self.cache_file}")
        except Exception as exc:
            logger.warning(f"Failed to load enrichment cache from {self.cache_file}: {exc}")

    def _save_disk_cache(self) -> None:
        if not self.cache_enabled or not self._cache_dirty:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with self._cache_lock:
                associations = []
                for key, entry in self._association_disk_cache.items():
                    source, gene, disease_term = self._cache_parse_key(key)
                    associations.append({
                        "source": source,
                        "gene": gene,
                        "disease_term": disease_term,
                        "ts": entry.get("ts"),
                        "value_json": json.dumps(entry.get("value", {})),
                    })

                disease_ids = [
                    {
                        "disease_term": term,
                        "ts": entry.get("ts"),
                        "disease_id": entry.get("value"),
                    }
                    for term, entry in self._disease_disk_cache.items()
                ]
                target_ids = [
                    {
                        "gene_name": gene_name,
                        "ts": entry.get("ts"),
                        "target_id": entry.get("value"),
                    }
                    for gene_name, entry in self._target_disk_cache.items()
                ]
            payload = {
                "version": CACHE_VERSION,
                "saved_at": time.time(),
                "associations": associations,
                "disease_ids": disease_ids,
                "target_ids": target_ids,
            }
            with open(self.cache_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            self._cache_dirty = False
            logger.info(f"Enrichment cache: saved {len(associations)} associations to {self.cache_file}")
        except Exception as exc:
            logger.warning(f"Failed to save enrichment cache to {self.cache_file}: {exc}")

    def _open_targets_request(self, query: str, variables: Dict) -> Dict:
        """Execute a GraphQL request against Open Targets."""
        response = self._get_session().post(
            self.open_targets_api_url,
            json={"query": query, "variables": variables},
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _resolve_open_targets_disease_id(self, disease_term: str) -> Optional[str]:
        """Resolve disease term to Open Targets disease ID."""
        cached = self._disease_cache_get(disease_term)
        if cached is not None:
            return cached

        query = """
        query DiseaseSearch($queryString: String!) {
          search(queryString: $queryString, entityNames: ["disease"]) {
            hits {
              id
              name
              entity
            }
          }
        }
        """
        try:
            result = self._open_targets_request(query, {"queryString": disease_term})
            hits = result.get("data", {}).get("search", {}).get("hits", [])
            disease_id = None
            term_lower = (disease_term or "").strip().lower()
            # Prefer a hit whose name matches the disease term (case-insensitive)
            for hit in hits:
                if str(hit.get("entity", "")).lower() != "disease":
                    continue
                name = (hit.get("name") or "").strip().lower()
                if term_lower and name and (term_lower in name or name in term_lower):
                    disease_id = hit.get("id")
                    logger.debug(f"Open Targets: matched disease '{disease_term}' to {disease_id} ({hit.get('name')})")
                    break
            # Fallback: first disease hit
            if not disease_id:
                for hit in hits:
                    if str(hit.get("entity", "")).lower() == "disease":
                        disease_id = hit.get("id")
                        break
            if not disease_id and hits:
                logger.warning(f"Open Targets: no disease entity in search hits for '{disease_term}' (first hit: {hits[0].get('entity')})")
            self._disease_cache_set(disease_term, disease_id)
            return disease_id
        except Exception as exc:
            logger.debug(f"Open Targets disease search failed: {exc}")
            return None

    def _resolve_open_targets_target_id(self, gene_name: str) -> Optional[str]:
        """Resolve gene symbol to Open Targets target ID."""
        cached = self._target_cache_get(gene_name)
        if cached is not None:
            return cached
        query = """
        query TargetSearch($queryString: String!) {
          search(queryString: $queryString, entityNames: ["target"]) {
            hits {
              id
              name
              entity
            }
          }
        }
        """
        try:
            result = self._open_targets_request(query, {"queryString": gene_name})
            hits = result.get("data", {}).get("search", {}).get("hits", [])
            target_id = None
            for hit in hits:
                if str(hit.get("entity", "")).lower() == "target":
                    target_id = hit.get("id")
                    break
            self._target_cache_set(gene_name, target_id)
            return target_id
        except Exception:
            raise

    def _fetch_open_targets_association(self, target_id: str, disease_id: str) -> Optional[Dict]:
        """Fetch Open Targets association score for target-disease pair."""
        query = """
        query TargetDiseases($targetId: String!) {
          target(id: $targetId) {
            associatedDiseases(page: {index: 0, size: 100}) {
              rows {
                disease {
                  id
                  name
                }
                score
              }
            }
          }
        }
        """
        result = self._open_targets_request(query, {"targetId": target_id})
        rows = (
            result.get("data", {})
            .get("target", {})
            .get("associatedDiseases", {})
            .get("rows", [])
        )
        for row in rows:
            disease = row.get("disease", {}) or {}
            if disease.get("id") == disease_id:
                score = float(row.get("score", 0.0) or 0.0)
                evidence_level = (
                    "high" if score >= 0.6 else
                    "medium" if score >= 0.3 else
                    "low" if score > 0 else
                    "none"
                )
                return {
                    'associated': score > 0,
                    'association_type': 'database',
                    'evidence_level': evidence_level,
                    'description': disease.get("name"),
                    'publications': 0,
                    'functional_role': None,
                    'source': 'open_targets',
                    'score': score
                }
        return None


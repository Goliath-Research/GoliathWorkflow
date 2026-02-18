"""
Gene-disease association enrichment using Grok API and biomedical databases.

This module enriches gene mapping results with disease associations, particularly
focused on cancer types like early-stage prostate cancer.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .secure_credentials import SecureCredentialManager

logger = logging.getLogger(__name__)

# Cache format version (2 = DataFrame-backed; 1 = legacy dict)
CACHE_VERSION = 2
CACHE_COLUMNS = ["source", "gene", "disease_term", "ts", "value_json"]
DISEASE_CACHE_COLUMNS = ["disease_term", "ts", "disease_id"]

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
        cache_ttl_days: Optional[int] = 7,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
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
            cache_ttl_days: Cache TTL in days (default: 0 = never use cache for fresh Grok results; set e.g. 7 to reuse cache)
            rate_limit_delay: Delay between API calls (seconds)
            max_retries: Maximum retry attempts for API calls
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

        self.cache_enabled = cache_enabled
        # 0 = never use cache (always re-query); None = no TTL (cache never expires); positive = max age in days
        self.cache_ttl_days = None if cache_ttl_days is None else int(cache_ttl_days)
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
        
        # Setup requests session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Cache for gene-disease associations (DataFrame for fast batch lookups)
        self._cache_df: pd.DataFrame = pd.DataFrame(columns=CACHE_COLUMNS)
        self._disease_id_df: pd.DataFrame = pd.DataFrame(columns=DISEASE_CACHE_COLUMNS)
        self._cache_dirty = False
        self._load_disk_cache()
    
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
        
        # Batch cache lookup (one DataFrame query instead of N dict lookups)
        cached_results = self._cache_get_batch("grok", gene_names, disease_term)
        uncached_genes = [g for g in gene_names if g.upper() not in cached_results]
        
        if cached_results:
            logger.info(f"Using cache for {len(cached_results)} genes (querying Grok for {len(uncached_genes)} new)")
        
        if not uncached_genes:
            logger.info(f"✅ Retrieved all {len(cached_results)} genes from cache")
            return cached_results
        
        logger.info(f"Querying Grok API for {len(uncached_genes)} genes associated with '{disease_term}'...")

        results = cached_results.copy()

        # Batch genes to avoid overwhelming the API
        batch_size = 10
        total_batches = (len(uncached_genes) + batch_size - 1) // batch_size  # Ceiling division

        # Initialize progress indicator
        progress = ProgressIndicator(total_batches, "Grok API batches", update_interval=1)

        # Retry failed batches up to this many times (exponential backoff)
        max_retries = 3
        base_timeout = 60
        per_gene_timeout = 20

        for i in range(0, len(uncached_genes), batch_size):
            batch = uncached_genes[i:i+batch_size]
            batch_num = i // batch_size + 1

            # Create prompt for Grok
            prompt = self._create_grok_prompt(batch, disease_term)

            last_error = None
            for attempt in range(max_retries):
                try:
                    # Timeout: base + per-gene (increased from previous 30+10 to reduce read timeouts)
                    timeout = max(base_timeout, base_timeout + len(batch) * per_gene_timeout)
                    # On retry, allow more time
                    if attempt > 0:
                        timeout = int(timeout * (1.5 ** attempt))
                    logger.debug(f"Querying batch {batch_num} with {len(batch)} genes (timeout: {timeout}s, attempt {attempt + 1}/{max_retries})")
                    response = self._call_grok_api(prompt, timeout=timeout)

                    # Parse response
                    batch_results = self._parse_grok_response(response, batch)

                    # Cache results
                    for gene_name, association_info in batch_results.items():
                        cache_key = self._cache_key("grok", gene_name, disease_term)
                        self._cache_set(cache_key, association_info)

                    results.update(batch_results)
                    progress.update(success=True)

                    # Persist cache every 10 batches so interrupted runs keep progress
                    if batch_num % 10 == 0:
                        self._save_disk_cache()

                    break
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = (2 ** attempt) * 5  # 5s, 10s, 20s
                        logger.warning(f"Grok API query failed for batch {batch_num} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"Grok API query failed for batch {batch_num} after {max_retries} attempts: {last_error}")
                        progress.update(success=False)
                        break

            # Rate limiting between batches
            if i + batch_size < len(uncached_genes):
                time.sleep(self.rate_limit_delay)

        logger.info(f"✅ Retrieved disease associations for {len(results)} genes from Grok API ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results
    
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

Return ONLY a valid JSON array—no other text. Example:
[
  {{"gene_name": "GENE1", "associated": true, "association_type": "direct", "evidence_level": "high", "description": "...", "publications": 15, "functional_role": "..."}},
  {{"gene_name": "GENE2", "associated": false, "association_type": "none", "evidence_level": "none", "description": null, "publications": 0, "functional_role": null}}
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
        response = self.session.post(
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
                            'functional_role': None
                        })
                    else:
                        associations.append({
                            'gene_name': gene_upper,
                            'associated': False,
                            'association_type': 'none',
                            'evidence_level': 'none',
                            'description': None,
                            'publications': 0,
                            'functional_role': None
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

        # Batch cache lookup
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

        # DisGeNET API endpoint
        base_url = "https://api.disgenet.com/api/v1/gda/gene/"

        # Initialize progress indicator for individual genes
        progress = ProgressIndicator(len(uncached_genes), "DisGeNET genes", update_interval=50)

        for gene in uncached_genes:
            try:
                url = f"{base_url}{gene}"
                headers = {"Authorization": f"Bearer {disgenet_api_key}"}

                response = self.session.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json()

                    # Filter by disease term if provided
                    if disease_term:
                        disease_lower = disease_term.lower()
                        relevant_associations = [
                            d for d in data
                            if disease_lower in d.get('disease_name', '').lower() or
                               disease_lower in d.get('disease_class', '').lower()
                        ]
                    else:
                        relevant_associations = data

                    if relevant_associations:
                        # Get highest score association
                        best = max(relevant_associations, key=lambda x: x.get('score', 0))
                        association_info = {
                            'associated': True,
                            'association_type': 'database',
                            'evidence_level': 'high' if best.get('score', 0) > 0.5 else 'medium',
                            'description': best.get('disease_name'),
                            'publications': best.get('nof_pmids', 0),
                            'functional_role': best.get('disease_class'),
                            'source': 'disgenet',
                            'score': best.get('score', 0)
                        }
                    else:
                        association_info = {
                            'associated': False,
                            'association_type': 'none',
                            'evidence_level': 'none',
                            'description': None,
                            'publications': 0,
                            'functional_role': None,
                            'source': 'disgenet'
                        }

                    # Cache result
                    cache_key = self._cache_key("disgenet", gene, disease_term)
                    self._cache_set(cache_key, association_info)
                    results[gene.upper()] = association_info
                    progress.update(success=True)

                else:
                    # Handle non-200 responses as errors
                    progress.update(success=False)

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                logger.debug(f"DisGeNET query failed for {gene}: {e}")
                association_info = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'disgenet_error'
                }
                # Cache error result too (to avoid retrying failed queries)
                cache_key = self._cache_key("disgenet", gene, disease_term)
                self._cache_set(cache_key, association_info)
                results[gene.upper()] = association_info
                progress.update(success=False)
        
        logger.info(f"✅ Retrieved associations for {len(results)} genes from DisGeNET ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results

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

        # Resolve disease ID once per call
        disease_id = self._resolve_open_targets_disease_id(disease_term)
        if not disease_id:
            logger.warning(f"Open Targets: no disease match for '{disease_term}'")
            return {}

        # Batch cache lookup
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

        for gene in uncached_genes:
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

                cache_key = self._cache_key("open_targets", gene, disease_term)
                self._cache_set(cache_key, association_info)
                results[gene.upper()] = association_info
                progress.update(success=True)
            except Exception as e:
                logger.debug(f"Open Targets query failed for {gene}: {e}")
                association_info = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'open_targets_error'
                }
                cache_key = self._cache_key("open_targets", gene, disease_term)
                self._cache_set(cache_key, association_info)
                results[gene.upper()] = association_info
                progress.update(success=False)

            time.sleep(0.1)

        logger.info(f"✅ Retrieved associations for {len(results)} genes from Open Targets ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        self._save_disk_cache()
        return results
    
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
        
        # Get unique genes (exclude empty strings)
        unique_genes = [g for g in df[gene_column].dropna().unique().tolist() if str(g).strip()]
        
        if not unique_genes:
            logger.warning("No genes found in DataFrame; adding disease columns with empty values.")
            empty_results = {}
            hyperlinks = self._generate_gene_hyperlinks([])
            return self._add_enrichment_columns(df.copy(), empty_results, gene_column, 'merged', hyperlinks)

        logger.info(f"Enriching {len(unique_genes)} unique genes with disease associations...")

        # Query enabled sources
        grok_results = {}
        open_targets_results = {}
        disgenet_results = {}

        if self.use_grok:
            grok_results = self.query_grok_api(unique_genes, disease_term)

        if self.use_open_targets:
            open_targets_results = self.query_open_targets(unique_genes, disease_term)

        if self.use_disgenet:
            disgenet_results = self.query_disgenet(unique_genes, disease_term)

        # Generate hyperlinks for all genes
        hyperlinks = self._generate_gene_hyperlinks(unique_genes)

        sources_enabled = {
            'grok': self.use_grok,
            'open_targets': self.use_open_targets,
            'disgenet': self.use_disgenet
        }
        sources_enabled = {k: v for k, v in sources_enabled.items() if v}

        # If separate sources requested and multiple sources enabled, return separate DataFrames
        if separate_sources and len(sources_enabled) > 1:
            logger.info("Returning separate results for each source...")

            # Create Grok-enriched DataFrame
            result_dfs = {}
            if self.use_grok:
                grok_df = df.copy()
                grok_df = self._add_enrichment_columns(grok_df, grok_results, gene_column, 'grok', hyperlinks)
                result_dfs['grok'] = grok_df

            if self.use_open_targets:
                ot_df = df.copy()
                ot_df = self._add_enrichment_columns(ot_df, open_targets_results, gene_column, 'open_targets', hyperlinks)
                result_dfs['open_targets'] = ot_df

            # Create DisGeNET-enriched DataFrame
            if self.use_disgenet:
                disgenet_df = df.copy()
                disgenet_df = self._add_enrichment_columns(disgenet_df, disgenet_results, gene_column, 'disgenet', hyperlinks)
                result_dfs['disgenet'] = disgenet_df

            # Create merged DataFrame (current behavior)
            merged_results = self._merge_results(grok_results, open_targets_results, disgenet_results, unique_genes)
            merged_df = df.copy()
            merged_df = self._add_enrichment_columns(merged_df, merged_results, gene_column, 'merged', hyperlinks)

            result_dfs['merged'] = merged_df
            return result_dfs

        # Default behavior: merge results
        merged_results = self._merge_results(grok_results, open_targets_results, disgenet_results, unique_genes)
        enriched_df = df.copy()
        enriched_df = self._add_enrichment_columns(enriched_df, merged_results, gene_column, 'merged', hyperlinks)

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

            # Priority: Associated results first, then any available results
            if gene_upper in grok_results and self._association_meets_thresholds(grok_results[gene_upper]):
                merged_results[gene_upper] = grok_results[gene_upper]
            elif gene_upper in open_targets_results and self._association_meets_thresholds(open_targets_results[gene_upper]):
                merged_results[gene_upper] = open_targets_results[gene_upper]
            elif gene_upper in disgenet_results and self._association_meets_thresholds(disgenet_results[gene_upper]):
                merged_results[gene_upper] = disgenet_results[gene_upper]
            elif gene_upper in grok_results:
                merged_results[gene_upper] = grok_results[gene_upper]
            elif gene_upper in open_targets_results:
                merged_results[gene_upper] = open_targets_results[gene_upper]
            elif gene_upper in disgenet_results:
                merged_results[gene_upper] = disgenet_results[gene_upper]
            else:
                # No association found
                merged_results[gene_upper] = {
                    'associated': False,
                    'association_type': 'none',
                    'evidence_level': 'none',
                    'description': None,
                    'publications': 0,
                    'functional_role': None,
                    'source': 'none'
                }
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

        # Add basic gene description for unrelated genes
        df['gene_basic_description'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('description', 'Gene function not determined') if pd.notna(x) else ''
        )

        return df

    def _generate_gene_hyperlinks(self, gene_names: List[str]) -> Dict[str, Dict]:
        """Generate hyperlinks for gene databases."""
        hyperlinks = {}

        for gene in gene_names:
            gene_upper = gene.upper()
            hyperlinks[gene_upper] = {
                'ncbi': f'https://www.ncbi.nlm.nih.gov/gene/?term={gene}',
                'ensembl': f'https://www.ensembl.org/id/{gene}',
                'uniprot': f'https://www.uniprot.org/uniprotkb?query={gene}',
                'omim': f'https://www.omim.org/search?search={gene}',
                'description': f'Protein-coding gene {gene} - function and biological role'
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
        if not self.cache_enabled:
            return None
        source, gene, disease_term = self._cache_parse_key(key)
        if not source:
            return None
        df = self._cache_df
        if df.empty:
            return None
        mask = (
            (df["source"] == source)
            & (df["gene"] == gene)
            & (df["disease_term"] == disease_term)
        )
        rows = df.loc[mask]
        if rows.empty:
            return None
        row = rows.iloc[0]
        ts = row.get("ts")
        if ts is not None and hasattr(ts, "item"):
            ts = float(ts)
        if not self._is_cache_valid(ts):
            self._cache_df = df[~mask].copy()
            self._cache_dirty = True
            return None
        try:
            return json.loads(row["value_json"])
        except (TypeError, ValueError):
            return None

    def _cache_get_batch(
        self, source: str, gene_names: List[str], disease_term: str
    ) -> Dict[str, Dict]:
        """Batch lookup: one DataFrame query for all genes. Returns dict gene_upper -> value."""
        if not self.cache_enabled or not gene_names:
            return {}
        genes_upper = [g.upper() for g in gene_names]
        df = self._cache_df
        if df.empty:
            return {}
        mask = (
            (df["source"] == source)
            & (df["disease_term"] == disease_term)
            & (df["gene"].str.upper().isin(genes_upper))
        )
        rows = df.loc[mask]
        if rows.empty:
            return {}
        valid_mask = rows.apply(
            lambda r: self._is_cache_valid(float(r["ts"]) if r.get("ts") is not None else None),
            axis=1
        )
        rows = rows.loc[valid_mask]
        result = {}
        for _, row in rows.iterrows():
            gene_upper = str(row["gene"]).upper()
            if gene_upper in result:
                continue
            try:
                result[gene_upper] = json.loads(row["value_json"])
            except (TypeError, ValueError):
                pass
        return result

    def _cache_set(self, key: str, value: Dict) -> None:
        """Store a cached association."""
        if not self.cache_enabled:
            return
        source, gene, disease_term = self._cache_parse_key(key)
        if not source:
            return
        gene = gene.upper()
        ts = time.time()
        value_json = json.dumps(value)
        # Drop existing row for this key
        df = self._cache_df
        if not df.empty:
            mask = (
                (df["source"] == source)
                & (df["gene"] == gene)
                & (df["disease_term"] == disease_term)
            )
            df = df[~mask]
        new_row = pd.DataFrame([{
            "source": source,
            "gene": gene,
            "disease_term": disease_term,
            "ts": ts,
            "value_json": value_json,
        }])
        self._cache_df = pd.concat([df, new_row], ignore_index=True)
        self._cache_dirty = True

    def _disease_cache_get(self, key: str) -> Optional[str]:
        if not self.cache_enabled:
            return None
        df = self._disease_id_df
        if df.empty:
            return None
        rows = df[df["disease_term"] == key]
        if rows.empty:
            return None
        row = rows.iloc[0]
        ts = row.get("ts")
        if ts is not None and hasattr(ts, "item"):
            ts = float(ts)
        if not self._is_cache_valid(ts):
            self._disease_id_df = df[df["disease_term"] != key].copy()
            self._cache_dirty = True
            return None
        val = row.get("disease_id")
        return str(val) if val is not None and pd.notna(val) else None

    def _disease_cache_set(self, key: str, value: Optional[str]) -> None:
        if not self.cache_enabled:
            return
        df = self._disease_id_df
        if not df.empty:
            df = df[df["disease_term"] != key]
        new_row = pd.DataFrame([{
            "disease_term": key,
            "ts": time.time(),
            "disease_id": value,
        }])
        self._disease_id_df = pd.concat([df, new_row], ignore_index=True)
        self._cache_dirty = True

    def _is_cache_valid(self, ts: Optional[float]) -> bool:
        if ts is None:
            return True
        if self.cache_ttl_days == 0:
            return False  # 0 = never use cache; Grok/literature updates make cached results stale
        if self.cache_ttl_days is None:
            return True
        return (time.time() - ts) <= (self.cache_ttl_days * 86400)

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

            if version == 2 and isinstance(associations, list):
                self._cache_df = pd.DataFrame(associations)
                if self._cache_df.empty and CACHE_COLUMNS:
                    self._cache_df = pd.DataFrame(columns=CACHE_COLUMNS)
            else:
                # Legacy v1 dict: key -> {value, ts}
                rows = []
                for key, entry in (associations or {}).items():
                    if isinstance(entry, dict) and "value" in entry:
                        val, ts = entry.get("value"), entry.get("ts", time.time())
                    else:
                        val, ts = entry, time.time()
                    source, gene, disease_term = self._cache_parse_key(key)
                    if not source:
                        continue
                    rows.append({
                        "source": source,
                        "gene": gene,
                        "disease_term": disease_term,
                        "ts": ts,
                        "value_json": json.dumps(val) if isinstance(val, dict) else "{}",
                    })
                self._cache_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=CACHE_COLUMNS)

            if isinstance(disease_ids, list):
                self._disease_id_df = pd.DataFrame(disease_ids)
                if self._disease_id_df.empty and DISEASE_CACHE_COLUMNS:
                    self._disease_id_df = pd.DataFrame(columns=DISEASE_CACHE_COLUMNS)
            else:
                rows = []
                for term, entry in (disease_ids or {}).items():
                    if isinstance(entry, dict) and "value" in entry:
                        val, ts = entry.get("value"), entry.get("ts", time.time())
                    else:
                        val, ts = entry, time.time()
                    rows.append({"disease_term": term, "ts": ts, "disease_id": val})
                self._disease_id_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=DISEASE_CACHE_COLUMNS)

            # Drop expired rows
            if not self._cache_df.empty and "ts" in self._cache_df.columns:
                valid = self._cache_df.apply(
                    lambda r: self._is_cache_valid(float(r["ts"]) if r.get("ts") is not None else None),
                    axis=1
                )
                self._cache_df = self._cache_df[valid]
            if not self._disease_id_df.empty and "ts" in self._disease_id_df.columns:
                valid = self._disease_id_df.apply(
                    lambda r: self._is_cache_valid(float(r["ts"]) if r.get("ts") is not None else None),
                    axis=1
                )
                self._disease_id_df = self._disease_id_df[valid]

            self._cache_dirty = False
            n = len(self._cache_df)
            logger.info(f"Enrichment cache: loaded {n} gene-disease associations from {self.cache_file}")
        except Exception as exc:
            logger.warning(f"Failed to load enrichment cache from {self.cache_file}: {exc}")

    def _save_disk_cache(self) -> None:
        if not self.cache_enabled or not self._cache_dirty:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            associations = self._cache_df.to_dict("records") if not self._cache_df.empty else []
            disease_ids = self._disease_id_df.to_dict("records") if not self._disease_id_df.empty else []
            payload = {
                "version": CACHE_VERSION,
                "saved_at": time.time(),
                "associations": associations,
                "disease_ids": disease_ids,
            }
            with open(self.cache_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            self._cache_dirty = False
            logger.info(f"Enrichment cache: saved {len(self._cache_df)} associations to {self.cache_file}")
        except Exception as exc:
            logger.warning(f"Failed to save enrichment cache to {self.cache_file}: {exc}")

    def _open_targets_request(self, query: str, variables: Dict) -> Dict:
        """Execute a GraphQL request against Open Targets."""
        response = self.session.post(
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
            for hit in hits:
                if str(hit.get("entity", "")).lower() == "disease":
                    disease_id = hit.get("id")
                    break
            self._disease_cache_set(disease_term, disease_id)
            return disease_id
        except Exception as exc:
            logger.debug(f"Open Targets disease search failed: {exc}")
            self._disease_cache_set(disease_term, None)
            return None

    def _resolve_open_targets_target_id(self, gene_name: str) -> Optional[str]:
        """Resolve gene symbol to Open Targets target ID."""
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
        result = self._open_targets_request(query, {"queryString": gene_name})
        hits = result.get("data", {}).get("search", {}).get("hits", [])
        for hit in hits:
            if str(hit.get("entity", "")).lower() == "target":
                return hit.get("id")
        return None

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


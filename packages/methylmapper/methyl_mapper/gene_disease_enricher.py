"""
Gene-disease association enrichment using Grok API and biomedical databases.

This module enriches gene mapping results with disease associations, particularly
focused on cancer types like early-stage prostate cancer.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .secure_credentials import SecureCredentialManager

logger = logging.getLogger(__name__)


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
    - DisGeNET database (fallback)
    - NCBI Gene database (fallback)
    """
    
    def __init__(
        self,
        grok_api_key: Optional[str] = None,
        disgenet_api_key: Optional[str] = None,
        grok_api_url: str = "https://api.x.ai/v1/chat/completions",
        disease_term: str = "early-stage prostate cancer",
        use_grok: bool = True,
        use_disgenet: bool = True,
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
            disease_term: Disease term to search for (e.g., "early-stage prostate cancer")
            use_grok: Whether to use Grok API for enrichment
            use_disgenet: Whether to use DisGeNET database for enrichment
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
        self.grok_api_url = grok_api_url
        self.disease_term = disease_term
        self.use_grok = use_grok
        self.use_disgenet = use_disgenet
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        
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
        
        # Cache for gene-disease associations
        self._cache: Dict[str, Dict] = {}
    
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
        
        # Separate cached and uncached genes
        cached_results = {}
        uncached_genes = []
        
        for gene in gene_names:
            cache_key = f"{gene.upper()}:{disease_term}"
            if cache_key in self._cache:
                cached_results[gene.upper()] = self._cache[cache_key]
            else:
                uncached_genes.append(gene)
        
        if cached_results:
            logger.debug(f"Found {len(cached_results)} genes in cache")
        
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

        for i in range(0, len(uncached_genes), batch_size):
            batch = uncached_genes[i:i+batch_size]

            # Create prompt for Grok
            prompt = self._create_grok_prompt(batch, disease_term)

            try:
                # Calculate timeout based on batch size (base 30s + 10s per gene)
                timeout = max(30, 30 + len(batch) * 10)
                logger.debug(f"Querying batch {i//batch_size + 1} with {len(batch)} genes (timeout: {timeout}s)")
                response = self._call_grok_api(prompt, timeout=timeout)

                # Parse response
                batch_results = self._parse_grok_response(response, batch)

                # Cache results
                for gene_name, association_info in batch_results.items():
                    cache_key = f"{gene_name}:{disease_term}"
                    self._cache[cache_key] = association_info

                results.update(batch_results)
                progress.update(success=True)

                # Rate limiting
                if i + batch_size < len(uncached_genes):
                    time.sleep(self.rate_limit_delay)

            except Exception as e:
                logger.warning(f"Grok API query failed for batch {i//batch_size + 1}: {e}")
                progress.update(success=False)
                # Continue with other batches
                continue

        logger.info(f"✅ Retrieved disease associations for {len(results)} genes from Grok API ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
        return results
    
    def _create_grok_prompt(self, gene_names: List[str], disease_term: str) -> str:
        """Create a prompt for Grok API."""
        genes_str = ", ".join(gene_names)
        
        prompt = f"""You are a biomedical expert. For each of the following genes: {genes_str}

Please provide information about their association with "{disease_term}" in JSON format. For each gene, provide:
1. "gene_name": The gene symbol
2. "associated": true/false indicating if the gene is associated with {disease_term}
3. "association_type": One of ["direct", "indirect", "predicted", "none"]
4. "evidence_level": One of ["high", "medium", "low", "none"]
5. "description": A brief description of the association (or null if none)
6. "publications": Number of publications mentioning this association (or 0)
7. "functional_role": Brief description of the gene's role in {disease_term} (or null)

Return ONLY valid JSON array format like:
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
    
    def _parse_grok_response(self, response: Dict, gene_names: List[str]) -> Dict[str, Dict]:
        """Parse Grok API response into gene-disease associations."""
        import json
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
            
            # Try to extract JSON from the response
            # Handle cases where response might be wrapped in markdown code blocks
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                associations = json.loads(json_str)
            else:
                # Try parsing entire content as JSON
                try:
                    associations = json.loads(content)
                except json.JSONDecodeError:
                    # If not JSON, try to extract structured data from text
                    logger.warning("Could not parse JSON from Grok response, attempting text parsing...")
                    # Fallback: create associations from text description
                    associations = []
                    for gene in gene_names:
                        # Simple heuristic: check if gene appears in content
                        gene_upper = gene.upper()
                        if gene_upper in content.upper():
                            associations.append({
                                'gene_name': gene_upper,
                                'associated': True,
                                'association_type': 'predicted',
                                'evidence_level': 'low',
                                'description': f"Mentioned in context of disease",
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
            
            # Convert to dictionary keyed by gene_name
            for assoc in associations:
                gene_name = str(assoc.get('gene_name', '')).upper()
                if gene_name:
                    results[gene_name] = {
                        'associated': assoc.get('associated', False),
                        'association_type': assoc.get('association_type', 'none'),
                        'evidence_level': assoc.get('evidence_level', 'none'),
                        'description': assoc.get('description'),
                        'publications': assoc.get('publications', 0),
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
                    
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            logger.warning(f"Failed to parse Grok API response: {e}")
            logger.debug(f"Response content: {content[:500] if 'content' in locals() else 'N/A'}")
            # Return empty associations for all genes
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

        # Separate cached and uncached genes
        cached_results = {}
        uncached_genes = []

        for gene in gene_names:
            cache_key = f"{gene.upper()}:{disease_term}"
            if cache_key in self._cache:
                cached_results[gene.upper()] = self._cache[cache_key]
            else:
                uncached_genes.append(gene)

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
                    cache_key = f"{gene.upper()}:{disease_term}"
                    self._cache[cache_key] = association_info
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
                cache_key = f"{gene.upper()}:{disease_term}"
                self._cache[cache_key] = association_info
                results[gene.upper()] = association_info
                progress.update(success=False)
        
        logger.info(f"✅ Retrieved associations for {len(results)} genes from DisGeNET ({len(cached_results)} cached, {len(results) - len(cached_results)} new)")
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
        
        # Get unique genes
        unique_genes = df[gene_column].dropna().unique().tolist()
        
        if not unique_genes:
            logger.warning("No genes found in DataFrame")
            if separate_sources and self.use_grok and self.use_disgenet:
                return {'grok': df.copy(), 'disgenet': df.copy(), 'merged': df.copy()}
            return df

        logger.info(f"Enriching {len(unique_genes)} unique genes with disease associations...")

        # Query enabled sources
        grok_results = {}
        disgenet_results = {}

        if self.use_grok:
            grok_results = self.query_grok_api(unique_genes, disease_term)

        if self.use_disgenet:
            disgenet_results = self.query_disgenet(unique_genes, disease_term)

        # Generate hyperlinks for all genes
        hyperlinks = self._generate_gene_hyperlinks(unique_genes)

        # If separate sources requested and both sources enabled, return separate DataFrames
        if separate_sources and self.use_grok and self.use_disgenet:
            logger.info("Returning separate results for each source...")

            # Create Grok-enriched DataFrame
            grok_df = df.copy()
            grok_df = self._add_enrichment_columns(grok_df, grok_results, gene_column, 'grok', hyperlinks)

            # Create DisGeNET-enriched DataFrame
            disgenet_df = df.copy()
            disgenet_df = self._add_enrichment_columns(disgenet_df, disgenet_results, gene_column, 'disgenet', hyperlinks)

            # Create merged DataFrame (current behavior)
            merged_results = self._merge_results(grok_results, disgenet_results, unique_genes)
            merged_df = df.copy()
            merged_df = self._add_enrichment_columns(merged_df, merged_results, gene_column, 'merged', hyperlinks)

            return {
                'grok': grok_df,
                'disgenet': disgenet_df,
                'merged': merged_df
            }

        # Default behavior: merge results
        merged_results = self._merge_results(grok_results, disgenet_results, unique_genes)
        enriched_df = df.copy()
        enriched_df = self._add_enrichment_columns(enriched_df, merged_results, gene_column, 'merged', hyperlinks)

        # Log summary
        n_associated = enriched_df['disease_associated'].sum()
        logger.info(f"✅ Enriched DataFrame: {n_associated}/{len(enriched_df)} genes associated with '{disease_term or self.disease_term}'")

        return enriched_df

    def _merge_results(self, grok_results: Dict[str, Dict], disgenet_results: Dict[str, Dict], unique_genes: List[str]) -> Dict[str, Dict]:
        """Merge results from multiple sources with priority logic."""
        merged_results = {}
        for gene in unique_genes:
            gene_upper = gene.upper()

            # Priority: Associated results first, then any available results
            if gene_upper in grok_results and grok_results[gene_upper]['associated']:
                merged_results[gene_upper] = grok_results[gene_upper]
            elif gene_upper in disgenet_results and disgenet_results[gene_upper]['associated']:
                merged_results[gene_upper] = disgenet_results[gene_upper]
            elif gene_upper in grok_results:
                merged_results[gene_upper] = grok_results[gene_upper]
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

    def _add_enrichment_columns(self, df: pd.DataFrame, results: Dict[str, Dict], gene_column: str, source_prefix: str, hyperlinks: Dict[str, Dict]) -> pd.DataFrame:
        """Add enrichment columns to DataFrame with hyperlinks."""
        # Disease association columns
        df[f'disease_associated'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('associated', False) if pd.notna(x) else False
        )
        df[f'disease_association_type'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('association_type', 'none') if pd.notna(x) else 'none'
        )
        df[f'disease_evidence_level'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('evidence_level', 'none') if pd.notna(x) else 'none'
        )
        df[f'disease_description'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('description') if pd.notna(x) else None
        )
        df[f'disease_publications'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('publications', 0) if pd.notna(x) else 0
        )
        df[f'disease_functional_role'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('functional_role') if pd.notna(x) else None
        )
        df[f'disease_source'] = df[gene_column].str.upper().map(
            lambda x: results.get(x, {}).get('source', 'none') if pd.notna(x) else 'none'
        )

        # Add hyperlinks
        df[f'gene_ncbi_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('ncbi', '') if pd.notna(x) else ''
        )
        df[f'gene_ensembl_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('ensembl', '') if pd.notna(x) else ''
        )
        df[f'gene_uniprot_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('uniprot', '') if pd.notna(x) else ''
        )
        df[f'gene_omim_link'] = df[gene_column].str.upper().map(
            lambda x: hyperlinks.get(x, {}).get('omim', '') if pd.notna(x) else ''
        )

        # Add basic gene description for unrelated genes
        df[f'gene_basic_description'] = df[gene_column].str.upper().map(
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


"""
Pydantic config models for MethylEnricher step (step_config.enricher in project JSON).
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class NetworkRefinementConfig(BaseModel):
    """Optional PPI network refinement settings."""

    model_config = ConfigDict(extra="ignore")

    enabled: Optional[bool] = None
    source: Optional[str] = None
    local_edges_file: Optional[str] = None
    cache_path: Optional[str] = None
    score_threshold: Optional[float] = None
    community_method: Optional[str] = None
    min_component_size: Optional[int] = None
    weight_in_final_score: Optional[float] = None
    hub_ranking_mode: Optional[str] = None
    hub_disease_boost: Optional[float] = None
    hub_w_degree: Optional[float] = None
    hub_w_betweenness: Optional[float] = None
    hub_w_closeness: Optional[float] = None


class CisbpConfig(BaseModel):
    """
    Optional CIS-BP transcription-factor motif integration.

    CIS-BP (https://cisbp.ccbr.utoronto.ca) ships TF motifs/PWMs, not ready-made
    gene sets. The integration is pluggable via ``mode``:

      * ``gene_sets`` (default, "1A"): derive TF -> target-gene sets (by scanning
        gene promoter sequences with CIS-BP PWMs, or from a prebuilt GMT) and run
        offline over-representation analysis, emitting an ``enrich_<label>.csv``
        that merges with the Enrichr libraries.
      * ``annotate`` ("1B", planned): annotate TFs already surfaced by ChEA/ENCODE/
        TRRUST results with CIS-BP motif metadata.
      * ``motif_scan`` ("1C", planned): scan DMP/DMR region sequences with CIS-BP
        PWMs for direct motif enrichment.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: Optional[bool] = None
    mode: Optional[str] = "gene_sets"  # gene_sets | annotate | motif_scan
    label: Optional[str] = "CIS-BP"  # library name used in merged results

    # Data acquisition (CIS-BP has no API; bulk per-species archive download).
    species: Optional[str] = "Homo_sapiens"
    motif_evidence: Optional[List[str]] = None  # subset of ["Direct","Inferred","None"]
    auto_download: Optional[bool] = True
    data_dir: Optional[str] = None  # pre-extracted bundle (TF_Information.txt + pwms_all_motifs/)
    cache_dir: Optional[str] = None  # where downloads/built artifacts are cached
    base_url: Optional[str] = "https://cisbp.ccbr.utoronto.ca"
    build: Optional[str] = "3.10"
    archive_url: Optional[str] = None  # explicit zip URL override

    # Gene-set construction (mode="gene_sets").
    gene_set_source: Optional[str] = "promoter_scan"  # promoter_scan | prebuilt_gmt
    gmt_path: Optional[str] = None  # used when gene_set_source="prebuilt_gmt"
    genome_fasta: Optional[str] = None
    gtf: Optional[str] = None
    promoter_upstream: Optional[int] = 5000
    promoter_downstream: Optional[int] = 200
    motif_score_threshold: Optional[float] = 0.85  # relative log-odds score in [0,1]
    min_targets_per_tf: Optional[int] = 5
    max_targets_per_tf: Optional[int] = 3000
    gene_universe_file: Optional[str] = None  # gene list; default = all genes in GTF
    background_size: Optional[int] = None  # ORA background size override
    rebuild_gmt: Optional[bool] = None  # force-rebuild cached GMT


class EnricherStepConfig(BaseModel):
    """
    Pydantic model for step_config.enricher in the pipeline project JSON (and --config).
    All fields optional; used to validate and apply enricher options from config.
    """

    model_config = ConfigDict(extra="ignore")

    # I/O (often overridden by project paths)
    input: Optional[str] = None
    input_file: Optional[str] = None
    output_dir: Optional[str] = None
    outdir: Optional[str] = None
    combined_csv_name: Optional[str] = None
    disease_subdir: Optional[str] = None
    methyl_enricher_home: Optional[str] = None

    # Gene list / filters
    gene_column: Optional[str] = None
    disease_only: Optional[bool] = None
    disease_association_type: Optional[List[str]] = None
    min_disease_evidence_level: Optional[str] = None
    min_disease_publications: Optional[int] = None
    min_disease_score: Optional[float] = None
    min_dmp_count: Optional[int] = None
    min_unique_dmps: Optional[int] = None
    max_gene_q_value: Optional[float] = None
    min_mean_effect_size: Optional[float] = None
    min_gene_z: Optional[float] = None
    min_gene_importance: Optional[float] = None
    feature_types: Optional[List[str]] = None
    sort_by: Optional[str] = None
    sort_ascending: Optional[bool] = None

    # Enrichment
    libraries: Optional[List[str]] = None
    library_preset: Optional[str] = None
    top: Optional[int] = None
    cutoff: Optional[float] = None
    organism: Optional[str] = None
    ensure_complete: Optional[bool] = None
    distributed: Optional[bool] = None
    enricher_max_retries: Optional[int] = None
    enricher_retry_base_seconds: Optional[float] = None
    enricher_retry_max_seconds: Optional[float] = None
    enricher_inter_library_delay_seconds: Optional[float] = None

    # Module pipeline
    modules: Optional[bool] = None
    similarity_threshold: Optional[float] = None
    cluster_resolution: Optional[float] = None
    cluster_seed: Optional[int] = None
    module_cluster_max_q: Optional[float] = None
    module_cluster_top_terms_per_library: Optional[int] = None
    module_label_mode: Optional[str] = "dual_label"
    network_plot: Optional[str] = None
    dash_host: Optional[str] = None
    dash_port: Optional[int] = None
    dash_open_browser: Optional[bool] = None

    # Optional CIS-BP TF-motif integration (nested object + quick flat toggles)
    cisbp: Optional[CisbpConfig] = None
    cisbp_enabled: Optional[bool] = None
    cisbp_mode: Optional[str] = None

    # Optional PPI/network refinement (nested and flat key support)
    network_refinement: Optional[NetworkRefinementConfig] = None
    network_refinement_enabled: Optional[bool] = None
    network_refinement_source: Optional[str] = None
    network_refinement_local_edges_file: Optional[str] = None
    network_refinement_cache_path: Optional[str] = None
    network_refinement_score_threshold: Optional[float] = None
    network_refinement_community_method: Optional[str] = None
    network_refinement_min_component_size: Optional[int] = None
    network_refinement_weight_in_final_score: Optional[float] = None
    network_refinement_hub_ranking_mode: Optional[str] = None
    network_refinement_hub_disease_boost: Optional[float] = None
    network_refinement_hub_w_degree: Optional[float] = None
    network_refinement_hub_w_betweenness: Optional[float] = None
    network_refinement_hub_w_closeness: Optional[float] = None

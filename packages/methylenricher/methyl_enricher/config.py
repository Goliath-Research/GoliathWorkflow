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

    # Module pipeline
    modules: Optional[bool] = None
    similarity_threshold: Optional[float] = None
    cluster_resolution: Optional[float] = None
    module_cluster_max_q: Optional[float] = None
    module_cluster_top_terms_per_library: Optional[int] = None
    network_plot: Optional[str] = None

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

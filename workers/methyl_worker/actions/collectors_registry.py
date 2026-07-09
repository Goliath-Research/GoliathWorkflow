"""Collector factories registered with CLI action providers."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..action_catalog import ActionCatalogEntry
from ..collectors import (
    ArtifactCollector,
    ManifestFirstCollector,
    _resolve_dmp_output_dir,
    _resolve_enricher_output_dir,
)
from ..task_models.pipeline_models import (
    CentroidTaskOutput,
    DerivedMeasuresTaskOutput,
    DetectorTaskOutput,
    DmpSelectTaskOutput,
    EnricherTaskOutput,
    GeneFeatureSelectTaskOutput,
    GeneSelectTaskOutput,
    InfoMeasuresTaskOutput,
    MapperTaskOutput,
)


def _output_dir(inp: Mapping[str, Any]) -> Optional[str]:
    val = inp.get("outputDir")
    return str(val) if val else None


def collector_centroid(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=CentroidTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_detector(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=DetectorTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_dmp_select(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=DmpSelectTaskOutput,
        resolve_output_dir=_resolve_dmp_output_dir,
    )


def collector_mapper(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=MapperTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_derived_measures(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=DerivedMeasuresTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_info_measures(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=InfoMeasuresTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_gene_select(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=GeneSelectTaskOutput,
        resolve_output_dir=lambda inp: inp.get("runDir"),
    )


def collector_gene_feature_select(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=GeneFeatureSelectTaskOutput,
        resolve_output_dir=_output_dir,
    )


def collector_enricher(_entry: ActionCatalogEntry) -> ArtifactCollector:
    return ManifestFirstCollector(
        output_model=EnricherTaskOutput,
        resolve_output_dir=_resolve_enricher_output_dir,
    )

"""
Shared pipeline project configuration for MethylPipeline workflows.

Defines Pydantic models for a single project config (two groups, output_base, project_name)
and derived paths under {output_base}/{project_name}/centroids|detection|mapper|enricher|classifier|alignment_qc.
Used by MethylCentroid, MethylDetector, MethylMapper, MethylEnricher, MethylClassifier, MethylAlignmentQC
to avoid repeating sample paths and output layout across configs.
"""

import json
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class ControlDiseaseSide(BaseModel):
    """One side (control or disease) with a display label and one or more sub-groups."""

    label: str = Field(..., description="Display name for this side (e.g. caucasians, prostate cancer)")
    groups: List["GroupConfig"] = Field(
        default_factory=list,
        description="Sub-groups, each with label and sample_paths (and optional level_labels_path, samples_base_path)",
    )


class ComparisonSpec(BaseModel):
    """One comparison: a pair of control group vs disease group to run through detection, mapper, enricher, classifier."""

    control_group: str = Field(..., description="Label of the control sub-group (must exist in control.groups)")
    disease_group: str = Field(..., description="Label of the disease sub-group (must exist in disease.groups)")
    comparison_label: Optional[str] = Field(
        default=None,
        description="Output folder name for this comparison (default: disease_group)",
    )


class SubclusterRequest(BaseModel):
    """
    Request to run MethylCluster on this group's samples before building centroids.
    When enabled and persist_centroids is True, the group is expanded into one sub-group per
    discovered cluster (e.g. healthy_c0, healthy_c1); centroids are built per cluster via MethylCentroid.
    When persist_centroids is False, MethylCluster runs and writes assignments only; the group
    remains a single centroid (all samples) as usual.
    """

    enabled: bool = Field(default=True, description="Enable sub-clustering for this group")
    method: Literal["centroid", "hdbscan", "hierarchical"] = Field(
        default="centroid",
        description="MethylCluster clustering method (centroid recommended for methylation data)",
    )
    metric: str = Field(
        default="jensen_shannon",
        description="Distance metric for clustering (e.g. jensen_shannon, hellinger)",
    )
    min_cluster_size: Optional[int] = Field(
        default=None,
        ge=2,
        description="Minimum samples per cluster (HDBSCAN); defaults to MethylCluster default if unset",
    )
    force_k: Optional[int] = Field(
        default=None,
        ge=2,
        description="Force K clusters (centroid/hierarchical); bypasses automatic K selection",
    )
    output_subdir: Optional[str] = Field(
        default=None,
        description="Subdir under project clustering output (default: side/group_label, e.g. control/healthy)",
    )
    persist_centroids: bool = Field(
        default=True,
        description="If True, run MethylCentroid per cluster and expand group to healthy_c0, healthy_c1, ...",
    )


class GroupConfig(BaseModel):
    """
    One cohort or one level within a cohort.
    If level_labels_path is set, this group is expanded into one logical group per level
    (sample_paths are split by the level column); centroid dirs are created per level.
    When subcluster is set and persist_centroids is True, MethylCluster runs first and the group
    is expanded into one sub-group per cluster (e.g. healthy_c0, healthy_c1); no single centroid
    for the parent label is built. When samples_base_path is set (project or group), sample_paths
    may be paths to CSV/text files containing only sample folder names (one per line or one column);
    each name is resolved to samples_base_path / name.
    """

    label: str = Field(..., description="Group label; used for centroid subdir name (e.g. healthy, pcancer)")
    sample_paths: List[str] = Field(
        default_factory=list,
        description="List of sample directory paths, or paths to files containing one path per line, "
        "JSON array, or (when samples_base_path is set) one sample name per line / single column CSV.",
    )
    level_labels_path: Optional[str] = Field(
        default=None,
        description="Optional path to CSV with columns mapping sample_path or sample name to level (path, level). "
        "When set, this group is expanded into one centroid dir per level; dir name is {label}_{level}.",
    )
    samples_base_path: Optional[str] = Field(
        default=None,
        description="Base directory to resolve sample names from file (overrides project-level samples_base_path). "
        "When set, entries in sample_paths files are treated as folder names and resolved to this path.",
    )
    subcluster: Optional[SubclusterRequest] = Field(
        default=None,
        description="When set, run MethylCluster on this group's samples; if persist_centroids, expand to one centroid per cluster.",
    )

    @field_validator("label")
    @classmethod
    def label_non_empty(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("label must be non-empty")
        return v.strip()


# Resolve forward reference in ControlDiseaseSide.groups
ControlDiseaseSide.model_rebuild()


class DerivedPaths(BaseModel):
    """
    Derived paths from a ProjectConfig.
    Convention: project root = {output_base}/{project_name}; step dirs under that:
    {project_root}/centroids|detections|classifiers|predictors|mapper|enricher|alignment_qc.
    When using N groups, centroid_dirs has one entry per group; control (index 0) is
    centroids/controls/{label}, non-control groups use centroids/diseases/cancer/{label} (same as detection/mapper/enricher).
    centroid1_dir and centroid2_dir are the first two for backward compatibility.
    """

    output_base: str = Field(..., description="Project root directory (output_base/project_name)")
    centroid1_dir: str = Field(..., description="Centroid directory for group1 (or first group)")
    centroid2_dir: str = Field(..., description="Centroid directory for group2 (or second group)")
    centroid_dirs: List[str] = Field(
        default_factory=list,
        description="List of centroid directories, one per group (when N groups); same as [centroid1_dir, centroid2_dir] when N=2.",
    )
    detection_dir: str = Field(..., description="MethylDetector output directory (detections/)")
    mapper_dir: str = Field(..., description="MethylMapper output directory")
    enricher_dir: str = Field(..., description="MethylEnricher output directory")
    classifier_dir: str = Field(..., description="MethylClassifier output directory (classifiers/)")
    validator_dir: str = Field(..., description="MethylValidator/MethylPredictor output directory (predictors/)")
    alignment_qc_dir: str = Field(..., description="MethylAlignmentQC output directory (one JSON per sample)")

    @property
    def mapper_combined_csv(self) -> str:
        """Typical MethylMapper combined gene CSV path."""
        return str(Path(self.mapper_dir) / "all-gene_name-combined.csv")


class ProjectConfig(BaseModel):
    """
    Single source of truth for a MethylPipeline project (two-group or N-group).
    Defines groups, output layout, and optional shared parameters.
    Use group1/group2 for backward compatibility; when groups is set, N groups are used
    (each with optional level stratification via level_labels_path).
    Unified config: you may use "controls" and "diseases" (plural) with multiple groups
    per side; these are normalized to "control" and "disease" at load time for all pipeline components.
    """

    project_name: str = Field(
        ...,
        description="Project identifier for metadata and naming (e.g. PCa_vs_Healthy)",
    )
    output_base: str = Field(
        ...,
        description="Global output folder; each project uses a subfolder {output_base}/{project_name} for all step outputs",
    )
    group1: Optional[GroupConfig] = Field(
        default=None,
        description="First cohort (e.g. control/healthy). Required when groups is not set.",
    )
    group2: Optional[GroupConfig] = Field(
        default=None,
        description="Second cohort (e.g. disease/cancer). Required when groups is not set.",
    )
    groups: Optional[List[GroupConfig]] = Field(
        default=None,
        description="Optional N groups (overrides group1/group2 when set). Each group can have level_labels_path for stratification.",
    )
    control: Optional[ControlDiseaseSide] = Field(
        default=None,
        description="When set with disease: control side (label + groups). Centroids go to centroids/controls/{group.label}.",
    )
    disease: Optional[ControlDiseaseSide] = Field(
        default=None,
        description="When set with control: disease side (label + groups). Centroids go to centroids/diseases/{disease_subdir}/{group.label}.",
    )
    comparisons: Optional[Union[List[ComparisonSpec], str]] = Field(
        default=None,
        description="When control+disease: list of {control_group, disease_group, comparison_label?} or shorthand: "
        '"control_vs_each_disease" (first control vs each disease), "all_pairs" (all control x disease).',
    )
    samples_base_path: Optional[str] = Field(
        default=None,
        description="Base directory to resolve sample names. When set, group sample_paths that point to files "
        "can list only sample folder names (one per line or single-column CSV); each is resolved to this path.",
    )
    chromosomes: Optional[List[str]] = Field(
        default=None,
        description="Shared chromosome list (e.g. ['1','2',...,'X','Y'])",
    )
    contexts: Optional[List[str]] = Field(
        default=None,
        description="Shared contexts (e.g. ['CG'])",
    )
    path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description="Prefix replacement when sample paths moved (e.g. NAS); longest match applied",
    )
    step_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Optional per-step configuration. Keys: centroid, detection, mapper, enricher, classifier, predictor, alignment_qc. "
        "Use 'predictor' (not 'validator') for prediction/validation; validator is deprecated. "
        "Values are merged into that step's config (override file / CLI still override these).",
    )

    @field_validator("output_base")
    @classmethod
    def output_base_stripped(cls, v: str) -> str:
        return v.rstrip("/") if v else v

    @model_validator(mode="before")
    @classmethod
    def normalize_control_disease_keys(cls, data: Any) -> Any:
        """Unified config: accept 'controls'/'diseases' (plural) for multiple groups; default comparisons to control_vs_each_disease.
        When chromosomes/contexts/path_remap/step_config are nested under diseases (or controls), promote them to top level
        so ProjectConfig has them; MethylCentroid and others need project.chromosomes and project.contexts."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "controls" in data and "control" not in data:
            data["control"] = data.pop("controls")
        if "diseases" in data and "disease" not in data:
            data["disease"] = data.pop("diseases")
        if (
            data.get("control") is not None
            and data.get("disease") is not None
            and data.get("comparisons") is None
        ):
            data["comparisons"] = "control_vs_each_disease"
        # Promote project-level keys from control/disease side to top level when missing at root
        for side_key in ("control", "disease"):
            side = data.get(side_key)
            if not isinstance(side, dict):
                continue
            for key in ("comparisons", "chromosomes", "contexts", "path_remap", "step_config"):
                if key in side and (key not in data or data.get(key) is None):
                    data[key] = side[key]
            if "predictor" in side and side.get("predictor") is not None:
                sc = data.setdefault("step_config", {})
                if isinstance(sc, dict) and "predictor" not in sc:
                    sc = dict(sc)
                    sc["predictor"] = side["predictor"]
                    data["step_config"] = sc
        return data

    @model_validator(mode="before")
    @classmethod
    def normalize_predictor_step_key(cls, data: Any) -> Any:
        """Copy step_config.validator to step_config.predictor when predictor is missing (backward compatibility)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        sc = data.get("step_config")
        if not isinstance(sc, dict):
            return data
        sc = dict(sc)
        if "predictor" not in sc and "validator" in sc:
            sc["predictor"] = sc["validator"]
        data["step_config"] = sc
        return data

    @model_validator(mode="after")
    def require_group_def(self):
        """Require either (group1+group2), or groups, or (control+disease+comparisons)."""
        has_flat = self.groups is not None or (self.group1 is not None and self.group2 is not None)
        has_control_disease = self.control is not None and self.disease is not None
        if has_control_disease:
            if not self.control.groups:
                raise ValueError("control.groups must be non-empty when control is set")
            if not self.disease.groups:
                raise ValueError("disease.groups must be non-empty when disease is set")
            if self.comparisons is None:
                raise ValueError("comparisons is required when control and disease are set")
        if not has_flat and not has_control_disease:
            raise ValueError("Set either group1+group2, or groups, or control+disease+comparisons")
        if has_flat and has_control_disease:
            raise ValueError("Do not set both flat groups (or group1/group2) and control/disease")
        return self

    def _base_for(self, g: Any) -> Optional[str]:
        return getattr(g, "samples_base_path", None) or getattr(self, "samples_base_path", None)

    def _expand_side_groups(
        self, side_groups: List[GroupConfig], base_for_fn: Any, resolve_paths: bool = True
    ) -> List[Tuple[str, List[str]]]:
        """Expand a list of GroupConfig (with optional level_labels_path) to (label, paths) list.
        When resolve_paths=False, returns [(g.label, []) for each g] (no file I/O; for label validation).
        """
        if not resolve_paths:
            return [(g.label, []) for g in side_groups]
        out: List[Tuple[str, List[str]]] = []
        for g in side_groups:
            paths = _resolve_sample_paths(g.sample_paths, base_path=base_for_fn(g))
            if g.level_labels_path:
                path_to_level = _load_level_labels(g.level_labels_path)
                by_level: Dict[str, List[str]] = {}
                for p in paths:
                    level = (
                        path_to_level.get(p)
                        or path_to_level.get(str(Path(p).resolve()))
                        or path_to_level.get(Path(p).name)
                    )
                    if level is None:
                        level = "default"
                    by_level.setdefault(level, []).append(p)
                for level, level_paths in sorted(by_level.items()):
                    out.append((f"{g.label}_{level}", level_paths))
            else:
                out.append((g.label, paths))
        return out

    def _expand_one_with_manifest(
        self,
        label: str,
        paths: List[str],
        side: Literal["control", "disease"],
    ) -> List[Tuple[str, List[str], Literal["control", "disease"]]]:
        """
        If this group has subcluster+persist_centroids and a clustering manifest exists,
        return [(derived_label, derived_paths, side), ...]; otherwise return [(label, paths, side)].
        """
        subcluster_groups = {(s, l) for s, l, g in self.get_groups_with_subcluster() if g.subcluster.persist_centroids}
        if (side, label) not in subcluster_groups:
            return [(label, paths, side)]
        manifest_path = Path(self.get_clustering_output_dir(side, label)) / "manifest.json"
        if not manifest_path.exists():
            return [(label, paths, side)]
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError):
            return [(label, paths, side)]
        derived = manifest.get("derived_labels", [])
        groups_map = manifest.get("groups", {})
        if not derived or not groups_map:
            return [(label, paths, side)]
        return [(dl, groups_map.get(dl, []), side) for dl in derived]

    def _get_resolved_groups_with_side(
        self,
        expand_subclusters: bool = False,
    ) -> List[Tuple[str, List[str], Literal["control", "disease"]]]:
        """
        Return list of (label, sample_paths, side) for each centroid group.
        When control/disease: control groups first (side=control), then disease (side=disease).
        When flat groups: first group = control, rest = disease.
        If expand_subclusters is True and a clustering manifest exists for a group with
        subcluster+persist_centroids, that group is expanded into (derived_label, paths, side) per cluster.
        """
        base_for = self._base_for
        if self.control is not None and self.disease is not None:
            out: List[Tuple[str, List[str], Literal["control", "disease"]]] = []
            for label, paths in self._expand_side_groups(self.control.groups, base_for):
                if expand_subclusters:
                    out.extend(self._expand_one_with_manifest(label, paths, "control"))
                else:
                    out.append((label, paths, "control"))
            for label, paths in self._expand_side_groups(self.disease.groups, base_for):
                if expand_subclusters:
                    out.extend(self._expand_one_with_manifest(label, paths, "disease"))
                else:
                    out.append((label, paths, "disease"))
            return out
        # Flat groups or group1/group2: no subcluster expansion
        resolved = self._get_resolved_groups()
        return [
            (label, paths, "control" if i == 0 else "disease")
            for i, (label, paths) in enumerate(resolved)
        ]

    def _get_resolved_groups(self, expand_subclusters: bool = False) -> List[Tuple[str, List[str]]]:
        """
        Return list of (label, sample_paths) for each centroid group.
        When control/disease: control groups first, then disease. When groups set, expands by level_labels_path.
        If expand_subclusters is True, groups with subcluster+persist_centroids are expanded from clustering manifests.
        """
        if expand_subclusters and self.control is not None and self.disease is not None:
            with_side = self._get_resolved_groups_with_side(expand_subclusters=True)
            return [(label, paths) for label, paths, _ in with_side]
        base_for = self._base_for
        if self.control is not None and self.disease is not None:
            out: List[Tuple[str, List[str]]] = []
            out.extend(self._expand_side_groups(self.control.groups, base_for))
            out.extend(self._expand_side_groups(self.disease.groups, base_for))
            return out
        if self.groups:
            return self._expand_side_groups(self.groups, base_for)
        if self.group1 is None or self.group2 is None:
            raise ValueError("group1 and group2 are required when groups is not set")
        return [
            (self.group1.label, _resolve_sample_paths(self.group1.sample_paths, base_path=base_for(self.group1))),
            (self.group2.label, _resolve_sample_paths(self.group2.sample_paths, base_path=base_for(self.group2))),
        ]

    CENTROID_DISEASE_SUBDIR: ClassVar[str] = "cancer"
    CENTROID_CONTROL_SUBDIR: ClassVar[str] = "controls"
    CENTROID_DISEASE_FOLDER: ClassVar[str] = "diseases"

    def _get_disease_subdir(self) -> str:
        """Middle path segment for disease step dirs: <step>/<disease_label>/<disease_group>. Uses disease.label from config when control/disease."""
        return self.disease.label if self.disease is not None else self.CENTROID_DISEASE_SUBDIR

    def get_centroid_dir(self, side: Literal["control", "disease"], group_label: str) -> str:
        """Return centroid output dir for a group. control → centroids/controls/{side_label}/{label}; disease → centroids/diseases/{disease_label}/{label}."""
        global_base = self.output_base.rstrip("/")
        project_root = f"{global_base}/{self.project_name}"
        disease_sub = self._get_disease_subdir()
        if self.control is not None and self.disease is not None:
            if side == "control":
                return f"{project_root}/centroids/{self.CENTROID_CONTROL_SUBDIR}/{self.control.label}/{group_label}"
            return f"{project_root}/centroids/{self.CENTROID_DISEASE_FOLDER}/{disease_sub}/{group_label}"
        # Flat: control = centroids/controls/{label}, disease = centroids/diseases/{disease_sub}/{label}
        if side == "control":
            return f"{project_root}/centroids/{self.CENTROID_CONTROL_SUBDIR}/{group_label}"
        return f"{project_root}/centroids/{self.CENTROID_DISEASE_FOLDER}/{disease_sub}/{group_label}"

    def get_clustering_output_dir(self, side: Literal["control", "disease"], group_label: str) -> str:
        """Output dir for MethylCluster for a group (assignments, manifest). control → clustering/controls/{side_label}/{label}; disease → clustering/diseases/{disease_label}/{label}."""
        disease_sub = self._get_disease_subdir()
        if self.control is not None and self.disease is not None and side == "control":
            return f"{self.get_project_root()}/clustering/{self.CENTROID_CONTROL_SUBDIR}/{self.control.label}/{group_label}"
        if side == "control":
            return f"{self.get_project_root()}/clustering/{self.CENTROID_CONTROL_SUBDIR}/{group_label}"
        return f"{self.get_project_root()}/clustering/{self.CENTROID_DISEASE_FOLDER}/{disease_sub}/{group_label}"

    def get_groups_with_subcluster(self) -> List[Tuple[Literal["control", "disease"], str, "GroupConfig"]]:
        """Return (side, label, group_config) for each group that has subcluster enabled. Only for control/disease projects."""
        if self.control is None or self.disease is None:
            return []
        out: List[Tuple[Literal["control", "disease"], str, GroupConfig]] = []
        for g in self.control.groups:
            if g.subcluster and g.subcluster.enabled:
                out.append(("control", g.label, g))
        for g in self.disease.groups:
            if g.subcluster and g.subcluster.enabled:
                out.append(("disease", g.label, g))
        return out

    def get_comparisons(self, expand_subclusters: bool = False) -> List[ComparisonSpec]:
        """
        Return list of ComparisonSpec. When control/disease: resolve shorthand or validate explicit list.
        When flat groups: not supported (caller should use get_resolved_groups and treat first as control).
        If expand_subclusters is True, control/disease labels include derived labels from clustering manifests.
        """
        if self.control is None or self.disease is None:
            return []
        if expand_subclusters:
            with_side = self._get_resolved_groups_with_side(expand_subclusters=True)
            control_labels_resolved = {label for label, _, s in with_side if s == "control"}
            disease_labels_resolved = {label for label, _, s in with_side if s == "disease"}
            control_resolved = [(l, []) for l, _, s in with_side if s == "control"]
            disease_resolved = [(l, []) for l, _, s in with_side if s == "disease"]
        else:
            control_resolved = self._expand_side_groups(self.control.groups, self._base_for, resolve_paths=False)
            disease_resolved = self._expand_side_groups(self.disease.groups, self._base_for, resolve_paths=False)
            control_labels_resolved = {label for label, _ in control_resolved}
            disease_labels_resolved = {label for label, _ in disease_resolved}

        raw = self.comparisons
        if isinstance(raw, str):
            if raw == "control_vs_each_disease":
                first_control = control_resolved[0][0] if control_resolved else ""
                return [
                    ComparisonSpec(control_group=first_control, disease_group=d)
                    for d, _ in disease_resolved
                ]
            if raw == "all_pairs":
                return [
                    ComparisonSpec(control_group=c, disease_group=d)
                    for c, _ in control_resolved
                    for d, _ in disease_resolved
                ]
            raise ValueError(f"comparisons shorthand must be 'control_vs_each_disease' or 'all_pairs', got: {raw!r}")
        out: List[ComparisonSpec] = []
        for spec in raw:
            if isinstance(spec, dict):
                spec = ComparisonSpec.model_validate(spec)
            if spec.control_group not in control_labels_resolved:
                raise ValueError(
                    f"comparisons: control_group {spec.control_group!r} not in control.groups (resolved: {sorted(control_labels_resolved)})"
                )
            if spec.disease_group not in disease_labels_resolved:
                raise ValueError(
                    f"comparisons: disease_group {spec.disease_group!r} not in disease.groups (resolved: {sorted(disease_labels_resolved)})"
                )
            out.append(ComparisonSpec(
                control_group=spec.control_group,
                disease_group=spec.disease_group,
                comparison_label=spec.comparison_label if spec.comparison_label is not None else spec.disease_group,
            ))
        return out

    def get_derived_paths(self, expand_subclusters: bool = False) -> DerivedPaths:
        """Compute derived paths from this project config. Project root is {output_base}/{project_name}. When expand_subclusters is True, centroid_dirs include derived groups from clustering manifests."""
        global_base = self.output_base.rstrip("/")
        project_root = f"{global_base}/{self.project_name}"
        with_side = self._get_resolved_groups_with_side(expand_subclusters=expand_subclusters)
        centroid_dirs_list = [self.get_centroid_dir(side, label) for label, _, side in with_side]
        c1 = centroid_dirs_list[0] if len(centroid_dirs_list) >= 1 else ""
        c2 = centroid_dirs_list[1] if len(centroid_dirs_list) >= 2 else c1
        return DerivedPaths(
            output_base=project_root,
            centroid1_dir=c1,
            centroid2_dir=c2,
            centroid_dirs=centroid_dirs_list,
            detection_dir=f"{project_root}/detections",
            mapper_dir=f"{project_root}/mapper",
            enricher_dir=f"{project_root}/enricher",
            classifier_dir=f"{project_root}/classifiers",
            validator_dir=f"{project_root}/predictors",
            alignment_qc_dir=f"{project_root}/alignment_qc",
        )

    def get_group1_sample_paths(self) -> List[str]:
        """Return resolved sample paths for group1 (or first group when using N groups)."""
        resolved = self._get_resolved_groups()
        return list(resolved[0][1]) if resolved else []

    def get_group2_sample_paths(self) -> List[str]:
        """Return resolved sample paths for group2 (or second group when using N groups)."""
        resolved = self._get_resolved_groups()
        return list(resolved[1][1]) if len(resolved) > 1 else []

    def get_group_sample_paths(self, index: int) -> List[str]:
        """Return resolved sample paths for the group at the given index (0-based)."""
        resolved = self._get_resolved_groups()
        if index < 0 or index >= len(resolved):
            raise IndexError(f"group index {index} out of range (have {len(resolved)} groups)")
        return list(resolved[index][1])

    def get_group_label(self, index: int) -> str:
        """Return the label for the group at the given index (0-based)."""
        resolved = self._get_resolved_groups()
        if index < 0 or index >= len(resolved):
            raise IndexError(f"group index {index} out of range (have {len(resolved)} groups)")
        return resolved[index][0]

    def get_group_sample_paths_by_label(self, label: str, expand_subclusters: bool = False) -> List[str]:
        """Return sample paths for the group with the given label (from control or disease). When expand_subclusters is True, derived labels (e.g. healthy_c0) are resolved from manifests."""
        resolved = self._get_resolved_groups(expand_subclusters=expand_subclusters)
        for l, paths in resolved:
            if l == label:
                return list(paths)
        raise ValueError(f"group label {label!r} not found in resolved groups")

    def get_resolved_groups(self, expand_subclusters: bool = False) -> List[tuple]:
        """Return list of (label, sample_paths). When expand_subclusters is True, groups with subcluster+persist_centroids are expanded from clustering manifests."""
        return self._get_resolved_groups(expand_subclusters=expand_subclusters)

    def get_step_config(self, step_name: str) -> Dict[str, Any]:
        """
        Return the config dict for a step, or empty dict if not defined.
        Step names: centroid, detection, mapper, enricher, classifier, predictor, alignment_qc.
        Use 'predictor' (canonical); 'validator' is deprecated but still accepted for backward compatibility.
        """
        if not self.step_config:
            return {}
        return dict(self.step_config.get(step_name) or {})

    def get_project_root(self) -> str:
        """Project root directory: {output_base}/{project_name}."""
        return f"{self.output_base.rstrip('/')}/{self.project_name}"

    def get_detection_output_dir(self, control_group: str, disease_group: str) -> str:
        """Output dir for detection for one comparison: detections/<control_group>/<disease_group>."""
        return f"{self.get_project_root()}/detections/{control_group}/{disease_group}"

    def get_mapper_output_dir(self, control_group: str, disease_group: str) -> str:
        """Output dir for mapper for one comparison: mapper/<control_group>/<disease_group>."""
        return f"{self.get_project_root()}/mapper/{control_group}/{disease_group}"

    def get_enricher_output_dir(self, control_group: str, disease_group: str) -> str:
        """Output dir for enricher for one comparison: enricher/<control_group>/<disease_group>."""
        return f"{self.get_project_root()}/enricher/{control_group}/{disease_group}"

    def get_classifier_output_dir(self, control_group: str, disease_group: str) -> str:
        """Output dir for classifier for one comparison: classifiers/<control_group>/<disease_group>."""
        return f"{self.get_project_root()}/classifiers/{control_group}/{disease_group}"

    def get_validator_output_dir(self, control_group: str, disease_group: str) -> str:
        """Output dir for validator/predictor for one comparison: predictors/<control_group>/<disease_group>."""
        return f"{self.get_project_root()}/predictors/{control_group}/{disease_group}"

    def uses_control_disease(self) -> bool:
        """True if this project uses control/disease + comparisons (not flat groups)."""
        return self.control is not None and self.disease is not None


def _load_level_labels(csv_path: str) -> Dict[str, str]:
    """
    Load path -> level mapping from a CSV file.
    Expects a header with a path column (path, sample_path, or first column) and a level column.
    """
    import csv
    path_col = level_col = None
    out: Dict[str, str] = {}
    p = Path(csv_path)
    if not p.is_file():
        raise FileNotFoundError(f"level_labels_path not found: {csv_path}")
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return out
        header_lower = [h.strip().lower() for h in header]
        for name in ("path", "sample_path", "sample"):
            if name in header_lower:
                path_col = header_lower.index(name)
                break
        if path_col is None:
            path_col = 0
        for name in ("level", "levels", "label", "labels", "stage", "grade"):
            if name in header_lower:
                level_col = header_lower.index(name)
                break
        if level_col is None:
            level_col = 1 if len(header) > 1 else 0
        for row in reader:
            if len(row) > max(path_col, level_col):
                path_val = row[path_col].strip()
                level_val = row[level_col].strip()
                if path_val and level_val:
                    out[path_val] = level_val
    return out


def _resolve_sample_paths(
    sample_paths: List[str],
    base_path: Optional[str] = None,
) -> List[str]:
    """
    Expand any path that points to a file (one path per line, JSON array, or single-column CSV of names)
    into a list of full paths. When base_path is set and the file contains sample names (no slashes),
    each name is resolved to base_path / name.
    """
    import csv
    import json
    out: List[str] = []
    base = Path(base_path).resolve() if base_path else None

    def resolve_entry(entry: str) -> str:
        entry = entry.strip()
        if not entry:
            return ""
        if base is not None and not _looks_like_absolute_path(entry):
            return str(base / entry)
        return entry

    for p in sample_paths:
        p = p.strip()
        if not p:
            continue
        path = Path(p)
        if path.is_file():
            content = path.read_text().strip()
            if content.startswith("["):
                data = json.loads(content)
                for x in data:
                    r = resolve_entry(str(x))
                    if r:
                        out.append(r)
            elif path.suffix.lower() == ".csv":
                with open(path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    first_row = next(reader, None)
                    if first_row is None:
                        pass
                    elif first_row and first_row[0].strip().lower() in ("sample", "path", "sample_path", "name", "id"):
                        for row in reader:
                            if len(row) > 0:
                                r = resolve_entry(row[0])
                                if r:
                                    out.append(r)
                    else:
                        if len(first_row) > 0:
                            r = resolve_entry(first_row[0])
                            if r:
                                out.append(r)
                        for row in reader:
                            if len(row) > 0:
                                r = resolve_entry(row[0])
                                if r:
                                    out.append(r)
            else:
                for line in content.splitlines():
                    if line.strip().startswith("#"):
                        continue
                    r = resolve_entry(line)
                    if r:
                        out.append(r)
        else:
            if base is not None and (_looks_like_file_path(p) or "/" in p or "\\" in p):
                raise FileNotFoundError(
                    f"Sample list file not found: {path}. "
                    "Create the file (e.g. CSV with a 'sample' column of folder names) or run from the directory where it exists."
                )
            out.append(resolve_entry(p) if base else p)
    return out


def _looks_like_file_path(entry: str) -> bool:
    """True if entry looks like a path to a list file (.csv, .txt, etc.)."""
    e = entry.strip().lower()
    return e.endswith(".csv") or e.endswith(".txt") or e.endswith(".json")


def _looks_like_absolute_path(entry: str) -> bool:
    if not entry:
        return False
    if entry.startswith("/"):
        return True
    if len(entry) >= 2 and entry[1] == ":":
        return True
    if "/" in entry or "\\" in entry:
        return True
    return False


def load_project(
    path: Union[str, Path],
    output_base_override: Optional[str] = None,
) -> ProjectConfig:
    """
    Load and validate a project config from a JSON file.
    This is the single place pipeline steps use to resolve input/output paths
    (via the returned project's get_derived_paths(), get_centroid_dir(), etc.).

    If output_base_override is set, the project's output_base is replaced before
    any path resolution, so all derived paths (centroids, detections, classifiers, etc.)
    are computed under that base. Use when running on a different machine or directory
    than the one in the project JSON.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    import json
    with open(path) as f:
        data = json.load(f)
    project = ProjectConfig.model_validate(data)
    if output_base_override is not None:
        project = project.model_copy(update={"output_base": output_base_override.rstrip("/")})
    return project

"""
Shared pipeline project configuration for MethylPipeline workflows.

Defines Pydantic models for a single project config (two groups, output_base, project_name)
and derived paths under {output_base}/{project_name}/centroids|detection|mapper|enricher|classifier|alignment_qc.
Used by MethylCentroid, MethylDetector, MethylMapper, MethylEnricher, MethylClassifier, MethylAlignmentQC
to avoid repeating sample paths and output layout across configs.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class GroupConfig(BaseModel):
    """
    One cohort or one level within a cohort.
    If level_labels_path is set, this group is expanded into one logical group per level
    (sample_paths are split by the level column); centroid dirs are created per level.
    When samples_base_path is set (project or group), sample_paths may be paths to CSV/text files
    containing only sample folder names (one per line or one column); each name is resolved to
    samples_base_path / name.
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

    @field_validator("label")
    @classmethod
    def label_non_empty(cls, v: str) -> str:
        if not (v and v.strip()):
            raise ValueError("label must be non-empty")
        return v.strip()


class DerivedPaths(BaseModel):
    """
    Derived paths from a ProjectConfig.
    Convention: project root = {output_base}/{project_name}; step dirs under that:
    {project_root}/centroids|detection|mapper|enricher|classifier|alignment_qc.
    When using N groups, centroid_dirs has one entry per group; centroid1_dir and centroid2_dir
    are the first two for backward compatibility (or only two if exactly two groups).
    """

    output_base: str = Field(..., description="Project root directory (output_base/project_name)")
    centroid1_dir: str = Field(..., description="Centroid directory for group1 (or first group)")
    centroid2_dir: str = Field(..., description="Centroid directory for group2 (or second group)")
    centroid_dirs: List[str] = Field(
        default_factory=list,
        description="List of centroid directories, one per group (when N groups); same as [centroid1_dir, centroid2_dir] when N=2.",
    )
    detection_dir: str = Field(..., description="MethylDetector output directory")
    mapper_dir: str = Field(..., description="MethylMapper output directory")
    enricher_dir: str = Field(..., description="MethylEnricher output directory")
    classifier_dir: str = Field(..., description="MethylClassifier output directory")
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
        description="Optional per-step configuration. Keys: centroid, detection, mapper, enricher, classifier, alignment_qc. "
        "Values are merged into that step's config (override file / CLI still override these).",
    )

    @field_validator("output_base")
    @classmethod
    def output_base_stripped(cls, v: str) -> str:
        return v.rstrip("/") if v else v

    @model_validator(mode="after")
    def require_group1_group2_when_no_groups(self):
        """When groups is not set, group1 and group2 are required."""
        if not self.groups and (self.group1 is None or self.group2 is None):
            raise ValueError("group1 and group2 are required when groups is not set")
        return self

    def _get_resolved_groups(self) -> List[Tuple[str, List[str]]]:
        """
        Return list of (label, sample_paths) for each centroid group.
        When groups is set, expands by level_labels_path per group; otherwise uses group1/group2.
        Uses samples_base_path (group or project) when resolving sample names from files.
        """

        def base_for(g: Any) -> Optional[str]:
            return getattr(g, "samples_base_path", None) or getattr(self, "samples_base_path", None)

        if self.groups:
            out: List[Tuple[str, List[str]]] = []
            for g in self.groups:
                paths = _resolve_sample_paths(g.sample_paths, base_path=base_for(g))
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
        if self.group1 is None or self.group2 is None:
            raise ValueError("group1 and group2 are required when groups is not set")
        return [
            (self.group1.label, _resolve_sample_paths(self.group1.sample_paths, base_path=base_for(self.group1))),
            (self.group2.label, _resolve_sample_paths(self.group2.sample_paths, base_path=base_for(self.group2))),
        ]

    def get_derived_paths(self) -> DerivedPaths:
        """Compute derived paths from this project config. Project root is {output_base}/{project_name}."""
        global_base = self.output_base.rstrip("/")
        project_root = f"{global_base}/{self.project_name}"
        resolved = self._get_resolved_groups()
        centroid_dirs_list = [f"{project_root}/centroids/{label}" for label, _ in resolved]
        c1 = centroid_dirs_list[0] if len(centroid_dirs_list) >= 1 else ""
        c2 = centroid_dirs_list[1] if len(centroid_dirs_list) >= 2 else c1
        return DerivedPaths(
            output_base=project_root,
            centroid1_dir=c1,
            centroid2_dir=c2,
            centroid_dirs=centroid_dirs_list,
            detection_dir=f"{project_root}/detection",
            mapper_dir=f"{project_root}/mapper",
            enricher_dir=f"{project_root}/enricher",
            classifier_dir=f"{project_root}/classifier",
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

    def get_resolved_groups(self) -> List[tuple]:
        """Public alias for _get_resolved_groups(); returns list of (label, sample_paths)."""
        return self._get_resolved_groups()

    def get_step_config(self, step_name: str) -> Dict[str, Any]:
        """
        Return the config dict for a step, or empty dict if not defined.
        Step names: centroid, detection, mapper, enricher, classifier, alignment_qc.
        """
        if not self.step_config:
            return {}
        return dict(self.step_config.get(step_name) or {})


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


def load_project(path: Union[str, Path]) -> ProjectConfig:
    """Load and validate a project config from a JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    import json
    with open(path) as f:
        data = json.load(f)
    return ProjectConfig.model_validate(data)

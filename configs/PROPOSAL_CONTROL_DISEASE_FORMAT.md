# Proposal: control / disease two-level group structure

## Goal

Allow the project config to declare **two top-level sides** (control and disease), each with:

- A **configurable label** (e.g. "caucasians" for control, "prostate cancer" for disease) for display and reporting.
- **One or more sub-groups**, each with its own `label` and `sample_paths` (same as current group items).

Path layout and pipeline behaviour stay the same: the first side is control (one or more centroid/detection groups), the second side is disease (one or more groups under `centroids/cancer/`, `detection/cancer/`, etc.). Sub-group labels are used for folder names.

---

## Proposed schema

Support an optional **control / disease** block. When present, it overrides the flat `groups` (and group1/group2) for resolving groups.

```json
"control": {
  "label": "caucasians",
  "groups": [
    { "label": "healthy", "sample_paths": ["configs/healthy-hardik.csv"] }
  ]
},
"disease": {
  "label": "prostate cancer",
  "groups": [
    { "label": "pca1-1", "sample_paths": ["configs/pca1-1.csv"] },
    { "label": "pca1-2", "sample_paths": ["configs/pca1-2.csv"] },
    { "label": "pca1-3", "sample_paths": ["configs/pca1-3.csv"] }
  ]
}
```

- **control** (object, optional):  
  - **label** (string): Display name for the control cohort (e.g. "caucasians").  
  - **groups** (array): List of `{ "label", "sample_paths" }` (same as current group entries). Can include **level_labels_path** and **samples_base_path** per sub-group if desired.

- **disease** (object, optional):  
  - **label** (string): Display name for the disease cohort (e.g. "prostate cancer").  
  - **groups** (array): Same structure as control.groups.

**Resolution rule (to implement in methyl_utils):**

- If `control` and `disease` are both present, then **resolved_groups** = flatten(control.groups) + flatten(disease.groups), in order. So all control sub-groups get indices 0, 1, … and all disease sub-groups follow. **Control index** = 0 (first group only) for detection/mapper/enricher semantics, or “all control groups” if we ever support multi-control. For current behaviour, treat the first resolved group as control and the rest as disease (so control should usually have one sub-group, or merge into one logical group).
- If only **groups** (or group1/group2) is set, keep current behaviour: resolved_groups = flat list, first = control.

**Path naming:** Keep using **sub-group labels** for paths (e.g. `centroids/healthy`, `centroids/cancer/pca1-1`). The top-level **control.label** and **disease.label** are for metadata, reports, and optional UI only (not for folder names), unless we later add an option to use them.

---

## Example config

See **project_PCa1_3levels_vs_Healthy_Hardik_control_disease.json**: same project as project_PCa1_3levels_vs_Healthy_Hardik.json but using the control/disease format with control label "caucasians" and disease label "prostate cancer".

---

## Implementation notes

1. **methyl_utils (ProjectConfig):**  
   - Add optional fields `control: Optional[ControlDiseaseSide]` and `disease: Optional[ControlDiseaseSide]` where `ControlDiseaseSide` has `label: str` and `groups: List[GroupConfig]`.  
   - In `_get_resolved_groups()`, if both `control` and `disease` are set, build the flat list from control.groups then disease.groups (with existing level_labels_path expansion per sub-group); otherwise keep current logic (groups or group1/group2).  
   - Store control_label and disease_label on the model for downstream use (e.g. reports).

2. **Backward compatibility:**  
   - If only `groups` or group1/group2 is present, behaviour unchanged.  
   - No change to DerivedPaths or step resolvers if resolved_groups remains (label, sample_paths) with the same order and path conventions.

3. **Validation:**  
   - Require that when `control` or `disease` is set, both are set and each has at least one group.

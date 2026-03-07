---
name: Rename MethylExtendedCentroid to MethylCentroid
overview: Rename the centroid data class from MethylExtendedCentroid to MethylCentroid across the monorepo, resolve the name clash in the methylcentroid package runner module, standardize is_centroid / sample_type "centroid", and update all documentation to use only MethylCentroid and MethylSample.
todos: []
isProject: false
---

# Rename MethylExtendedCentroid to MethylCentroid and update documentation

## Scope

- **MethylUtils**: The centroid data class (currently `MethylExtendedCentroid` in [packages/methylutils/methyl_utils/core/methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py)) becomes `MethylCentroid`. Only two data types remain: `MethylSample` and `MethylCentroid`.
- **Name clash**: The package [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py) defines a **runner** class also named `MethylCentroid`. That file must import the data class under an alias (e.g. `MethylCentroidData`) so both can be used.
- **API surface**: Replace `is_extended_centroid` with `is_centroid`, and `sample_type == "extended_centroid"` with `sample_type == "centroid"` for the centroid type. Keep backward compatibility only where it is a string literal used for filtering (e.g. `basic_centroid` / `extended_centroid` in configs) if the plan says "no backward compatibility" — otherwise accept breaking changes and use `"centroid"` only.

## 1. MethylUtils – rename class and exports

** [packages/methylutils/methyl_utils/core/methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py)**

- Rename class `MethylExtendedCentroid` to `MethylCentroid`.
- Update all return type hints and docstrings in that file from `MethylExtendedCentroid` to `MethylCentroid` (e.g. `add_sample`, `remove_sample`, `from_centroid_data`).
- Replace `is_extended_centroid` property with `is_centroid` (return `True` for this class).
- Replace `sample_type` return value from `"extended_centroid"` to `"centroid"`.

** [packages/methylutils/methyl_utils/**init**.py](packages/methylutils/methyl_utils/__init__.py)**

- Import `MethylCentroid` from `methyl_frame` (the renamed class).
- Remove exports of `MethylExtendedCentroid` and remove aliases `MethylCentroid = MethylExtendedCentroid`, `MethylBetaCentroid = MethylExtendedCentroid`.
- Export only `MethylCentroid` (and keep `MethylSample`, `MethylFrame` as needed). Update `__all_`_ and any re-exports in [packages/methylutils/**init**.py](packages/methylutils/__init__.py) to use `MethylCentroid` and drop `MethylExtendedCentroid` / `MethylBetaCentroid` if present.

** [packages/methylutils/methyl_utils/core/io.py](packages/methylutils/methyl_utils/core/io.py)**

- Replace `MethylExtendedCentroid` with `MethylCentroid` (import and type hints, and `cls = MethylCentroid` in load path).

** [packages/methylutils/methyl_utils/core/centroid_builder.py](packages/methylutils/methyl_utils/core/centroid_builder.py)**

- Import and use `MethylCentroid`; replace all references to `MethylExtendedCentroid` in signatures and docstrings.

** [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)**

- Import `MethylCentroid` from `methyl_frame`.
- Replace type hints and docstrings that reference `MethylExtendedCentroid` with `MethylCentroid`.
- Replace validation messages that say "extended centroids" with "centroids" and use `is_centroid` instead of `is_extended_centroid` where applicable.
- In `create_reference_sample` (or equivalent) and anywhere a centroid instance is constructed, use `MethylCentroid(...)`.
- Update `data_structure="extended_centroid"` to `data_structure="centroid"` if that string is part of the public API; otherwise keep a single canonical value `"centroid"` and update call sites.

** [packages/methylutils/methyl_utils/core/distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py)** (if it references the class)

- Replace any `MethylExtendedCentroid` reference with `MethylCentroid`.

** [packages/methylutils/methyl_utils/bayesian_classifier_trainer.py](packages/methylutils/methyl_utils/bayesian_classifier_trainer.py)**

- Replace checks for `sample_type != "extended_centroid"` with `sample_type != "centroid"` and update error messages.

## 2. MethylCentroid package – resolve name clash

** [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)**

- Import the data class with an alias: `from methyl_utils import MethylCentroid as MethylCentroidData` (or `CentroidData`).
- Replace every use of `MethylExtendedCentroid` (type hints, `isinstance(..., MethylExtendedCentroid)`, and constructor calls like `MethylExtendedCentroid(df, ...)`) with `MethylCentroidData`.
- Keep the runner class name as `MethylCentroid` (no change).
- Remove or update references to `as_extended_centroid` if they exist (e.g. replace with a check for `MethylCentroidData` or `is_centroid`).
- Update docstrings that mention "MethylExtendedCentroid" to "MethylCentroid (data)" or "centroid data".

## 3. MethylCluster

** [packages/methylcluster/methyl_cluster/centroid_manager.py](packages/methylcluster/methyl_cluster/centroid_manager.py)**

- Change import to `from methyl_utils.core.methyl_frame import MethylCentroid, MethylSample`.
- Replace all `MethylExtendedCentroid` type hints and `isinstance` checks with `MethylCentroid`.
- Rename `_ensure_extended_centroid` to `_ensure_centroid` and update docstrings; return type `MethylCentroid`.
- Update `self.centroid: Optional[MethylCentroid]`.

## 4. MethylDetector and MethylClassifier

- ** [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)**  
No change to `MethylCentroidPair` usage; only MethylUtils and MethylCentroid package need the class rename. If any internal type hint or string mentions "extended centroid", switch to "centroid".
- ** [packages/methylclassifier/methyl_classifier/cli/main.py](packages/methylclassifier/methyl_classifier/cli/main.py)**  
Replace string checks for `'extended_centroid'` (and optionally `'basic_centroid'`) with `'centroid'` so a single centroid type is recognized.

## 5. Tests (methylutils and others)

- ** [packages/methylutils/methyl_utils/tests/test_centroid_builder.py](packages/methylutils/methyl_utils/tests/test_centroid_builder.py)**  
Import and assert `isinstance(..., MethylCentroid)`; replace `MethylExtendedCentroid` everywhere.
- ** [packages/methylutils/methyl_utils/tests/test_methyl_frame_statistics.py](packages/methylutils/methyl_utils/tests/test_methyl_frame_statistics.py)**  
Replace `MethylExtendedCentroid` with `MethylCentroid`; replace `sample_type == "extended_centroid"` and `"extended_centroid"` string literals with `"centroid"`.
- ** [packages/methylutils/tests/test_centroid_creation.py](packages/methylutils/tests/test_centroid_creation.py)**  
Replace `is_extended_centroid` with `is_centroid` if used.
- ** [packages/methylcentroid/methyl_centroid/tests/test_extended_centroid.py](packages/methylcentroid/methyl_centroid/tests/test_extended_centroid.py)**  
Rename or refactor tests so they refer to "centroid" (e.g. test file or test names); update imports and assertions to use `MethylCentroid` (data class) from methyl_utils where needed.
- ** [packages/methylutils/tests/test_genome_processing.py](packages/methylutils/tests/test_genome_processing.py)**  
Replace `data_structure="extended_centroid"` with `data_structure="centroid"`.
- ** [packages/methylutils/methyl_utils/memory_manager.py](packages/methylutils/methyl_utils/memory_manager.py)**  
Replace parameter default or options `"extended_centroid"` with `"centroid"` where applicable.
- ** [packages/methylutils/examples/package_demos/container_optimization.py](packages/methylutils/examples/package_demos/container_optimization.py)**  
Same: use `"centroid"` instead of `"extended_centroid"`.

## 6. Documentation updates

- ** [packages/methylutils/README.md](packages/methylutils/README.md)**  
Use `MethylCentroid` in examples and text; remove "Extended" from class name.
- ** [packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md](packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md)**  
Replace MethylExtendedCentroid with MethylCentroid; document `is_centroid` and `sample_type == "centroid"`.
- ** [packages/methylutils/docs/MethylUtils_Theoretical_Foundation.md](packages/methylutils/docs/MethylUtils_Theoretical_Foundation.md)**  
Replace extended centroid naming with MethylCentroid / centroid.
- ** [packages/methylutils/docs/METHYLUTILS_IMPLEMENTATION.md](packages/methylutils/docs/METHYLUTILS_IMPLEMENTATION.md)**  
Same.
- ** [packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md](packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md)**  
Same.
- ** [packages/methylutils/docs/USAGE.md](packages/methylutils/docs/USAGE.md)**  
Same.
- ** [packages/methylcentroid/README.md](packages/methylcentroid/README.md)**  
Clarify that the package provides the MethylCentroid **runner**; centroid data is MethylUtils’ `MethylCentroid` (data class).
- ** [packages/methylcentroid/docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md](packages/methylcentroid/docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)**  
Use MethylCentroid (runner) vs MethylCentroid data (from MethylUtils) consistently; remove "extended" terminology.
- ** [packages/methylcentroid/docs/METHYLCENTROID_IMPLEMENTATION.md](packages/methylcentroid/docs/METHYLCENTROID_IMPLEMENTATION.md)**  
Same.
- ** [packages/methylcentroid/docs/MethylCentroid_Theoretical_Foundation.md](packages/methylcentroid/docs/MethylCentroid_Theoretical_Foundation.md)**  
Same.
- ** [packages/methylcentroid/docs/USAGE.md](packages/methylcentroid/docs/USAGE.md)**  
Same.
- ** [packages/methyldetector/docs/USAGE.md](packages/methyldetector/docs/USAGE.md)**  
Refer to MethylCentroid (and MethylSample) where relevant; no "extended" centroid.
- ** [packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md)**  
Same.
- ** [packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md)**  
Same.
- ** [docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md](docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md)**  
Use MethylCentroid and MethylSample only; remove MethylExtendedCentroid and "extended centroid" wording.
- ** [docs/index.md](docs/index.md)**  
No change unless it mentions extended centroid.
- ** [packages/methylutils/methyl_utils/tests/README_METHYL_FRAME_STATS.md](packages/methylutils/methyl_utils/tests/README_METHYL_FRAME_STATS.md)**  
Update test names or instructions that reference methyl_extended_centroid or extended_centroid to centroid.
- ** [packages/methylutils/tests/README_centroid_test.md](packages/methylutils/tests/README_centroid_test.md)**  
Same.
- ** [packages/methylutils/examples/usage_examples/show_sample_properties.py](packages/methylutils/examples/usage_examples/show_sample_properties.py)**  
Replace `is_extended_centroid` with `is_centroid` in print or logic.
- ** [packages/methylcentroid/methyl_centroid/examples/example_metadata_access.py](packages/methylcentroid/methyl_centroid/examples/example_metadata_access.py)**  
Replace `is_extended_centroid` with `is_centroid`.
- ** [packages/methylcentroid/methyl_centroid/examples/extended_centroid_example.py](packages/methylcentroid/methyl_centroid/examples/extended_centroid_example.py)**  
Rename or refactor to "centroid" (e.g. centroid_example.py); use MethylCentroid (data) from methyl_utils in examples and text.

## 7. MethylFrame base class (MethylSample)

** [packages/methylutils/methyl_utils/core/methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py)**

- On the **base** `MethylFrame` (if it defines `is_extended_centroid`), keep a property that returns `False` for non-centroid; subclasses override. Rename to `is_centroid`: base returns `False`, `MethylCentroid` (formerly MethylExtendedCentroid) returns `True`.
- Ensure `MethylSample` does not define `is_extended_centroid`; if it does, change to `is_centroid` returning `False`.

## 8. Backward compatibility and **all**

- Do **not** add backward-compat aliases (per "don't introduce backward compatibility"). Remove `MethylExtendedCentroid` and `MethylBetaCentroid` from public API.
- Update [packages/methylutils/**init**.py](packages/methylutils/__init__.py) re-exports so external code that did `from methyl_utils import MethylExtendedCentroid` must switch to `from methyl_utils import MethylCentroid`.

## Summary


| Item                   | Before                                    | After                                                   |
| ---------------------- | ----------------------------------------- | ------------------------------------------------------- |
| Data class name        | MethylExtendedCentroid                    | MethylCentroid                                          |
| Alias MethylCentroid   | Alias in **init**                         | Removed; class is MethylCentroid                        |
| MethylBetaCentroid     | Alias                                     | Removed                                                 |
| is_extended_centroid   | Property                                  | is_centroid                                             |
| sample_type (centroid) | "extended_centroid"                       | "centroid"                                              |
| data_structure strings | "extended_centroid"                       | "centroid"                                              |
| methyl_centroid runner | class MethylCentroid                      | Unchanged; imports MethylCentroid as MethylCentroidData |
| Docs / tests           | MethylExtendedCentroid, extended centroid | MethylCentroid, centroid                                |


## Order of implementation

1. methyl_frame.py: rename class, is_centroid, sample_type.
2. methyl_utils **init**.py and core modules (io, centroid_builder, methyl_centroid_pair, distribution_views, bayesian_classifier_trainer).
3. methylcentroid package: alias import and replace all MethylExtendedCentroid usages with MethylCentroidData.
4. methylcluster centroid_manager.
5. methylclassifier cli (string "centroid").
6. Tests (methylutils, methylcentroid, methylutils/tests, genome_processing, memory_manager, container_optimization, examples).
7. All documentation and example files listed above.


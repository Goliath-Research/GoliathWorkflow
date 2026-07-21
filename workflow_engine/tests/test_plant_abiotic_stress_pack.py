"""Plant abiotic stress methylation pack: binary manifest + plant_tissue analyte checks.

The plant pack is config on the existing methylation control plane plus a few platform
unblockers (plant_tissue analyte, plant-stress-core preset, a lifecycle program without
blood cell deconvolution). These tests assert the binary Control vs Drought manifest
resolves as expected, the plant_tissue analyte opens the non-CG QC that is fatal for
mammalian WGBS, the committed enrichment preset resolves without human disease libraries,
the trait overlay selects it, and the plant lifecycle program has no cell-deconvolution
node.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (
    _REPO / "packages" / "methylutils",
    _REPO / "packages" / "methylenricher",
    _REPO / "workflow_engine",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_CHECK_MANIFEST = (
    _REPO
    / "workflow_engine"
    / "domain"
    / "checks"
    / "plant_abiotic_stress"
    / "configs"
    / "project_Control_vs_Drought_smoke.json"
)
_EXAMPLE_DIR = _REPO / "docs" / "examples" / "samd" / "plant-abiotic-stress"
_PROGRAM = (
    _REPO / "workflow_engine" / "domain" / "fixtures" / "plant_stress_study_lifecycle.program.json"
)


def test_binary_manifest_resolves_control_vs_drought() -> None:
    from methyl_utils import load_project

    project = load_project(str(_CHECK_MANIFEST))
    assert project.get_primary_modality() == "methylation"
    assert project.get_primary_analyte() == "plant_tissue"
    assert project.contexts == ["CG", "CHG", "CHH"]
    assert project.chromosomes == ["1"]

    comparisons = project.get_comparisons()
    assert len(comparisons) == 1
    assert comparisons[0].control_group == "all"
    assert comparisons[0].disease_group == "drought"


def test_plant_tissue_analyte_opens_non_cg_qc() -> None:
    from methyl_utils.analyte_profiles import merge_step_config, normalize_primary_analyte

    assert normalize_primary_analyte("leaf") == "plant_tissue"

    align = merge_step_config("alignment_qc", {}, "plant_tissue")
    assert align["bisulfite_conversion"]["enabled"] is True
    # Non-CpG methylation is real plant biology, not a conversion failure.
    assert align["bisulfite_conversion"]["max_non_cpg_methylation_pct"] == 100.0

    frag = merge_step_config("fragmentomics", {}, "plant_tissue")
    assert frag["enabled"] is False

    extraction = merge_step_config("extraction_qc", {}, "plant_tissue")
    assert extraction["guardrails"]["max_chh_methylation_level"] == 1.0
    assert extraction["guardrails"]["max_chg_methylation_level"] == 1.0

    enr = merge_step_config("enricher", {}, "plant_tissue")
    assert enr["library_preset"] == "plant-stress-core"
    assert enr["organism"] == "Arabidopsis_thaliana"


def test_plant_stress_core_preset_resolves_without_human_disease_libs() -> None:
    from methyl_enricher.preset_registry import load_catalog

    catalog = load_catalog()
    assert "plant-stress-core" in catalog.presets
    libs = catalog.resolve("plant-stress-core")
    # Organism-general GO terms only; human pathway/disease/oncology libraries dropped.
    assert "GO_Biological_Process_2023" in libs
    assert "KEGG_2021_Human" not in libs
    assert "DisGeNET" not in libs
    assert "DSigDB" not in libs


def test_trait_overlay_disables_human_priors_and_targets_arabidopsis() -> None:
    overlay = json.loads((_EXAMPLE_DIR / "context_plant_abiotic_stress.json").read_text())
    ac = overlay["actionConfig"]
    assert ac["mapper"]["enrich_disease"] is False
    assert ac["enricher"]["library_preset"] == "plant-stress-core"
    assert ac["enricher"]["organism"] == "Arabidopsis_thaliana"
    assert ac["enricher"]["string_species"] == 3702
    assert overlay["runProgressionAnalysis"] is False


def test_example_manifest_is_plant_tissue_methylation() -> None:
    manifest = json.loads((_EXAMPLE_DIR / "project_Control_vs_Drought.json").read_text())
    reg = manifest["regulatory"]
    assert reg["primary_modality"] == "methylation"
    assert reg["primary_analyte"] == "plant_tissue"
    assert manifest["contexts"] == ["CG", "CHG", "CHH"]
    assert manifest["chromosomes"] == ["1", "2", "3", "4", "5"]


def test_plant_lifecycle_program_has_no_cell_deconvolution() -> None:
    program = json.loads(_PROGRAM.read_text())
    do_keys: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            do = node.get("do")
            if isinstance(do, str):
                do_keys.append(do)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(program["body"])
    assert "pipeline.cell_deconvolution" not in do_keys
    # Core science is still present.
    assert "pipeline.mapper" in do_keys
    assert "validation.model_mc" in do_keys

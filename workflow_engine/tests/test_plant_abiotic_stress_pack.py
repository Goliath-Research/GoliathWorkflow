"""Plant abiotic stress methylation pack: binary manifest + plant_tissue analyte checks.

The plant pack is config on the existing methylation control plane plus a few platform
unblockers (plant_tissue analyte, plant-stress-core preset, a lifecycle program without
blood cell deconvolution, multi-crop site recipes, offline plant_traits prior). These
tests assert the binary Control vs Drought manifest resolves as expected, the
plant_tissue analyte opens the non-CG QC that is fatal for mammalian WGBS, the committed
enrichment preset resolves without human disease libraries, the trait overlay selects
plant_traits (not Open Targets), crop smokes validate, and the plant lifecycle program
has no cell-deconvolution node.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
for _p in (
    _REPO / "packages" / "methylutils",
    _REPO / "packages" / "methylenricher",
    _REPO / "packages" / "methylmapper",
    _REPO / "workflow_engine",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_CHECK_DIR = (
    _REPO / "workflow_engine" / "domain" / "checks" / "plant_abiotic_stress" / "configs"
)
_CHECK_MANIFEST = _CHECK_DIR / "project_Control_vs_Drought_smoke.json"
_EXAMPLE_DIR = _REPO / "docs" / "examples" / "samd" / "plant-abiotic-stress"
_PROGRAM = (
    _REPO / "workflow_engine" / "domain" / "fixtures" / "plant_stress_study_lifecycle.program.json"
)
_PROGRAM_WITH_DECONV = (
    _REPO
    / "workflow_engine"
    / "domain"
    / "fixtures"
    / "plant_stress_study_lifecycle_with_deconv.program.json"
)
_HOUSEMAN_FIXTURE = (
    _REPO
    / "workflow_engine"
    / "domain"
    / "checks"
    / "plant_abiotic_stress"
    / "data"
    / "plant_houseman_seed_fixture.json"
)
_PROFILES = _REPO / "workflow_engine" / "domain" / "profiles"
_DEMO_TRAITS = _EXAMPLE_DIR / "data" / "arabidopsis_drought_gene_traits.tsv"

_CROP_SMOKES = (
    ("soybean", _CHECK_DIR / "project_Control_vs_Drought_soybean_smoke.json", ["1"]),
    ("maize", _CHECK_DIR / "project_Control_vs_Drought_maize_smoke.json", ["1"]),
    ("wheat", _CHECK_DIR / "project_Control_vs_Drought_wheat_smoke.json", ["1A"]),
)

_CROP_SITES = (
    "site_glycine_max_wm82.example.json",
    "site_zea_mays_b73.example.json",
    "site_triticum_aestivum_iwgsc.example.json",
)

_DOWNLOAD_SCRIPTS = (
    "download_glycine_max_wm82.sh",
    "download_zea_mays_b73.sh",
    "download_triticum_aestivum_iwgsc.sh",
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


def test_trait_overlay_uses_plant_traits_not_open_targets() -> None:
    overlay = json.loads((_EXAMPLE_DIR / "context_plant_abiotic_stress.json").read_text())
    assert overlay["pipelineProcedure"] == "plant_wgbs_gene_fc"
    ac = overlay["actionConfig"]
    mapper = ac["mapper"]
    assert mapper["enrich_disease"] is True
    assert mapper["enrich_source"] == "plant_traits"
    assert mapper["disease_term"] == "drought"
    traits_path = _REPO / mapper["plant_traits_path"]
    assert traits_path.is_file()
    assert ac["enricher"]["library_preset"] == "plant-stress-core"
    assert ac["enricher"]["organism"] == "Arabidopsis_thaliana"
    assert ac["enricher"]["string_species"] == 3702
    assert overlay["runProgressionAnalysis"] is False
    # Human therapeutic APIs must not appear in the plant overlay.
    assert "opentargets" not in json.dumps(overlay).lower()
    assert "open_targets" not in json.dumps(overlay).lower()


def test_example_manifest_is_plant_tissue_methylation() -> None:
    manifest = json.loads((_EXAMPLE_DIR / "project_Control_vs_Drought.json").read_text())
    reg = manifest["regulatory"]
    assert reg["primary_modality"] == "methylation"
    assert reg["primary_analyte"] == "plant_tissue"
    assert manifest["contexts"] == ["CG", "CHG", "CHH"]
    assert manifest["chromosomes"] == ["1", "2", "3", "4", "5"]


def _program_do_keys(program: dict) -> list[str]:
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
    return do_keys


def test_plant_lifecycle_program_has_no_cell_deconvolution() -> None:
    program = json.loads(_PROGRAM.read_text())
    do_keys = _program_do_keys(program)
    assert "pipeline.cell_deconvolution" not in do_keys
    assert "pipeline.mapper" in do_keys
    assert "validation.model_mc" in do_keys


def test_plant_lifecycle_with_deconv_includes_node_and_fixture() -> None:
    program = json.loads(_PROGRAM_WITH_DECONV.read_text())
    do_keys = _program_do_keys(program)
    assert "pipeline.cell_deconvolution" in do_keys
    assert _HOUSEMAN_FIXTURE.is_file()
    fixture = json.loads(_HOUSEMAN_FIXTURE.read_text())
    assert "mesophyll" in fixture["cell_types"]
    contexts = {m["context"] for m in fixture["markers"]}
    assert contexts == {"CG", "CHG", "CHH"}


@pytest.mark.parametrize("crop,path,chroms", _CROP_SMOKES)
def test_crop_smoke_manifest_resolves(crop: str, path: Path, chroms: list[str]) -> None:
    from admin.study_validate import validate_manifest
    from methyl_utils import load_project

    assert path.is_file(), f"missing {crop} smoke manifest"
    project = load_project(str(path))
    assert project.get_primary_analyte() == "plant_tissue"
    assert project.chromosomes == chroms
    assert project.contexts == ["CG", "CHG", "CHH"]
    raw = json.loads(path.read_text())
    assert validate_manifest(raw, pipeline_profile="samd_research") == []


@pytest.mark.parametrize(
    "name",
    [
        "project_Control_vs_Drought_soybean.json",
        "project_Control_vs_Drought_maize.json",
        "project_Control_vs_Drought_wheat.json",
    ],
)
def test_example_crop_manifests_validate_samd_research(name: str) -> None:
    from admin.study_validate import validate_manifest
    from methyl_utils import load_project

    path = _EXAMPLE_DIR / name
    project = load_project(str(path))
    assert project.get_primary_analyte() == "plant_tissue"
    raw = json.loads(path.read_text())
    assert validate_manifest(raw, pipeline_profile="samd_research") == []


@pytest.mark.parametrize("site_name", _CROP_SITES)
def test_crop_site_json_parses(site_name: str) -> None:
    path = _PROFILES / site_name
    data = json.loads(path.read_text())
    assert "reference_genome" in data and "fasta" in data["reference_genome"]
    assert "annotation" in data and "gtf" in data["annotation"]
    assert "pangenome" not in data
    assert "string_edges" in (data.get("caches") or {})


@pytest.mark.parametrize("script", _DOWNLOAD_SCRIPTS)
def test_crop_download_scripts_bash_n(script: str) -> None:
    path = _REPO / "scripts" / script
    assert path.is_file()
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_crop_overlays_set_string_species() -> None:
    expected = {
        "context_soybean_drought.json": 3847,
        "context_maize_drought.json": 4577,
        "context_wheat_drought.json": 4565,
    }
    for name, taxon in expected.items():
        overlay = json.loads((_EXAMPLE_DIR / name).read_text())
        assert overlay["actionConfig"]["enricher"]["string_species"] == taxon
        assert overlay["actionConfig"]["mapper"].get("enrich_source") != "opentargets"


def test_plant_traits_demo_tsv_joins_without_open_targets() -> None:
    import pandas as pd
    from methyl_mapper.bedtools_mapper import BedtoolsMapper
    from methyl_mapper.plant_trait_enricher import PlantTraitEnricher

    assert _DEMO_TRAITS.is_file()
    use_grok, use_ot, use_dg = BedtoolsMapper._parse_enrich_source("plant_traits")
    assert (use_grok, use_ot, use_dg) == (False, False, False)

    enricher = PlantTraitEnricher(_DEMO_TRAITS, disease_term="drought")
    out = enricher.enrich_gene_dataframe(
        pd.DataFrame({"gene_name": ["AT5G52310", "AT0G00000"]}),
        gene_column="gene_name",
    )
    assert bool(out.loc[0, "disease_associated"])
    assert out.loc[0, "disease_source"] == "plant_traits"
    assert not bool(out.loc[1, "disease_associated"])

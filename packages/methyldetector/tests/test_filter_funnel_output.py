"""Filter funnel sweep writes per-chromosome CSV (no overwrite across chromosomes)."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from methyl_detector.core.methyldetector import MethylDetector
from methyl_detector.models.config import MethylDetectorConfig


def test_filter_funnel_sweep_writes_chromosome_specific_csv():
    with TemporaryDirectory() as td:
        temp = Path(td)
        c1 = temp / "c1"
        c2 = temp / "c2"
        out = temp / "out"
        c1.mkdir()
        c2.mkdir()
        cfg = MethylDetectorConfig.model_validate(
            {
                "chromosome": "7",
                "contexts": ["CG"],
                "centroid1_dir": str(c1),
                "centroid2_dir": str(c2),
                "output_dir": str(out),
                "filter_funnel_explore": {
                    "effect_size_coverage": {"min": 0.8, "max": 0.9, "step": 0.1},
                },
            }
        )
        detector = MethylDetector(cfg)
        dmps_df = pd.DataFrame(
            {"effect_size": [1.0, 0.5, 0.2], "context": ["CG", "CG", "CG"]}
        )
        detector._run_filter_funnel_sweep(dmps_df)

        chrom_path = out / "filter_funnel-7.csv"
        legacy_path = out / "filter_funnel.csv"
        assert chrom_path.is_file()
        assert not legacy_path.is_file()
        written = pd.read_csv(chrom_path)
        assert list(written.columns) == [
            "n_statistical_dmps",
            "effect_size_coverage",
            "n_biological_dmps",
        ]
        assert len(written) == 2

"""
Basic tests for MethylClassifier
"""

import pytest
import numpy as np
from pathlib import Path
from methyl_classifier.classifier import MethylClassifier
from methyl_classifier.data_loader import DataLoader


def test_classifier_initialization():
    """Test that MethylClassifier can be initialized."""
    classifier = MethylClassifier()
    assert classifier.classifier is None
    assert classifier.chromosome is None
    assert classifier.context is None
    assert classifier.n_classes is None
    assert classifier.class_names is None


def test_extract_chrom_context():
    """Test chromosome/context extraction from classifier path."""
    from methyl_classifier.classifier import extract_chrom_context_from_classifier

    # Test fallback format - directory names ending with -CG/-CHG/-CHH
    test_path = Path("/path/to/pb-ch-2-CG/methyl_detector_classifier.pkl")
    chrom, context = extract_chrom_context_from_classifier(test_path)
    assert chrom == "2"
    assert context == "CG"

    # Test another fallback case
    test_path2 = Path("/path/to/data/detection/single/pb-ch-1-CHG/methyl_detector_classifier.pkl")
    chrom2, context2 = extract_chrom_context_from_classifier(test_path2)
    assert chrom2 == "1"
    assert context2 == "CHG"

    # Test invalid path
    invalid_path = Path("/path/to/invalid.pkl")
    with pytest.raises(ValueError):
        extract_chrom_context_from_classifier(invalid_path)


def test_data_loader_filtering():
    """Test H5 file filtering by chromosome and context."""
    from methyl_classifier.data_loader import DataLoader

    # Mock H5 files - the filtering expects exact filename match: {chrom}-{context}.h5
    mock_files = [
        Path("data/sample1-1-CG.h5"),  # File in subdirectory
        Path("1-CG.h5"),               # Exact match
        Path("2-CG.h5"),               # Different chromosome
        Path("1-CHG.h5"),              # Different context
        Path("11-CG.h5"),              # Should not match chrom="1"
    ]

    # Test filtering
    filtered = DataLoader._filter_h5_files_by_chrom_context(mock_files, "1", "CG")
    assert len(filtered) == 1
    assert filtered[0].name == "1-CG.h5"


def test_cli_import():
    """Test that CLI module can be imported."""
    try:
        from methyl_classifier import cli
        assert cli.main is not None
    except ImportError as e:
        pytest.fail(f"CLI import failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__])

#!/usr/bin/env python3
"""
Test script to verify GPU detection and fallback logic in MethylCentroid
"""

import sys
from pathlib import Path

# Add MethylUtils to Python path
methyl_utils_path = Path(__file__).parent.parent / "MethylUtils"
if str(methyl_utils_path) not in sys.path:
    sys.path.insert(0, str(methyl_utils_path))

# Add genomic_position_aligner to Python path
gpa_path = Path(__file__).parent.parent / "MethylUtils" / "gpa_pkg"
if str(gpa_path) not in sys.path:
    sys.path.insert(0, str(gpa_path))

try:
    from methyl_utils import is_gpu_available
    from methylcentroid.methyl_centroid import MethylCentroid

    print("Testing GPU detection and MethylCentroid initialization...")

    # Test GPU detection
    gpu_available = is_gpu_available()
    print(f"GPU available: {gpu_available}")

    # Test MethylCentroid initialization with minimal config
    mc = MethylCentroid(
        chrom="test",
        ctx="CG",
        output_dir=Path("/tmp/test_centroid"),
        verbose=True
    )

    print(f"MethylCentroid GPU available: {mc._gpu_available}")
    print(f"MethylCentroid using GPU: {mc._using_gpu}")
    print(f"MethylCentroid processing mode: {'GPU' if mc._using_gpu else 'CPU'}")

    print("✓ GPU detection and initialization test passed!")

except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()

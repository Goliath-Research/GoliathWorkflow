#!/usr/bin/env python3
"""
Test script to verify progress indicators work correctly
"""

import sys
import time
sys.path.insert(0, '/home/ubuntu/MethylPipeline/packages/methylmapper')

from methyl_mapper.gene_disease_enricher import ProgressIndicator

def test_progress_indicator():
    """Test the progress indicator functionality"""
    print("Testing ProgressIndicator...")

    # Test basic progress
    print("\n1. Testing basic progress with 10 items:")
    progress = ProgressIndicator(10, "Test items", update_interval=2)

    for i in range(10):
        time.sleep(0.1)  # Simulate work
        success = i != 4  # Simulate one failure
        progress.update(success)

    # Test with different update intervals
    print("\n2. Testing with update interval 1:")
    progress2 = ProgressIndicator(5, "Quick test", update_interval=1)

    for i in range(5):
        time.sleep(0.05)
        progress2.update(True)

    print("\n✅ Progress indicator tests completed!")

if __name__ == "__main__":
    test_progress_indicator()

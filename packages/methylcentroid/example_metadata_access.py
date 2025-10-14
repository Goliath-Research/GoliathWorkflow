#!/usr/bin/env python3
"""
Example: Accessing metadata from a centroid H5 file.

This demonstrates how to load a centroid and access its metadata properties.
"""

from pathlib import Path
from methyl_utils import MethylSample

def example_metadata_access(centroid_path: Path):
    """
    Load a centroid and display its metadata.
    
    Args:
        centroid_path: Path to a centroid H5 file
    """
    print(f"Loading centroid from: {centroid_path}")
    print("=" * 60)
    
    # Load the centroid
    centroid = MethylSample.load_from_h5(centroid_path)
    
    # Check if it's a centroid
    print(f"\nSample type: {centroid.sample_type}")
    print(f"Is centroid: {centroid.is_centroid}")
    print(f"Is extended centroid: {centroid.is_extended_centroid}")
    
    # Access metadata properties
    print("\nMetadata:")
    print(f"  Laboratory: {centroid.laboratory}")
    print(f"  Disease: {centroid.disease}")
    print(f"  Group: {centroid.group}")
    print(f"  Batch: {centroid.batch}")
    print(f"  Chromosome: {centroid.chromosome}")
    print(f"  Context: {centroid.context}")
    
    # Access full metadata dictionary
    if centroid.metadata:
        print(f"\nAll metadata keys: {list(centroid.metadata.keys())}")
        
        # Show sample count if available
        if "samples" in centroid.metadata:
            samples = centroid.metadata["samples"]
            print(f"Number of samples: {len(samples)}")
            if samples:
                print(f"First sample: {samples[0]}")
                if len(samples) > 1:
                    print(f"Last sample: {samples[-1]}")
        
        # Show processing parameters
        if "min_coverage" in centroid.metadata:
            print(f"\nProcessing parameters:")
            print(f"  Min coverage: {centroid.metadata.get('min_coverage')}")
            print(f"  Alpha: {centroid.metadata.get('alpha')}")
            print(f"  Distance metrics: {centroid.metadata.get('distance_metrics')}")
    else:
        print("\nNo metadata available (this centroid was created before metadata support)")
    
    # Show data statistics
    print(f"\nData statistics:")
    print(f"  Positions: {len(centroid.pos):,}")
    print(f"  Mean coverage: {centroid.get_coverage().mean():.2f}")
    if centroid.is_centroid:
        print(f"  Mean sample count: {centroid.N.mean():.2f}")
    
    print("=" * 60)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python example_metadata_access.py <centroid.h5>")
        print("\nExample:")
        print("  python example_metadata_access.py /path/to/centroids/1-CG.h5")
        sys.exit(1)
    
    centroid_path = Path(sys.argv[1])
    
    if not centroid_path.exists():
        print(f"Error: File not found: {centroid_path}")
        sys.exit(1)
    
    example_metadata_access(centroid_path)


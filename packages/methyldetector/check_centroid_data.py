#!/usr/bin/env python3
"""
Quick script to inspect centroid data and find invalid methylation values.
"""

import sys
from pathlib import Path
import numpy as np

# Add MethylUtils to path
sys.path.insert(0, '/home/ubuntu/MethylUtils')

from methyl_utils import MethylSample

def check_centroid(centroid_path: str):
    """Check centroid for invalid methylation values."""
    print(f"\n{'='*70}")
    print(f"Checking: {centroid_path}")
    print(f"{'='*70}")
    
    try:
        # Load centroid
        centroid = MethylSample.load_from_h5(centroid_path)
        
        # Check mean values
        mean_min = centroid.mean.min()
        mean_max = centroid.mean.max()
        mean_invalid = np.sum((centroid.mean < 0) | (centroid.mean > 1))
        
        print(f"\n📊 Mean Statistics:")
        print(f"  Min: {mean_min:.6f}")
        print(f"  Max: {mean_max:.6f}")
        print(f"  Invalid values (< 0 or > 1): {mean_invalid:,} / {len(centroid.mean):,}")
        
        if mean_invalid > 0:
            print(f"\n⚠️  Found {mean_invalid:,} invalid mean values!")
            # Show some examples
            invalid_mask = (centroid.mean < 0) | (centroid.mean > 1)
            invalid_positions = centroid.pos[invalid_mask][:10]
            invalid_means = centroid.mean[invalid_mask][:10]
            print(f"\n  First 10 invalid entries:")
            for pos, val in zip(invalid_positions, invalid_means):
                print(f"    Position {pos}: mean = {val:.6f}")
        else:
            print(f"  ✅ All mean values are valid (0-1)")
        
        # Check N (coverage)
        if centroid.N is not None:
            n_min = centroid.N.min()
            n_max = centroid.N.max()
            print(f"\n📊 Coverage Statistics:")
            print(f"  Min: {n_min}")
            print(f"  Max: {n_max}")
        
        # Check variance
        if hasattr(centroid, 'variance') and centroid.variance is not None:
            var_min = centroid.variance.min()
            var_max = centroid.variance.max()
            print(f"\n📊 Variance Statistics:")
            print(f"  Min: {var_min:.6f}")
            print(f"  Max: {var_max:.6f}")
        
        print(f"\n✅ Centroid loaded successfully")
        print(f"  Total positions: {len(centroid.pos):,}")
        
        return mean_invalid == 0
        
    except Exception as e:
        print(f"❌ Error loading centroid: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    # Check both centroids for chromosome 1, CG context
    centroid1 = "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/centroids/pb-healthy/1-CG.h5"
    centroid2 = "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/centroids/pb-cancer/1-CG.h5"
    
    print("Checking Centroids for Chromosome 1, CG Context")
    
    valid1 = check_centroid(centroid1)
    valid2 = check_centroid(centroid2)
    
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Centroid 1 (pb-healthy): {'✅ VALID' if valid1 else '❌ INVALID'}")
    print(f"Centroid 2 (pb-cancer): {'✅ VALID' if valid2 else '❌ INVALID'}")
    print(f"{'='*70}")
    
    sys.exit(0 if (valid1 and valid2) else 1)


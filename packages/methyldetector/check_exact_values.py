#!/usr/bin/env python3
"""
Check exact values that would fail validation.
"""

import sys
import numpy as np
sys.path.insert(0, '/home/ubuntu/MethylUtils')

from methyl_utils import MethylSample

centroid_path = "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/centroids/pb-cancer/1-CG.h5"
centroid = MethylSample.load_from_h5(centroid_path)

# Use same check as validation (with tolerance)
TOLERANCE = 1e-6
invalid_mask = (centroid.mean < -TOLERANCE) | (centroid.mean > 1.0 + TOLERANCE)
n_invalid = np.sum(invalid_mask)

print(f"Positions that would fail validation (< {-TOLERANCE} or > {1.0 + TOLERANCE}): {n_invalid}")

if n_invalid > 0:
    invalid_positions = centroid.pos[invalid_mask][:20]
    invalid_means = centroid.mean[invalid_mask][:20]
    print(f"\nFirst 20 problematic values:")
    for pos, val in zip(invalid_positions, invalid_means):
        print(f"  Position {pos}: mean = {val:.15f} (repr: {repr(val)})")
else:
    print("✅ All values pass validation!")
    
# Also check for NaN or Inf
nan_count = np.sum(np.isnan(centroid.mean))
inf_count = np.sum(np.isinf(centroid.mean))
print(f"\nNaN values: {nan_count}")
print(f"Inf values: {inf_count}")


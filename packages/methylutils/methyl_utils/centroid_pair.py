from typing import Union, Tuple
import numpy as np
from pathlib import Path
# Assume existing imports for MethylSample, ComparisonConfig, etc.
import logging

logger = logging.getLogger(__name__)

class MethylCentroidPair:
    # Existing class definition and methods...
    
    @classmethod
    def load_and_align(cls, path1: Union[str, Path], path2: Union[str, Path], config: ComparisonConfig) -> Tuple['MethylSample', 'MethylSample', np.ndarray]:
        """
        Load two centroids from paths, align on common positions, and return aligned MethylSamples.
        
        Handles validation, zero-coverage clamping, and efficient indexing using native numpy.
        
        Args:
            path1, path2: Paths to HDF5 centroid files.
            config: ComparisonConfig for min_coverage validation.
        
        Returns:
            (centroid1: MethylSample, centroid2: MethylSample, common_pos: np.ndarray)
        """
        # Load via MethylSample (native HDF5 parsing)
        centroid1 = MethylSample.load_from_h5(path1)
        centroid2 = MethylSample.load_from_h5(path2)

        # Validate extended centroids (assume is_extended_centroid checks N, Sx, etc.)
        if not centroid1.is_extended_centroid or not centroid2.is_extended_centroid:
            raise ValueError("Both inputs must be extended centroids with N, Sx, Sx2, log sums.")

        # Assume positions are sorted (typical for genomic data); if not, sort them
        if not np.all(np.diff(centroid1.pos) > 0):
            logger.warning("Centroid1 positions not sorted; sorting for alignment.")
            sort_idx1 = np.argsort(centroid1.pos)
            centroid1 = cls._sort_sample(centroid1, sort_idx1)
        if not np.all(np.diff(centroid2.pos) > 0):
            logger.warning("Centroid2 positions not sorted; sorting for alignment.")
            sort_idx2 = np.argsort(centroid2.pos)
            centroid2 = cls._sort_sample(centroid2, sort_idx2)

        # Find common positions efficiently (numpy intersection)
        common_pos = np.intersect1d(centroid1.pos, centroid2.pos, assume_unique=True)

        if len(common_pos) == 0:
            raise ValueError("No common positions between centroids.")

        # Fast index lookup with np.searchsorted (O(log n) per query, O(n log n) total)
        idx1 = np.searchsorted(centroid1.pos, common_pos, side='left')
        idx2 = np.searchsorted(centroid2.pos, common_pos, side='left')

        # Verify exact matches (positions must be unique and sorted)
        if not np.all(centroid1.pos[idx1] == common_pos) or not np.all(centroid2.pos[idx2] == common_pos):
            raise ValueError("Position mismatch during alignment; duplicates or unsorted positions?")

        # Slice using internal mask if available, else create masked/sliced sample
        if hasattr(centroid1, 'apply_mask'):
            aligned1 = centroid1.apply_mask(idx1)  # Assumes mask-based filtering
            aligned2 = centroid2.apply_mask(idx2)
        else:
            # Fallback: slice arrays directly and create new sample
            aligned1 = cls._slice_sample(centroid1, idx1)
            aligned2 = cls._slice_sample(centroid2, idx2)

        # Clamp zero-coverage in-place (efficient masking)
        for cent in [aligned1, aligned2]:
            zero_mask = (cent.mC + cent.uC) == 0
            if np.any(zero_mask):
                cent.uC[zero_mask] = 1  # Ensure mean=0, avoid div-by-zero in comparisons
                logger.debug(f"Clamped {np.sum(zero_mask)} zero-coverage positions in centroid")

        # Validate min_coverage post-alignment
        max_n = max(
            aligned1.N.max() if aligned1.N is not None else 0,
            aligned2.N.max() if aligned2.N is not None else 0
        )
        if max_n < config.min_coverage:
            logger.warning(f"Max coverage {max_n} < min_coverage {config.min_coverage}; proceeding with warning.")

        return aligned1, aligned2, common_pos

    @staticmethod
    def _slice_sample(sample: 'MethylSample', indices: np.ndarray) -> 'MethylSample':
        """
        Helper to slice a MethylSample by indices (fallback if no native method).

        Creates a new MethylSample with sliced arrays (numpy slicing is view-based for efficiency).
        """
        # Slice all arrays (zero-copy views where possible)
        new_pos = sample.pos[indices]
        new_mC = sample.mC[indices]
        new_uC = sample.uC[indices]
        new_tnc = sample.tnc[indices] if sample.tnc is not None else None
        new_N = sample.N[indices] if sample.N is not None else None
        new_Sx = sample.Sx[indices] if sample.Sx is not None else None
        new_Sx2 = sample.Sx2[indices] if sample.Sx2 is not None else None
        new_log_x_sum = sample.log_x_sum[indices] if sample.log_x_sum is not None else None
        new_log_1_minus_x_sum = sample.log_1_minus_x_sum[indices] if sample.log_1_minus_x_sum is not None else None

        # Reconstruct MethylSample (assumes constructor takes sliced arrays)
        return MethylSample(
            pos=new_pos,
            mC=new_mC,
            uC=new_uC,
            tnc=new_tnc,
            N=new_N,
            Sx=new_Sx,
            Sx2=new_Sx2,
            log_x_sum=new_log_x_sum,
            log_1_minus_x_sum=new_log_1_minus_x_sum
        )

    @classmethod
    def _sort_sample(cls, sample: 'MethylSample', sort_indices: np.ndarray) -> 'MethylSample':
        """
        Helper to sort a MethylSample by position indices.
        """
        # Slice by sort indices to reorder
        return cls._slice_sample(sample, sort_indices)

    # ... rest of existing class (e.g., __init__, compare_centroids) ...

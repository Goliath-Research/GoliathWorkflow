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

        # Validate extended centroids (N, Sx, Sx2)
        if not getattr(centroid1, "is_centroid", False) or not getattr(centroid2, "is_centroid", False):
            raise ValueError("Both inputs must be extended centroids with N, Sx, Sx2.")

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
        Helper to slice a MethylSample or MethylCentroid by indices (fallback if no native method).
        Builds a DataFrame and returns MethylCentroid if full centroid schema present, else MethylSample.
        """
        import pandas as pd
        from methyl_utils.core.methyl_frame import MethylSample, MethylCentroid

        new_pos = sample.pos[indices] if hasattr(sample.pos, '__getitem__') else np.asarray(sample.pos).ravel()[indices]
        new_mC = sample.mC[indices] if hasattr(sample.mC, '__getitem__') else np.asarray(sample.mC).ravel()[indices]
        new_uC = sample.uC[indices] if hasattr(sample.uC, '__getitem__') else np.asarray(sample.uC).ravel()[indices]
        new_tnc = (sample.tnc[indices] if sample.tnc is not None else None)
        has_centroid = (
            hasattr(sample, 'N') and sample.N is not None
            and hasattr(sample, 'Sx') and sample.Sx is not None
            and hasattr(sample, 'Sx2') and sample.Sx2 is not None
            and hasattr(sample, 'Sm') and hasattr(sample, 'Su')
            and hasattr(sample, 'Sc2') and hasattr(sample, 'Swx2')
        )
        if has_centroid:
            new_N = sample.N[indices] if hasattr(sample.N, '__getitem__') else np.asarray(sample.N).ravel()[indices]
            new_Sx = sample.Sx[indices] if hasattr(sample.Sx, '__getitem__') else np.asarray(sample.Sx).ravel()[indices]
            new_Sx2 = sample.Sx2[indices] if hasattr(sample.Sx2, '__getitem__') else np.asarray(sample.Sx2).ravel()[indices]
            new_Sm = sample.Sm[indices] if hasattr(sample.Sm, '__getitem__') else np.asarray(sample.Sm).ravel()[indices]
            new_Su = sample.Su[indices] if hasattr(sample.Su, '__getitem__') else np.asarray(sample.Su).ravel()[indices]
            new_Sc2 = sample.Sc2[indices] if hasattr(sample.Sc2, '__getitem__') else np.asarray(sample.Sc2).ravel()[indices]
            new_Swx2 = sample.Swx2[indices] if hasattr(sample.Swx2, '__getitem__') else np.asarray(sample.Swx2).ravel()[indices]
            df = pd.DataFrame({
                'pos': new_pos, 'tnc': new_tnc, 'N': new_N, 'Sx': new_Sx, 'Sx2': new_Sx2,
                'Sm': new_Sm, 'Su': new_Su, 'Sc2': new_Sc2, 'Swx2': new_Swx2,
            })
            return MethylCentroid(df)
        df = pd.DataFrame({'pos': new_pos, 'mC': new_mC, 'uC': new_uC, 'tnc': new_tnc})
        return MethylSample(df)

    @classmethod
    def _sort_sample(cls, sample: 'MethylSample', sort_indices: np.ndarray) -> 'MethylSample':
        """
        Helper to sort a MethylSample by position indices.
        """
        # Slice by sort indices to reorder
        return cls._slice_sample(sample, sort_indices)

    # ... rest of existing class (e.g., __init__, compare_centroids) ...

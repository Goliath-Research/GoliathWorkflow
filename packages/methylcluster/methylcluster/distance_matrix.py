"""
Distance matrix computation for methylation sample clustering.

This module handles the computation of pairwise distance matrices between
methylation samples using GPU-accelerated metrics from MethylUtils, with
support for caching to improve performance.
"""

import numpy as np
import hashlib
import json
from pathlib import Path
from typing import List, Optional, Tuple
import logging

# Import MethylUtils components
try:
    from methyl_utils.metrics_factory import get_metric_factory
    from methyl_utils.methyl_sample import MethylSample
except ImportError:
    # Fallback for development
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'methylutils'))
    from methyl_utils.metrics_factory import get_metric_factory
    from methyl_utils.methyl_sample import MethylSample

logger = logging.getLogger(__name__)


class DistanceMatrixComputer:
    """
    Computes pairwise distance matrices between methylation samples.
    
    This class handles:
    - Distance computation using MethylUtils GPU-accelerated metrics
    - Caching of computed distance matrices
    - Beta parameter extraction from MethylSample instances
    """
    
    def __init__(
        self,
        metric: str,
        use_gpu: bool = True,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize the distance matrix computer.
        
        Args:
            metric: Distance metric name (e.g., 'jensen_shannon', 'hellinger')
            use_gpu: Whether to use GPU acceleration
            cache_dir: Directory for caching distance matrices
        """
        self.metric_factory = get_metric_factory()
        self.metric = metric
        self.use_gpu = use_gpu
        self.cache_dir = Path(cache_dir) if cache_dir else None
        
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Distance matrix caching enabled: {self.cache_dir}")
    
    def compute_pairwise_distances(
        self,
        samples: List[MethylSample],
        sample_paths: List[Path]
    ) -> np.ndarray:
        """
        Compute pairwise distance matrix using Beta parameters.
        
        Args:
            samples: List of MethylSample instances
            sample_paths: List of sample directory paths (for cache key)
        
        Returns:
            Symmetric distance matrix of shape (n_samples, n_samples)
        """
        logger.info(f"Computing pairwise distances for {len(samples)} samples using {self.metric}")
        
        # Check for cached matrix
        cache_path = self._get_cache_path(sample_paths)
        if cache_path and cache_path.exists():
            logger.info(f"Loading cached distance matrix from {cache_path}")
            return self._load_cached_matrix(cache_path)
        
        n_samples = len(samples)
        distance_matrix = np.zeros((n_samples, n_samples), dtype=np.float32)
        
        # Compute Beta parameters for all samples
        logger.info("Computing Beta parameters from mC/uC counts")
        beta_params = [self._compute_beta_params(s) for s in samples]
        
        # Compute pairwise distances (upper triangle only, since matrix is symmetric)
        logger.info("Computing pairwise distances...")
        total_pairs = (n_samples * (n_samples - 1)) // 2
        computed = 0
        
        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                a1, b1 = beta_params[i]
                a2, b2 = beta_params[j]
                
                # Compute distance using MethylUtils metric factory
                dist = self.metric_factory.compute_distance(
                    self.metric, a1, b1, a2, b2, use_gpu=self.use_gpu
                )
                
                # Average distance across all positions
                avg_dist = float(np.mean(dist))
                distance_matrix[i, j] = avg_dist
                distance_matrix[j, i] = avg_dist
                
                computed += 1
                if computed % 100 == 0:
                    logger.info(f"Computed {computed}/{total_pairs} pairwise distances")
        
        logger.info(f"Distance matrix computation complete: shape {distance_matrix.shape}")
        
        # Cache the matrix
        if cache_path:
            self._save_cached_matrix(distance_matrix, cache_path, sample_paths)
        
        return distance_matrix
    
    def _compute_beta_params(
        self,
        sample: MethylSample
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute Beta distribution parameters from mC/uC counts.
        
        Uses pseudocounts for numerical stability:
        alpha = mC + 1
        beta = uC + 1
        
        Args:
            sample: MethylSample instance
        
        Returns:
            Tuple of (alpha, beta) arrays
        """
        # Add pseudocounts for numerical stability
        alpha = sample.mC.astype(np.float32) + 1.0
        beta = sample.uC.astype(np.float32) + 1.0
        return alpha, beta
    
    def _get_cache_path(self, sample_paths: List[Path]) -> Optional[Path]:
        """
        Generate cache file path based on sample paths and metric.
        
        Args:
            sample_paths: List of sample paths
        
        Returns:
            Path to cache file or None if caching is disabled
        """
        if not self.cache_dir:
            return None
        
        # Create a hash of sample paths and metric for unique identification
        path_str = '|'.join(sorted([str(p) for p in sample_paths]))
        cache_key = f"{path_str}|{self.metric}"
        hash_obj = hashlib.sha256(cache_key.encode())
        cache_hash = hash_obj.hexdigest()[:16]
        
        cache_filename = f"distance_matrix_{cache_hash}.npz"
        return self.cache_dir / cache_filename
    
    def _save_cached_matrix(
        self,
        distance_matrix: np.ndarray,
        cache_path: Path,
        sample_paths: List[Path]
    ) -> None:
        """
        Save distance matrix to cache file.
        
        Args:
            distance_matrix: Distance matrix to cache
            cache_path: Path to cache file
            sample_paths: List of sample paths (for verification)
        """
        logger.info(f"Saving distance matrix to cache: {cache_path}")
        np.savez_compressed(
            cache_path,
            distance_matrix=distance_matrix,
            sample_paths=np.array([str(p) for p in sample_paths]),
            metric=self.metric
        )
    
    def _load_cached_matrix(self, cache_path: Path) -> np.ndarray:
        """
        Load distance matrix from cache file.
        
        Args:
            cache_path: Path to cache file
        
        Returns:
            Cached distance matrix
        """
        data = np.load(cache_path)
        return data['distance_matrix']


__all__ = ['DistanceMatrixComputer']


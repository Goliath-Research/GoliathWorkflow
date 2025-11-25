"""
Centroid Manager for MethylCluster

This module provides cluster centroid management using MethylSample instances
and PositionAligner for dynamic centroid updates.
"""

import numpy as np
import logging
from typing import List, Tuple, Optional
from pathlib import Path
from methyl_utils.beta_analytics import beta_log_pdf

logger = logging.getLogger(__name__)


class ClusterCentroid:
    """
    Manages a single cluster centroid with add/remove operations.
    
    Uses PositionAligner from methyl_utils to maintain a dynamic centroid
    that automatically recalculates when samples are added or removed.
    
    The centroid is represented as a MethylSample instance with extended
    statistics (Sx, Sx2, N) for proper Beta distribution parameter estimation.
    """
    
    def __init__(
        self,
        cluster_id: int,
        chrom: str,
        ctx: str,
        min_coverage: int = 4,
        use_gpu: bool = True,
        max_samples: int = 1000
    ):
        """
        Initialize a cluster centroid.
        
        Args:
            cluster_id: Unique identifier for this cluster
            chrom: Chromosome identifier
            ctx: Context (CG, CHG, CHH)
            min_coverage: Minimum coverage for valid positions
            use_gpu: Whether to use GPU acceleration
            max_samples: Maximum number of samples this cluster can hold
        """
        from methyl_utils.core.methyl_frame import MethylExtendedCentroid
        
        self.cluster_id = cluster_id
        self.chrom = chrom
        self.ctx = ctx
        self.min_coverage = min_coverage
        self.use_gpu = use_gpu
        
        # Initialize empty centroid
        self.centroid: Optional[MethylExtendedCentroid] = None
        
        # Track samples in this cluster: list of (sample_idx, sample_path)
        self.samples: List[Tuple[int, Path]] = []
        
        logger.debug(f"Initialized ClusterCentroid {cluster_id} for {chrom}-{ctx}")
    
    def add_sample(self, sample_idx: int, sample: MethylExtendedCentroid, sample_path: Path) -> bool:
        """
        Add a sample to this cluster and recalculate centroid.
        
        Args:
            sample_idx: Index of the sample
            sample: MethylExtendedCentroid instance
            sample_path: Path to the sample file
            
        Returns:
            True if sample was added successfully
        """
        try:
            if self.centroid is None:
                # First sample - set as centroid
                self.centroid = sample
            else:
                # Add to existing centroid
                self.centroid = self.centroid.add_sample(sample)
            
            self.samples.append((sample_idx, sample_path))
            logger.debug(f"Added sample {sample_idx} to cluster {self.cluster_id} "
                       f"(now {len(self.samples)} samples)")
            return True
                
        except Exception as e:
            logger.error(f"Error adding sample {sample_idx} to cluster {self.cluster_id}: {e}")
            return False
    
    def remove_sample(self, sample_idx: int, sample: MethylExtendedCentroid) -> bool:
        """
        Remove a sample from this cluster and recalculate centroid.
        
        Args:
            sample_idx: Index of the sample to remove
            sample: MethylExtendedCentroid instance
            
        Returns:
            True if sample was removed successfully
        """
        try:
            if self.centroid is None:
                logger.warning(f"Cannot remove from empty cluster {self.cluster_id}")
                return False
            
            # Remove from centroid
            self.centroid = self.centroid.remove_sample(sample)
            
            # Remove from samples list
            self.samples = [(idx, path) for idx, path in self.samples if idx != sample_idx]
            logger.debug(f"Removed sample {sample_idx} from cluster {self.cluster_id} "
                       f"(now {len(self.samples)} samples)")
            return True
                
        except Exception as e:
            logger.error(f"Error removing sample {sample_idx} from cluster {self.cluster_id}: {e}")
            return False
    
    def get_centroid(self) -> MethylExtendedCentroid:
        """
        Get the current centroid as a MethylExtendedCentroid instance.
        
        Returns:
            MethylExtendedCentroid representing the centroid with extended statistics
            
        Raises:
            RuntimeError: If no samples in cluster or no valid positions
        """
        if len(self.samples) == 0 or self.centroid is None:
            logger.warning(f"Cluster {self.cluster_id} is empty, cannot get centroid")
            raise RuntimeError(f"Cluster {self.cluster_id} is empty")
        
        return self.centroid
    
    def compute_log_likelihood(self, sample: MethylExtendedCentroid) -> float:
        """
        Compute log-likelihood of a sample belonging to this centroid.
        
        Uses Beta distribution log-likelihood:
        log P(sample|centroid) = Σ log Beta(sample_meth | centroid_α, centroid_β)
        
        Args:
            sample: MethylExtendedCentroid instance to evaluate
            
        Returns:
            Log-likelihood value (higher = better fit)
        """
        
        try:
            # Get current centroid
            centroid = self.get_centroid()
            
            # Find common positions between sample and centroid
            common_pos = np.intersect1d(sample.pos, centroid.pos, assume_unique=True)
            
            if len(common_pos) == 0:
                logger.warning(f"No common positions between sample and cluster {self.cluster_id}")
                return -np.inf
            
            # Align to common positions
            sample_idx = np.searchsorted(sample.pos, common_pos)
            centroid_idx = np.searchsorted(centroid.pos, common_pos)
            
            # Get sample methylation levels
            sample_mC = sample.mC[sample_idx].astype(np.float64)
            sample_uC = sample.uC[sample_idx].astype(np.float64)
            sample_total = sample_mC + sample_uC
            
            # Avoid division by zero
            valid_coverage = sample_total > 0
            if not np.any(valid_coverage):
                logger.warning(f"No valid coverage for sample in cluster {self.cluster_id}")
                return -np.inf
            
            # Calculate methylation levels (clip to avoid log(0))
            sample_meth = np.zeros_like(sample_mC)
            sample_meth[valid_coverage] = sample_mC[valid_coverage] / sample_total[valid_coverage]
            sample_meth = np.clip(sample_meth, 1e-6, 1.0 - 1e-6)
            
            # Get centroid Beta parameters
            centroid_alpha, centroid_beta = centroid._compute_beta_parameters()
            centroid_alpha = centroid_alpha[centroid_idx]
            centroid_beta = centroid_beta[centroid_idx]
            
            # Filter valid positions (both sample and centroid must be valid)
            valid_params = (centroid_alpha > 0) & (centroid_beta > 0) & valid_coverage
            
            if not np.any(valid_params):
                logger.warning(f"No valid Beta parameters for cluster {self.cluster_id}")
                return -np.inf
            
            # Compute log-likelihood for valid positions
            log_probs = beta_log_pdf(
                sample_meth[valid_params],
                centroid_alpha[valid_params],
                centroid_beta[valid_params],
                use_gpu=self.use_gpu
            )
            
            # Sum log-likelihoods across all valid positions
            total_log_likelihood = np.sum(log_probs)
            
            # Normalize by number of positions to make comparable across samples
            normalized_log_likelihood = total_log_likelihood / np.sum(valid_params)
            
            return float(normalized_log_likelihood)
            
        except Exception as e:
            logger.error(f"Error computing log-likelihood for cluster {self.cluster_id}: {e}")
            return -np.inf
    
    def compute_membership_probabilities(self, sample: 'MethylExtendedCentroid', other_centroids: List['ClusterCentroid'], temperature: float = 1.0) -> float:
        """
        Compute the posterior probability of the sample belonging to this centroid
        relative to other centroids using softmax of averaged log-likelihoods.
        
        Args:
            sample: MethylExtendedCentroid to evaluate
            other_centroids: List of other ClusterCentroid instances for comparison
            temperature: Softmax temperature to control uncertainty (default 1.0)
        
        Returns:
            Probability that sample belongs to this centroid (0-1)
        """
        try:
            # Compute log-likelihood for this centroid (already averaged)
            log_l_this = self.compute_log_likelihood(sample)
            
            # Compute log-likelihoods for other centroids
            log_l_others = []
            for other in other_centroids:
                log_l_others.append(other.compute_log_likelihood(sample))
            
            # Stack all log L (this + others)
            all_log_l = np.array([log_l_this] + log_l_others)
            
            # Handle -inf: set to very low value to avoid NaN in softmax
            all_log_l = np.where(np.isfinite(all_log_l), all_log_l, -1e6)
            
            # Warn if many empty (inf from empty clusters)
            num_empty = np.sum(np.isneginf(np.array([log_l_this] + log_l_others)))
            if num_empty / len(all_log_l) > 0.5:
                logger.warning(f"Many empty clusters ({num_empty}/{len(all_log_l)} in membership probs for sample)—consider more restarts")
            
            # Softmax with temperature: preserves uncertainty
            scaled_log_l = all_log_l / temperature
            max_log = np.max(scaled_log_l)
            exp_terms = np.exp(scaled_log_l - max_log)
            probs = exp_terms / np.sum(exp_terms)
            
            # Return probability for this centroid (index 0)
            return float(probs[0])
            
        except Exception as e:
            logger.error(f"Error computing membership probabilities for cluster {self.cluster_id}: {e}")
            return 0.5  # Neutral probability on error
    
    def get_sample_count(self) -> int:
        """Get the number of samples in this cluster."""
        return len(self.samples)
    
    def get_sample_indices(self) -> List[int]:
        """Get list of sample indices in this cluster."""
        return [idx for idx, _ in self.samples]
    
    def __repr__(self) -> str:
        return f"ClusterCentroid(id={self.cluster_id}, n_samples={len(self.samples)})"


__all__ = ['ClusterCentroid']


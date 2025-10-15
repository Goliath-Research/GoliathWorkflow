"""
Main clustering logic for methylation samples.

This module implements the core MethylCluster class that performs HDBSCAN
clustering on methylation samples using precomputed distance matrices.
"""

import numpy as np
import hdbscan
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import local modules
from .config import MethylClusterConfig
from .distance_matrix import DistanceMatrixComputer

# Import MethylUtils components
try:
    from methyl_utils.methyl_sample import MethylSample
except ImportError:
    # Fallback for development
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'methylutils'))
    from methyl_utils.methyl_sample import MethylSample

logger = logging.getLogger(__name__)


class MethylCluster:
    """
    Performs HDBSCAN clustering on methylation samples.
    
    This class orchestrates the complete clustering workflow:
    1. Load methylation samples from HDF5 files
    2. Compute pairwise distance matrix using GPU-accelerated metrics
    3. Perform HDBSCAN clustering with precomputed distances
    4. Generate and save results with visualizations
    """
    
    def __init__(self, config: MethylClusterConfig):
        """
        Initialize MethylCluster with configuration.
        
        Args:
            config: MethylClusterConfig instance
        """
        self.config = config
        self.samples: List[MethylSample] = []
        self.sample_paths: List[Path] = []
        self.distance_matrix: Optional[np.ndarray] = None
        self.cluster_labels: Optional[np.ndarray] = None
        self.clusterer: Optional[hdbscan.HDBSCAN] = None
        
        logger.info(f"Initialized MethylCluster for {config.chrom}-{config.ctx}")
        logger.info(f"Metric: {config.metric.value}, Min cluster size: {config.min_cluster_size}")
    
    def load_samples(self) -> None:
        """
        Load all samples from configured paths.
        
        Samples are loaded as MethylSample instances from HDF5 files
        named {chrom}-{ctx}.h5 in each sample directory.
        
        Raises:
            FileNotFoundError: If sample file doesn't exist
            ValueError: If sample data is invalid
        """
        logger.info(f"Loading {len(self.config.samples)} samples...")
        
        for i, sample_path_str in enumerate(self.config.samples):
            sample_dir = Path(sample_path_str)
            h5_file = sample_dir / f"{self.config.chrom}-{self.config.ctx}.h5"
            
            if not h5_file.exists():
                raise FileNotFoundError(f"Sample file not found: {h5_file}")
            
            logger.debug(f"Loading sample {i+1}/{len(self.config.samples)}: {h5_file}")
            sample = MethylSample.load_from_h5(h5_file)
            
            self.samples.append(sample)
            self.sample_paths.append(sample_dir)
        
        logger.info(f"Successfully loaded {len(self.samples)} samples")
        
        # Log sample statistics
        n_positions = [len(s.pos) for s in self.samples]
        logger.info(f"Position counts: min={min(n_positions)}, max={max(n_positions)}, "
                   f"mean={np.mean(n_positions):.0f}")
    
    def compute_distances(self) -> None:
        """
        Compute pairwise distance matrix between all samples.
        
        Uses GPU-accelerated distance metrics from MethylUtils with
        optional caching to disk for reuse.
        """
        logger.info("Computing pairwise distance matrix...")
        
        cache_dir = Path(self.config.output_dir) / "cache" if self.config.cache_distance_matrix else None
        
        computer = DistanceMatrixComputer(
            metric=self.config.metric.value,
            use_gpu=self.config.use_gpu,
            cache_dir=cache_dir
        )
        
        self.distance_matrix = computer.compute_pairwise_distances(
            self.samples, self.sample_paths
        )
        
        # Log distance statistics
        tri_upper = np.triu_indices_from(self.distance_matrix, k=1)
        distances = self.distance_matrix[tri_upper]
        logger.info(f"Distance statistics: min={np.min(distances):.4f}, "
                   f"max={np.max(distances):.4f}, mean={np.mean(distances):.4f}, "
                   f"median={np.median(distances):.4f}")
    
    def cluster(self) -> Dict[str, Any]:
        """
        Perform HDBSCAN clustering using precomputed distance matrix.
        
        Returns:
            Dictionary containing clustering results:
            - n_clusters: Number of clusters found
            - n_noise: Number of noise samples
            - cluster_assignments: Dict mapping cluster labels to sample paths
            - labels: List of cluster labels for each sample
            - probabilities: Cluster membership probabilities (if available)
        
        Raises:
            ValueError: If distance matrix hasn't been computed
        """
        if self.distance_matrix is None:
            raise ValueError("Distance matrix must be computed before clustering. Call compute_distances() first.")
        
        logger.info("Performing HDBSCAN clustering...")
        
        # Determine min_samples parameter
        min_samples = self.config.min_samples if self.config.min_samples is not None else self.config.min_cluster_size
        
        logger.info(f"HDBSCAN parameters: min_cluster_size={self.config.min_cluster_size}, "
                   f"min_samples={min_samples}, "
                   f"cluster_selection_epsilon={self.config.cluster_selection_epsilon}, "
                   f"cluster_selection_method={self.config.cluster_selection_method}")
        
        # Create and fit HDBSCAN clusterer
        self.clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            min_samples=min_samples,
            cluster_selection_epsilon=self.config.cluster_selection_epsilon,
            cluster_selection_method=self.config.cluster_selection_method,
            metric='precomputed'
        )
        
        self.cluster_labels = self.clusterer.fit_predict(self.distance_matrix)
        
        logger.info("Clustering complete")
        
        # Compile and return results
        results = self._compile_results()
        logger.info(f"Found {results['n_clusters']} clusters with {results['n_noise']} noise samples")
        
        return results
    
    def _compile_results(self) -> Dict[str, Any]:
        """
        Compile clustering results and statistics.
        
        Returns:
            Dictionary with clustering results
        """
        unique_labels = set(self.cluster_labels)
        n_clusters = len(unique_labels - {-1})  # Exclude noise label (-1)
        n_noise = int(np.sum(self.cluster_labels == -1))
        
        # Create cluster assignments
        clusters = {}
        for label in sorted(unique_labels):
            indices = np.where(self.cluster_labels == label)[0]
            sample_list = [str(self.sample_paths[i]) for i in indices]
            
            if label == -1:
                clusters['noise'] = sample_list
            else:
                clusters[f'cluster_{label}'] = sample_list
        
        # Compile results
        results = {
            'n_clusters': n_clusters,
            'n_noise': n_noise,
            'cluster_assignments': clusters,
            'labels': self.cluster_labels.tolist(),
            'sample_paths': [str(p) for p in self.sample_paths],
            'config': self.config.model_dump()
        }
        
        # Add probabilities if available
        if hasattr(self.clusterer, 'probabilities_'):
            results['probabilities'] = self.clusterer.probabilities_.tolist()
        
        # Add cluster sizes
        cluster_sizes = {}
        for label in unique_labels:
            if label == -1:
                cluster_sizes['noise'] = int(np.sum(self.cluster_labels == -1))
            else:
                cluster_sizes[f'cluster_{label}'] = int(np.sum(self.cluster_labels == label))
        results['cluster_sizes'] = cluster_sizes
        
        return results
    
    def save_results(self, results: Dict[str, Any]) -> None:
        """
        Save clustering results, statistics, and visualizations.
        
        Creates:
        - JSON file with cluster assignments and statistics
        - NPZ file with distance matrix (if caching is enabled)
        - Visualization plots (via ClusterVisualizer)
        
        Args:
            results: Clustering results dictionary from cluster()
        """
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Saving results to {output_dir}")
        
        # Save cluster assignments as JSON
        results_file = output_dir / f"clusters_{self.config.chrom}_{self.config.ctx}.json"
        logger.info(f"Saving cluster assignments to {results_file}")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Save distance matrix
        if self.config.cache_distance_matrix:
            matrix_file = output_dir / f"distance_matrix_{self.config.chrom}_{self.config.ctx}.npz"
            logger.info(f"Saving distance matrix to {matrix_file}")
            np.savez_compressed(
                matrix_file,
                distance_matrix=self.distance_matrix,
                sample_paths=np.array([str(p) for p in self.sample_paths]),
                labels=self.cluster_labels
            )
        
        # Create visualizations
        try:
            from .visualization import ClusterVisualizer
            logger.info("Generating visualizations...")
            visualizer = ClusterVisualizer(self)
            visualizer.create_all_plots(output_dir)
            logger.info("Visualizations complete")
        except Exception as e:
            logger.warning(f"Failed to create visualizations: {e}")
        
        logger.info(f"Results saved to {output_dir}")
    
    def run(self) -> Dict[str, Any]:
        """
        Run the complete clustering workflow.
        
        This convenience method executes all steps:
        1. Load samples
        2. Compute distances
        3. Perform clustering
        4. Save results
        
        Returns:
            Clustering results dictionary
        """
        self.load_samples()
        self.compute_distances()
        results = self.cluster()
        self.save_results(results)
        return results


__all__ = ['MethylCluster']


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
from typing import Dict, Any, List, Optional, Tuple
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

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
        
        cache_dir = Path(self.config.output_dir) if self.config.cache_distance_matrix else None
        
        computer = DistanceMatrixComputer(
            metric=self.config.metric.value,
            chrom=self.config.chrom,
            ctx=self.config.ctx,
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
        Perform clustering using the configured method (HDBSCAN or Hierarchical).
        
        Returns:
            Dictionary containing clustering results:
            - n_clusters: Number of clusters found
            - n_noise: Number of noise samples
            - cluster_assignments: Dict mapping cluster labels to sample paths
            - labels: List of cluster labels for each sample
            - clustering_method: Method used
            - silhouette_score: Quality metric (if applicable)
        
        Raises:
            ValueError: If distance matrix hasn't been computed
        """
        if self.distance_matrix is None:
            raise ValueError("Distance matrix must be computed before clustering. Call compute_distances() first.")
        
        # Choose clustering method
        if self.config.clustering_method.value == "hierarchical":
            return self._hierarchical_clustering()
        else:
            return self._hdbscan_clustering()
    
    def _hdbscan_clustering(self) -> Dict[str, Any]:
        """
        Perform HDBSCAN clustering using precomputed distance matrix.
        
        Returns:
            Dictionary containing clustering results
        """
        logger.info("Performing HDBSCAN clustering...")
        
        # Determine min_samples parameter
        min_samples = self.config.min_samples if self.config.min_samples is not None else self.config.min_cluster_size
        
        logger.info(f"HDBSCAN parameters: min_cluster_size={self.config.min_cluster_size}, "
                   f"min_samples={min_samples}, "
                   f"cluster_selection_epsilon={self.config.cluster_selection_epsilon}, "
                   f"cluster_selection_method={self.config.cluster_selection_method}, "
                   f"allow_single_cluster={self.config.allow_single_cluster}")
        
        # Create and fit HDBSCAN clusterer
        self.clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            min_samples=min_samples,
            cluster_selection_epsilon=self.config.cluster_selection_epsilon,
            cluster_selection_method=self.config.cluster_selection_method,
            allow_single_cluster=self.config.allow_single_cluster,
            metric='precomputed'
        )
        
        self.cluster_labels = self.clusterer.fit_predict(self.distance_matrix)
        
        logger.info("Clustering complete")
        
        # Compile and return results
        results = self._compile_results()
        logger.info(f"Found {results['n_clusters']} clusters with {results['n_noise']} noise samples")
        
        # Check if K-means fallback should be used
        if self.config.enable_kmeans_fallback:
            should_use_fallback = self._should_use_kmeans_fallback(results)
            if should_use_fallback:
                logger.info("HDBSCAN results are ambiguous, trying K-means with automatic K selection...")
                kmeans_results = self._kmeans_clustering_with_silhouette()
                if kmeans_results is not None:
                    logger.info(f"K-means found {kmeans_results['n_clusters']} clusters "
                               f"(silhouette={kmeans_results.get('silhouette_score', 0):.4f})")
                    results = kmeans_results
                else:
                    logger.info("K-means did not find meaningful clusters, keeping HDBSCAN results")
        
        return results
    
    def _hierarchical_clustering(self) -> Dict[str, Any]:
        """
        Perform hierarchical clustering with automatic K selection using silhouette analysis.
        
        Returns:
            Dictionary containing clustering results or indication of homogeneous population
        """
        logger.info("Performing hierarchical clustering with silhouette analysis...")
        
        n_samples = len(self.distance_matrix)
        
        # Check if K is forced
        if self.config.force_k is not None:
            logger.info(f"Forcing K={self.config.force_k} clusters (bypassing silhouette threshold)")
            
            # Convert distance matrix to condensed form for scipy
            condensed_dist = squareform(self.distance_matrix, checks=False)
            
            # Perform hierarchical clustering
            linkage_matrix = linkage(condensed_dist, method=self.config.linkage_method)
            
            # Extract forced number of clusters
            best_labels = fcluster(linkage_matrix, self.config.force_k, criterion='maxclust') - 1
            best_k = self.config.force_k
            best_score = silhouette_score(self.distance_matrix, best_labels, metric='precomputed')
            
            logger.info(f"Forced K={best_k} with silhouette={best_score:.4f}")
            
            self.cluster_labels = best_labels
            silhouette_scores = {best_k: best_score}
            
        else:
            # Automatic K selection using silhouette analysis
            # Determine max_k
            if self.config.max_k is not None:
                max_k = min(self.config.max_k, n_samples - 1)
            else:
                max_k = min(int(np.sqrt(n_samples)), n_samples - 1)
            
            if max_k < 2:
                logger.warning("Not enough samples for hierarchical clustering")
                # Return single cluster with all samples
                self.cluster_labels = np.zeros(n_samples, dtype=int)
                return self._compile_results()
            
            logger.info(f"Testing K from 2 to {max_k} with {self.config.linkage_method} linkage...")
            
            # Convert distance matrix to condensed form for scipy
            condensed_dist = squareform(self.distance_matrix, checks=False)
            
            # Perform hierarchical clustering
            linkage_matrix = linkage(condensed_dist, method=self.config.linkage_method)
            
            best_k = 2
            best_score = -1
            best_labels = None
            silhouette_scores = {}
            
            # Test different numbers of clusters
            for k in range(2, max_k + 1):
                labels = fcluster(linkage_matrix, k, criterion='maxclust') - 1  # Convert to 0-indexed
                
                # Calculate silhouette score using original distance matrix
                score = silhouette_score(self.distance_matrix, labels, metric='precomputed')
                silhouette_scores[k] = score
                
                logger.info(f"  K={k}: silhouette={score:.4f}")
                
                if score > best_score:
                    best_score = score
                    best_k = k
                    best_labels = labels
            
            logger.info(f"Best K={best_k} with silhouette={best_score:.4f}")
            
            self.cluster_labels = best_labels
        
        # Try K-medoids refinement for all K >= 2, even if score is below threshold
        # This can sometimes find better clusters than hierarchical clustering
        if self.config.enable_medoid_refinement and best_k >= 2:
            logger.info(f"Refining {best_k} clusters using K-medoids with farthest-point initialization...")
            refined_labels, refined_score = self._refine_with_kmedoids(best_k)
            
            if refined_score > best_score:
                logger.info(f"Medoid refinement improved silhouette: {best_score:.4f} → {refined_score:.4f}")
                self.cluster_labels = refined_labels
                best_score = refined_score
            else:
                logger.info(f"Medoid refinement did not improve silhouette: {refined_score:.4f} <= {best_score:.4f}")
        
        # Check if final silhouette score meets threshold (unless K is forced)
        if self.config.force_k is None and best_score < self.config.silhouette_threshold:
            logger.info(f"Final silhouette score {best_score:.4f} < threshold {self.config.silhouette_threshold:.4f}")
            logger.info("No meaningful clusters found - population appears homogeneous")
            logger.info("Assigning all samples to a single cluster")
            # Assign all to one cluster
            self.cluster_labels = np.zeros(n_samples, dtype=int)
            results = self._compile_results()
            results['clustering_method'] = 'hierarchical'
            results['silhouette_score'] = float(best_score)
            results['silhouette_scores_by_k'] = {int(k): float(v) for k, v in silhouette_scores.items()}
            results['homogeneous'] = True
            return results
        
        # Compile results
        results = self._compile_results()
        results['clustering_method'] = 'hierarchical'
        results['silhouette_score'] = float(best_score)
        results['silhouette_scores_by_k'] = {int(k): float(v) for k, v in silhouette_scores.items()}
        results['linkage_method'] = self.config.linkage_method
        
        return results
    
    def _refine_with_kmedoids(self, k: int) -> Tuple[np.ndarray, float]:
        """
        Refine clustering using K-medoids (PAM - Partitioning Around Medoids algorithm).
        
        This is a standard implementation of the PAM algorithm:
        1. Initialize: Select k samples that are farthest apart (farthest-first heuristic)
        2. Assignment: Assign each sample to nearest medoid
        3. Update: For each cluster, find new medoid (sample minimizing within-cluster distances)
        4. Repeat 2-3 until convergence
        
        Reference: Kaufman, L. and Rousseeuw, P.J. (1987), Clustering by means of Medoids.
        
        Args:
            k: Number of clusters
            
        Returns:
            Tuple of (labels, silhouette_score)
        """
        n_samples = len(self.distance_matrix)
        max_iterations = self.config.max_medoid_iterations
        
        # Initialize medoids using farthest-point strategy (farthest-first heuristic)
        medoid_indices = self._initialize_farthest_medoids(k)
        logger.info(f"Initial medoids (farthest-first): {medoid_indices}")
        
        # Iterative PAM algorithm
        logger.info(f"Running K-medoids (PAM algorithm)...")
        for iteration in range(max_iterations):
            # Assignment step: assign each sample to nearest medoid
            labels = self._assign_to_nearest_medoid(medoid_indices)
            
            # Update step: find new medoid for each cluster
            new_medoid_indices = self._find_cluster_medoids(labels, k)
            
            # Check convergence
            if set(new_medoid_indices) == set(medoid_indices):
                logger.info(f"K-medoids converged after {iteration + 1} iterations")
                break
            
            medoid_indices = new_medoid_indices
        else:
            logger.info(f"K-medoids reached max iterations ({max_iterations})")
        
        # Final assignment
        labels = self._assign_to_nearest_medoid(medoid_indices)
        
        # Calculate silhouette score
        score = silhouette_score(self.distance_matrix, labels, metric='precomputed')
        
        # Log results
        cluster_sizes = [np.sum(labels == i) for i in range(k)]
        logger.info(f"Final medoids: {medoid_indices}")
        logger.info(f"Cluster sizes: {cluster_sizes}")
        
        return labels, score
    
    def _initialize_farthest_medoids(self, k: int) -> List[int]:
        """
        Initialize k medoids by selecting samples that are farthest apart.
        
        Algorithm:
        1. Start with sample pair that has maximum distance
        2. Iteratively add sample that is farthest from all selected medoids
        
        Args:
            k: Number of medoids to select
            
        Returns:
            List of medoid indices
        """
        n_samples = len(self.distance_matrix)
        
        # Start with the two samples that are farthest apart
        max_dist = 0
        medoid_indices = [0, 1]
        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                if self.distance_matrix[i, j] > max_dist:
                    max_dist = self.distance_matrix[i, j]
                    medoid_indices = [i, j]
        
        # If k == 2, we're done
        if k == 2:
            return medoid_indices
        
        # For k > 2, iteratively add farthest samples
        for _ in range(k - 2):
            max_min_dist = -1
            next_medoid = -1
            
            for i in range(n_samples):
                if i in medoid_indices:
                    continue
                
                # Find minimum distance from i to any medoid
                min_dist = min(self.distance_matrix[i, m] for m in medoid_indices)
                
                # Keep track of sample with maximum min_dist
                if min_dist > max_min_dist:
                    max_min_dist = min_dist
                    next_medoid = i
            
            medoid_indices.append(next_medoid)
        
        return medoid_indices
    
    def _assign_to_nearest_medoid(self, medoid_indices: List[int]) -> np.ndarray:
        """
        Assign each sample to its nearest medoid.
        
        Args:
            medoid_indices: List of medoid sample indices
            
        Returns:
            Array of cluster labels
        """
        n_samples = len(self.distance_matrix)
        labels = np.zeros(n_samples, dtype=int)
        
        for i in range(n_samples):
            distances_to_medoids = [self.distance_matrix[i, m] for m in medoid_indices]
            labels[i] = int(np.argmin(distances_to_medoids))
        
        return labels
    
    def _find_cluster_medoids(self, labels: np.ndarray, k: int) -> List[int]:
        """
        Find the medoid (most central sample) for each cluster.
        
        The medoid is the sample that minimizes the sum of distances to all
        other samples in the cluster (standard PAM definition).
        
        Args:
            labels: Current cluster assignments
            k: Number of clusters
            
        Returns:
            List of medoid indices
        """
        medoid_indices = []
        
        for cluster_id in range(k):
            cluster_samples = np.where(labels == cluster_id)[0]
            
            if len(cluster_samples) == 0:
                # Empty cluster - use random sample
                logger.warning(f"Empty cluster {cluster_id}, using random sample")
                medoid_indices.append(int(np.random.choice(len(labels))))
                continue
            
            if len(cluster_samples) == 1:
                # Single sample cluster
                medoid_indices.append(int(cluster_samples[0]))
                continue
            
            # Find sample with minimum sum of distances to all cluster members
            min_sum_dist = np.inf
            medoid = cluster_samples[0]
            
            for candidate in cluster_samples:
                sum_dist = self.distance_matrix[candidate, cluster_samples].sum()
                if sum_dist < min_sum_dist:
                    min_sum_dist = sum_dist
                    medoid = candidate
            
            medoid_indices.append(int(medoid))
        
        return medoid_indices
    
    def _compile_results(self) -> Dict[str, Any]:
        """
        Compile clustering results and statistics.
        
        Returns:
            Dictionary with clustering results
        """
        # Ensure cluster_labels matches sample count
        if len(self.cluster_labels) != len(self.sample_paths):
            raise ValueError(f"Mismatch: {len(self.cluster_labels)} labels but {len(self.sample_paths)} samples")
        
        unique_labels = set(self.cluster_labels)
        n_clusters = len(unique_labels - {-1})  # Exclude noise label (-1)
        n_noise = int(np.sum(self.cluster_labels == -1))
        
        # Create cluster assignments
        clusters = {}
        for label in sorted(unique_labels):
            indices = np.where(self.cluster_labels == label)[0]
            # Validate indices
            if np.any(indices >= len(self.sample_paths)):
                raise ValueError(f"Invalid indices: max={indices.max()}, n_samples={len(self.sample_paths)}")
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
    
    def _should_use_kmeans_fallback(self, hdbscan_results: Dict[str, Any]) -> bool:
        """
        Determine if K-means fallback should be used based on HDBSCAN results.
        
        Args:
            hdbscan_results: Results from HDBSCAN clustering
        
        Returns:
            True if K-means fallback should be attempted
        """
        n_clusters = hdbscan_results['n_clusters']
        n_noise = hdbscan_results['n_noise']
        n_samples = len(self.cluster_labels)
        noise_pct = n_noise / n_samples
        
        # Use fallback if:
        # 1. No clusters found (all noise)
        # 2. Only 1 cluster with > 20% noise (ambiguous)
        # 3. Multiple clusters but > 50% noise (weak structure)
        
        if n_clusters == 0:
            logger.info("  Reason: HDBSCAN found no clusters (all noise)")
            return True
        
        if n_clusters == 1 and noise_pct > 0.2:
            logger.info(f"  Reason: Single cluster with {noise_pct*100:.1f}% noise (ambiguous)")
            return True
        
        if n_clusters >= 2 and noise_pct > 0.5:
            logger.info(f"  Reason: {n_clusters} clusters but {noise_pct*100:.1f}% noise (weak structure)")
            return True
        
        return False
    
    def _kmeans_clustering_with_silhouette(self) -> Optional[Dict[str, Any]]:
        """
        Perform K-means clustering with automatic K selection using silhouette analysis.
        
        Tests K from 2 to max_k and selects the K with the highest silhouette score.
        If the best silhouette score is below the threshold, returns None (no meaningful clusters).
        
        Returns:
            Dictionary with clustering results or None if no meaningful clusters found
        """
        n_samples = len(self.distance_matrix)
        
        # Determine max_k
        if self.config.max_k is not None:
            max_k = min(self.config.max_k, n_samples - 1)
        else:
            max_k = min(int(np.sqrt(n_samples)), n_samples - 1)
        
        if max_k < 2:
            logger.warning("Not enough samples for K-means clustering")
            return None
        
        logger.info(f"Testing K-means for K=2 to K={max_k}...")
        
        # Convert distance matrix to feature space using MDS
        # K-means needs coordinates, not distances
        from sklearn.manifold import MDS
        
        logger.info("Converting distance matrix to feature space using MDS...")
        mds = MDS(n_components=min(10, n_samples - 1), dissimilarity='precomputed', random_state=42)
        X = mds.fit_transform(self.distance_matrix)
        
        best_k = 2
        best_score = -1
        best_labels = None
        silhouette_scores = {}
        
        for k in range(2, max_k + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X)
            
            # Calculate silhouette score using original distance matrix
            score = silhouette_score(self.distance_matrix, labels, metric='precomputed')
            silhouette_scores[k] = score
            
            logger.info(f"  K={k}: silhouette={score:.4f}")
            
            if score > best_score:
                best_score = score
                best_k = k
                best_labels = labels
        
        logger.info(f"Best K={best_k} with silhouette={best_score:.4f}")
        
        # Check if silhouette score meets threshold
        if best_score < self.config.silhouette_threshold:
            logger.info(f"Best silhouette score {best_score:.4f} < threshold {self.config.silhouette_threshold:.4f}")
            logger.info("No meaningful clusters found - population appears homogeneous")
            return None
        
        # Update cluster_labels for visualization
        self.cluster_labels = best_labels
        
        # Compile results
        results = {
            'n_clusters': best_k,
            'n_noise': 0,  # K-means doesn't have noise
            'cluster_assignments': {},
            'labels': best_labels.tolist(),
            'sample_paths': [str(p) for p in self.sample_paths],
            'config': self.config.model_dump(),
            'clustering_method': 'kmeans',
            'silhouette_score': float(best_score),
            'silhouette_scores_by_k': {int(k): float(v) for k, v in silhouette_scores.items()}
        }
        
        # Create cluster assignments
        for k in range(best_k):
            indices = np.where(best_labels == k)[0]
            sample_list = [str(self.sample_paths[i]) for i in indices]
            results['cluster_assignments'][f'cluster_{k}'] = sample_list
        
        # Add cluster sizes
        cluster_sizes = {}
        for k in range(best_k):
            cluster_sizes[f'cluster_{k}'] = int(np.sum(best_labels == k))
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


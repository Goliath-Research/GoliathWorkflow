from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import numpy as np
import random
from collections import defaultdict
from methyl_utils.core.methyl_frame import MethylCentroid
from methyl_utils.beta_analytics import beta_log_pdf, compute_beta_mean, compute_beta_variance



@dataclass
class DPConfig:
    n_components: int = 10
    alpha: float = 1.0
    max_iter: int = 100
    tol: float = 1e-4
    use_gpu: bool = True
    min_cluster_size: int = 2
    seed: int = 42


@dataclass
class MethylClusterDP:
    cfg: DPConfig
    centroids: List["MethylSample"] = field(default_factory=list)
    
    def fit(self, samples: List["MethylSample"], max_samples: Optional[int] = None) -> None:
        if max_samples is not None:
            samples = random.sample(samples, min(max_samples, len(samples)))
        
        n_samples = len(samples)
        assignments = np.full(n_samples, -1, dtype=int)
        
        # Initialize first centroid with random sample
        first_sample_idx = random.randint(0, n_samples - 1)
        self.centroids.append(self._build_centroid([samples[first_sample_idx]]))
        assignments[first_sample_idx] = 0
        
        for i in range(1, n_samples):
            # Assign or create new cluster
            max_ll = -np.inf
            best_cluster = -1
            for j, centroid in enumerate(self.centroids):
                ll = self._log_pred_lik(centroid, samples[i])
                if ll > max_ll:
                    max_ll = ll
                    best_cluster = j
            
            # Probability of new cluster
            new_ll = self._log_prior_pred_lik(samples[i]) + np.log(self.cfg.alpha / (i + self.cfg.alpha))
            
            if new_ll > max_ll:
                # Create new centroid
                self.centroids.append(self._build_centroid([samples[i]]))
                assignments[i] = len(self.centroids) - 1
            else:
                assignments[i] = best_cluster
        
        # Iterative refinement
        for iter in range(self.cfg.max_iter):
            changes = 0
            for i in random.sample(range(n_samples), n_samples):
                old_cluster = assignments[i]
                if old_cluster == -1:
                    continue
                
                # Temporarily remove from old cluster
                self.centroids[old_cluster] = self.centroids[old_cluster].remove_sample(samples[i])
                
                # Find best cluster or new
                best_cluster, best_ll = self._reassign_one(samples, i)
                
                if best_cluster != old_cluster:
                    changes += 1
                    assignments[i] = best_cluster
                    self.centroids[best_cluster] = self.centroids[best_cluster].add_sample(samples[i])
            
            # logger.info(f"Iter {iter+1}: {changes} changes") # Original code had this line commented out
            if changes / n_samples < self.cfg.tol:
                break
        
        # Enforce min cluster size
        cluster_sizes = [sum(assignments == i) for i in range(len(self.centroids))]
        small_clusters = [i for i, size in enumerate(cluster_sizes) if size < self.cfg.min_cluster_size]
        
        for small_id in small_clusters:
            # Merge small cluster into largest
            large_id = np.argmax(cluster_sizes)
            small_samples = [samples[j] for j in np.where(assignments == small_id)[0]]
            for s in small_samples:
                self.centroids[large_id] = self.centroids[large_id].add_sample(s)
            assignments[assignments == small_id] = large_id
            del self.centroids[small_id]
        
        # logger.info(f"Final clusters: {len(self.centroids)}") # Original code had this line commented out
    
    def predict(self, samples: List["MethylSample"]) -> np.ndarray:
        assignments = np.zeros(len(samples), dtype=int)
        for i, s in enumerate(samples):
            assignments[i] = self._argmax_existing_logprob(s)
        return assignments
    
    def predict_log_proba(self, samples: List["MethylSample"]) -> np.ndarray:
        probs = np.zeros((len(samples), len(self.centroids)))
        for i, s in enumerate(samples):
            for j, c in enumerate(self.centroids):
                probs[i, j] = self._log_pred_lik(c, s)
        return probs
    
    def _build_centroid(self, sample_list: List["MethylSample"]) -> "MethylSample":
        return MethylSample.create_centroid_from_samples(sample_list, use_gpu=self.cfg.use_gpu)
    
    def _reassign_one(self, samples: List["MethylSample"], i: int):
        max_ll = -np.inf
        best_cluster = -1
        for j, centroid in enumerate(self.centroids):
            ll = self._log_pred_lik(centroid, samples[i])
            if ll > max_ll:
                max_ll = ll
                best_cluster = j
        return best_cluster, max_ll
    
    def _log_pred_lik(self, centroid: "MethylSample", sample: "MethylSample") -> float:
        common_pos = np.intersect1d(centroid.pos, sample.pos)
        if len(common_pos) == 0:
            return -np.inf
        
        sample_idx = np.searchsorted(sample.pos, common_pos)
        centroid_idx = np.searchsorted(centroid.pos, common_pos)
        
        sample_meth = sample.mC[sample_idx] / (sample.mC[sample_idx] + sample.uC[sample_idx])
        alpha = centroid.alpha[centroid_idx]
        beta = centroid.beta[centroid_idx]
        
        return np.sum(beta_log_pdf(sample_meth, alpha, beta))
    
    def _log_prior_pred_lik(self, sample: "MethylSample") -> float:
        # Prior predictive likelihood for new cluster
        return 0.0  # Simplified; implement proper prior
    
    def _argmax_existing_logprob(self, sample: "MethylSample") -> int:
        max_ll = -np.inf
        best = 0
        for j, c in enumerate(self.centroids):
            ll = self._log_pred_lik(c, sample)
            if ll > max_ll:
                max_ll = ll
                best = j
        return best

    def _joint_log_predictive(self, samples: List["MethylSample"]) -> float:
        total = 0.0
        for s in samples:
            total += self._log_prior_pred_lik(s)
        return total



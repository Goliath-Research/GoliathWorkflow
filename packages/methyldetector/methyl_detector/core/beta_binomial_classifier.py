"""Beta-Binomial classifier for unified multi-context chromosome-level classification."""

import numpy as np
import pandas as pd
from scipy.special import gammaln
from typing import Optional, Dict, Any
from pathlib import Path


class BetaBinomialClassifier:
    """
    Unified Beta-Binomial classifier for multi-context chromosome analysis.
    
    Uses log-likelihood ratios (LLR) to classify samples based on Beta-Binomial
    distribution matching between sample counts and centroid Beta parameters.
    
    Mathematical Model:
    ------------------
    For each CpG site i with methylated counts m_i, unmethylated counts u_i:
    - Sample: (m_i, u_i) where n_i = m_i + u_i
    - Centroid C (Cancer): Beta(α_i^C, β_i^C)
    - Centroid H (Healthy): Beta(α_i^H, β_i^H)
    
    Per-site log-likelihood ratio:
        LLR_i = log P(m_i, u_i | C) - log P(m_i, u_i | H)
             = [log B(m_i + α_i^C, u_i + β_i^C) - log B(α_i^C, β_i^C)]
               - [log B(m_i + α_i^H, u_i + β_i^H) - log B(α_i^H, β_i^H)]
    
    where log B(x, y) = log Γ(x) + log Γ(y) - log Γ(x + y)
    
    Chromosome-level score (weighted sum across contexts):
        Δ_k = Σ_i w_i * LLR_i
    
    where w_i is the context weight (γ_c) for position i's context.
    
    Classification probability:
        P(Cancer | sample) = sigmoid(Δ_k) = 1 / (1 + exp(-Δ_k))
    """
    
    def __init__(
        self,
        chromosome: str,
        positions: np.ndarray,
        contexts: np.ndarray,
        alpha1: np.ndarray,
        beta1: np.ndarray,
        alpha2: np.ndarray,
        beta2: np.ndarray,
        weights: np.ndarray
    ):
        """
        Initialize Beta-Binomial classifier.
        
        Args:
            chromosome: Chromosome identifier (e.g., "1", "X")
            positions: Array of genomic positions (DMP sites)
            contexts: Array of context strings parallel to positions (e.g., "CG", "CHG")
            alpha1: Beta distribution alpha parameters for centroid 1 (Healthy)
            beta1: Beta distribution beta parameters for centroid 1
            alpha2: Beta distribution alpha parameters for centroid 2 (Cancer)
            beta2: Beta distribution beta parameters for centroid 2
            weights: Per-position weights (γ_c for each position's context)
        """
        self.chromosome = str(chromosome)
        self.positions = np.asarray(positions, dtype=np.uint32)
        self.contexts = np.asarray(contexts, dtype=str)
        self.alpha1 = np.asarray(alpha1, dtype=np.float64)
        self.beta1 = np.asarray(beta1, dtype=np.float64)
        self.alpha2 = np.asarray(alpha2, dtype=np.float64)
        self.beta2 = np.asarray(beta2, dtype=np.float64)
        self.weights = np.asarray(weights, dtype=np.float64)
        
        # Validate shapes
        n = len(self.positions)
        assert len(self.contexts) == n, "contexts must match positions length"
        assert len(self.alpha1) == n, "alpha1 must match positions length"
        assert len(self.beta1) == n, "beta1 must match positions length"
        assert len(self.alpha2) == n, "alpha2 must match positions length"
        assert len(self.beta2) == n, "beta2 must match positions length"
        assert len(self.weights) == n, "weights must match positions length"
        
        # Build position lookup for fast indexing
        self._build_position_index()
    
    def _build_position_index(self):
        """Build position->index lookup for efficient sample processing."""
        self.position_to_idx = {}
        for i, (pos, ctx) in enumerate(zip(self.positions, self.contexts)):
            key = (int(pos), str(ctx))
            self.position_to_idx[key] = i
    
    @classmethod
    def from_dataframe(cls, dmps_df: pd.DataFrame, chromosome: str) -> 'BetaBinomialClassifier':
        """
        Build classifier from unified DataFrame with all contexts.
        
        Args:
            dmps_df: DataFrame with required columns:
                - position, context, alpha1, beta1, alpha2, beta2, context_weight
            chromosome: Chromosome identifier
            
        Returns:
            BetaBinomialClassifier instance
        """
        required_cols = ['position', 'context', 'alpha1', 'beta1', 'alpha2', 'beta2', 'context_weight']
        missing = [c for c in required_cols if c not in dmps_df.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")
        
        return cls(
            chromosome=chromosome,
            positions=dmps_df['position'].values,
            contexts=dmps_df['context'].values,
            alpha1=dmps_df['alpha1'].values,
            beta1=dmps_df['beta1'].values,
            alpha2=dmps_df['alpha2'].values,
            beta2=dmps_df['beta2'].values,
            weights=dmps_df['context_weight'].values
        )
    
    @staticmethod
    def compute_log_beta(x: float, y: float) -> float:
        """
        Compute log of Beta function: log B(x, y) = log Γ(x) + log Γ(y) - log Γ(x + y)
        
        Args:
            x: First parameter
            y: Second parameter
            
        Returns:
            log B(x, y)
        """
        return gammaln(x) + gammaln(y) - gammaln(x + y)
    
    def compute_site_llr(
        self,
        m: int,
        u: int,
        alpha_C: float,
        beta_C: float,
        alpha_H: float,
        beta_H: float
    ) -> float:
        """
        Compute per-site log-likelihood ratio.
        
        Args:
            m: Methylated read count at site
            u: Unmethylated read count at site
            alpha_C, beta_C: Beta parameters for Cancer centroid
            alpha_H, beta_H: Beta parameters for Healthy centroid
            
        Returns:
            LLR_i = log P(m, u | Cancer) - log P(m, u | Healthy)
        """
        # Log-likelihood for Cancer centroid
        llr_cancer = self.compute_log_beta(m + alpha_C, u + beta_C) - \
                     self.compute_log_beta(alpha_C, beta_C)
        
        # Log-likelihood for Healthy centroid
        llr_healthy = self.compute_log_beta(m + alpha_H, u + beta_H) - \
                      self.compute_log_beta(alpha_H, beta_H)
        
        return llr_cancer - llr_healthy
    
    def predict_sample(
        self,
        sample_positions: np.ndarray,
        sample_contexts: np.ndarray,
        sample_m: np.ndarray,
        sample_u: np.ndarray
    ) -> Dict[str, Any]:
        """
        Predict cancer probability for a sample using vectorized operations.
        
        Args:
            sample_positions: Array of genomic positions in sample
            sample_contexts: Array of contexts parallel to positions
            sample_m: Array of methylated counts
            sample_u: Array of unmethylated counts
            
        Returns:
            Dictionary with:
                - chromosome_llr: Δ_k (weighted sum of LLRs)
                - probability: P(Cancer | sample)
                - n_sites_used: Number of overlapping sites used
                - per_context_llr: LLR contribution by context
        """
        llr_sum = 0.0
        n_used = 0
        per_context_llr = {}
        
        # Process each position in sample
        for i, (pos, ctx, m, u) in enumerate(zip(sample_positions, sample_contexts, sample_m, sample_u)):
            # Skip sites with no coverage
            if m + u == 0:
                continue
            
            # Check if this position is a DMP in our model
            key = (int(pos), str(ctx))
            if key not in self.position_to_idx:
                continue
            
            # Get model parameters for this DMP
            idx = self.position_to_idx[key]
            
            # Compute weighted LLR
            llr = self.compute_site_llr(
                m, u,
                self.alpha2[idx], self.beta2[idx],  # Cancer (class 2)
                self.alpha1[idx], self.beta1[idx]   # Healthy (class 1)
            )
            weighted_llr = self.weights[idx] * llr
            llr_sum += weighted_llr
            n_used += 1
            
            # Track per-context contributions
            if ctx not in per_context_llr:
                per_context_llr[ctx] = 0.0
            per_context_llr[ctx] += weighted_llr
        
        # Compute probability using sigmoid
        prob = 1.0 / (1.0 + np.exp(-llr_sum))
        
        return {
            'chromosome_llr': float(llr_sum),
            'probability': float(prob),
            'n_sites_used': n_used,
            'per_context_llr': per_context_llr
        }
    
    def predict_proba(self, sample) -> Dict[str, Any]:
        """
        Predict cancer probability for a MethylSample object.
        
        Args:
            sample: MethylSample with methylation data
            
        Returns:
            Dictionary with prediction results
        """
        # Extract sample data based on our DMP positions
        sample_positions = []
        sample_contexts = []
        sample_m = []
        sample_u = []
        
        for pos, ctx in zip(self.positions, self.contexts):
            # Try to get counts for this position/context from sample
            try:
                # Assuming MethylSample has a method to get counts
                if hasattr(sample, 'get_counts'):
                    m, u = sample.get_counts(pos, ctx)
                elif hasattr(sample, 'methylation_counts') and hasattr(sample, 'total_counts'):
                    # Alternative: use arrays directly
                    idx = np.where((sample.pos == pos) & (sample.context == ctx))[0]
                    if len(idx) > 0:
                        m = sample.methylation_counts[idx[0]]
                        u = sample.total_counts[idx[0]] - m
                    else:
                        continue
                else:
                    continue
                
                sample_positions.append(pos)
                sample_contexts.append(ctx)
                sample_m.append(m)
                sample_u.append(u)
            except Exception:
                continue
        
        # Convert to arrays and predict
        return self.predict_sample(
            np.array(sample_positions),
            np.array(sample_contexts),
            np.array(sample_m),
            np.array(sample_u)
        )
    
    def save(self, path: Path):
        """Save classifier to pickle file."""
        import pickle
        with open(path, 'wb') as f:
            pickle.dump(self, f)
    
    @classmethod
    def load(cls, path: Path) -> 'BetaBinomialClassifier':
        """Load classifier from pickle file."""
        import pickle
        with open(path, 'rb') as f:
            return pickle.load(f)
    
    def __repr__(self):
        unique_contexts = np.unique(self.contexts)
        n_per_context = {ctx: np.sum(self.contexts == ctx) for ctx in unique_contexts}
        return (f"BetaBinomialClassifier(chromosome={self.chromosome}, "
                f"n_dmps={len(self.positions)}, "
                f"contexts={dict(n_per_context)})")


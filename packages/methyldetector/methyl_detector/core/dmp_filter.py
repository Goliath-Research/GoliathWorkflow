"""
DMP Filtering Module for MethylDetector

This module provides advanced filtering of differentially methylated positions (DMPs)
to select those with the highest discrimination power between experimental groups.
It implements various effect size metrics including distribution overlap, delta mean,
Jeffreys divergence, and AUC-based discrimination.
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import warnings

# Import directly from MethylUtils
from methyl_utils.gpu_detection import (
    is_gpu_available, 
    is_cupyx_scipy_available,
    is_cupyx_scipy_special_available,
    cleanup_gpu_memory
)

# Import directly from MethylUtils
# Import statistical functions from MethylUtils (required)
from methyl_utils import compute_beta_llr_moments

# Optional imports for advanced metrics
try:
    from scipy.special import digamma, betaln
    from scipy.stats import norm
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Initialize logger for import-time warnings
logger = logging.getLogger(__name__)

# Suppress warnings during import
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*import.*", category=ImportWarning)

# GPU availability flags
GPU_AVAILABLE = is_gpu_available()
CUPY_SCIPY_AVAILABLE = is_cupyx_scipy_available()
cupy_special_available = is_cupyx_scipy_special_available()

# Import GPU libraries if available
if GPU_AVAILABLE and cupy_special_available:
    try:
        import cupy as cp
            
        logger.debug("GPU acceleration available for DMP filter")
    except ImportError as e:
        logger.warning(f"Failed to import GPU libraries: {e}")
        GPU_AVAILABLE = False
        CUPY_SCIPY_AVAILABLE = False
        cupy_special_available = False
else:
    logger.debug("GPU not available, using CPU-only mode for DMP filter")

@dataclass
class DMPFilterResult:
    """Result of DMP filtering with discrimination metrics."""
    position: int
    p_value: float
    q_value: float
    Δμ: float
    distribution_overlap: Optional[float] = None
    bhattacharyya: Optional[float] = None
    JD: Optional[float] = None
    cohen_d: Optional[float] = None
    auc_score: Optional[float] = None
    alpha1: Optional[float] = None
    beta1: Optional[float] = None
    alpha2: Optional[float] = None
    beta2: Optional[float] = None
    mean1: float = 0.0
    mean2: float = 0.0
    selected: bool = False
    selection_reason: str = ""
    signed_auc: Optional[float] = None  # 2*P(X1>X2)-1, signed in (-1,1)
    direction: int = 0                  # +1 hyper(disease), -1 hypo(disease), 0 tie
    w: Optional[float] = None           # composite rank weight = JD * |signed_auc|**gamma

@dataclass
class DMPData:
    """Typed data structure for DMP processing with NumPy arrays."""
    positions: np.ndarray
    p_values: np.ndarray
    q_values: np.ndarray
    mean1: np.ndarray
    mean2: np.ndarray
    alpha1: np.ndarray
    beta1: np.ndarray
    alpha2: np.ndarray
    beta2: np.ndarray
    variance1: Optional[np.ndarray] = None
    variance2: Optional[np.ndarray] = None
    
    def __post_init__(self):
        """Ensure all arrays have the same length and valid parameters."""
        n = len(self.positions)
        assert all(len(arr) == n for arr in [self.p_values, self.q_values, self.mean1, self.mean2, 
                                             self.alpha1, self.beta1, self.alpha2, self.beta2])
        assert np.all(self.alpha1 > 0) and np.all(self.beta1 > 0), "Alpha1/Beta1 must be positive"
        assert np.all(self.alpha2 > 0) and np.all(self.beta2 > 0), "Alpha2/Beta2 must be positive"
        self.alpha1 = np.maximum(self.alpha1, 1e-6)
        self.beta1 = np.maximum(self.beta1, 1e-6)
        self.alpha2 = np.maximum(self.alpha2, 1e-6)
        self.beta2 = np.maximum(self.beta2, 1e-6)
        if self.variance1 is not None:
            assert len(self.variance1) == n
        if self.variance2 is not None:
            assert len(self.variance2) == n
    
    @property
    def n_dmps(self) -> int:
        """Number of DMPs."""
        return len(self.positions)
    
    def __len__(self) -> int:
        """Return the number of DMPs."""
        return len(self.positions)
    
    @property
    def delta_means(self) -> np.ndarray:
        """Calculate delta means (|mean1 - mean2|)."""
        return np.abs(self.mean1 - self.mean2).astype(np.float32)


class DMPFilter:
    """
    Advanced DMP filtering for selecting highly discriminative positions.

    This class implements multiple effect size metrics to filter DMPs based on
    their discrimination power between experimental groups.
    """

    def __init__(
        self,
        min_overlap: float = 0.6,
        min_Δμ: float = 0.2,
        min_JD: float = 0.5,
        min_cohen_d: float = 0.8,
        min_auc: float = 0.7,
        max_selected_dmps: Optional[int] = None,
        selection_method: str = "combined",
        use_gpu: bool = True,
        simulation_samples: int = 1000,
        gamma: float = 1.5
    ):
        """
        Initialize DMP filter with user-defined thresholds.

        Args:
            min_overlap: Maximum allowed distribution overlap (default: 0.6)
            min_Δμ: Minimum delta mean threshold (default: 0.2)
            min_JD: Minimum Jeffreys divergence (default: 0.5)
            min_cohen_d: Minimum Cohen's d (default: 0.8)
            min_auc: Minimum AUC score (default: 0.7)
            max_selected_dmps: Maximum number of DMPs to select (default: None)
            selection_method: Filtering method ('combined', 'threshold', etc.) (default: "combined")
            use_gpu: Use GPU acceleration if available (default: True)
            simulation_samples: Samples for simulation-based metrics (default: 1000)
            gamma: Exponent for signed AUC in weight calculation (default: 1.5)
        """
        self.min_overlap = min_overlap
        self.min_Δμ = min_Δμ
        self.min_JD = min_JD
        self.min_cohen_d = min_cohen_d
        self.min_auc = min_auc
        self.max_selected_dmps = max_selected_dmps
        self.selection_method = selection_method
        self.use_gpu = use_gpu
        self.simulation_samples = simulation_samples
        self.gamma = gamma

    def gpu_filter_dmps(self, data: DMPData, export_prefix: Optional[str] = None, export_dir: Optional[Path] = None) -> List[DMPFilterResult]:
        """Filter DMPs using vectorized metrics computation."""
        use_gpu = self.use_gpu and GPU_AVAILABLE
        
        # Compute delta mean
        delta_mean = data.delta_means
        
        # Compute overlap
        bc = self._compute_bhattacharyya_coeff(data.alpha1, data.beta1, data.alpha2, data.beta2, use_gpu)
        overlap = 1 - bc

        # Compute JD
        jd = self._compute_jeffreys_divergence(data.alpha1, data.beta1, data.alpha2, data.beta2, use_gpu)
        
        # Compute Cohen's d
        cohen_d = self._compute_cohen_d(data.mean1, data.mean2, data.variance1, data.variance2, use_gpu)
        
        # Compute AUC (analytical)
        da = data.alpha1 - data.alpha2
        db = data.beta1 - data.beta2
        mu1, var1 = compute_beta_llr_moments(data.alpha1, data.beta1, da, db, use_gpu)
        mu2, var2 = compute_beta_llr_moments(data.alpha2, data.beta2, da, db, use_gpu)

        # Clip variances to prevent overflow when summing
        max_reasonable_var = 1e12
        var1 = np.clip(var1, 1e-10, max_reasonable_var)
        var2 = np.clip(var2, 1e-10, max_reasonable_var)

        d = np.abs(mu1 - mu2) / np.sqrt(var1 + var2 + 1e-10)
        auc_score = norm.cdf(d)

        #auc_score = np.zeros(len(data.positions), dtype=np.float32)
        #for i in range(len(data.positions)):
        #    auc_score[i] = self._single_dmp_auc(data.alpha1[i], data.beta1[i], data.alpha2[i], data.beta2[i], use_gpu)
        
        # Create results
        results = []
        for i in range(len(data.positions)):
            r = DMPFilterResult(
                position=int(data.positions[i]),
                p_value=float(data.p_values[i]),
                q_value=float(data.q_values[i]),
                Δμ=float(delta_mean[i]),
                distribution_overlap=float(overlap[i]) if overlap[i] is not None else None,
                JD=float(jd[i]) if jd[i] is not None else None,
                cohen_d=float(cohen_d[i]) if cohen_d[i] is not None else None,
                auc_score=float(auc_score[i]) if auc_score[i] is not None else None,
                alpha1=float(data.alpha1[i]),
                beta1=float(data.beta1[i]),
                alpha2=float(data.alpha2[i]),
                beta2=float(data.beta2[i]),
                mean1=float(data.mean1[i]),
                mean2=float(data.mean2[i])
            )
            results.append(r)
        
        # Refine directional AUC and compute w
        results = self.refine_directional_auc(results)
        
        # Compute ranking metric: delta_mean / overlap
        rank_metric = delta_mean / (1 - overlap + 1e-6)
        #rank_metric = delta_mean / np.maximum(overlap, 1e-6)
        
        # Sort results by rank_metric descending
        indices = np.argsort(rank_metric)[::-1]
        results = [results[i] for i in indices]
        
        # Apply max_selected_dmps
        if self.max_selected_dmps is not None and len(results) > self.max_selected_dmps:
            results = results[:self.max_selected_dmps]
        
        if self.use_gpu and GPU_AVAILABLE:
            cleanup_gpu_memory()
        
        # Export results if requested
        if export_prefix and export_dir:
            try:
                statistics = {
                    "method": self.selection_method,
                    "input_dmps": len(data.positions),
                    "selected_dmps": len(results),
                    "selection_rate": len(results) / len(data.positions) if len(data.positions) > 0 else 0,
                    "thresholds": {
                        "min_overlap": self.min_overlap,
                        "min_delta_mean": self.min_Δμ,
                        "min_jeffreys_divergence": self.min_JD,
                        "min_cohen_d": self.min_cohen_d,
                        "min_auc": self.min_auc,
                        "max_selected_dmps": self.max_selected_dmps
                    }
                }
                self.save_results(results, statistics, export_prefix, export_dir)
            except Exception as e:
                logger.warning(f"Failed to export filtering results: {e}")
        
        return results

    def _compute_jeffreys_divergence(self, a1: np.ndarray, b1: np.ndarray, a2: np.ndarray, b2: np.ndarray, use_gpu: bool = False) -> np.ndarray:
        """Compute Jeffreys divergence between two Beta distributions."""
        if use_gpu and GPU_AVAILABLE and cupy_special_available:
            from cupyx.scipy.special import digamma as cupy_digamma, betaln as cupy_betaln
            xdigamma = cupy_digamma
            xbetaln = cupy_betaln
        else:
            xdigamma = digamma
            xbetaln = betaln
        kl12 = (a1 - a2) * (xdigamma(a1) - xdigamma(a1 + b1)) + (b1 - b2) * (xdigamma(b1) - xdigamma(a1 + b1)) + xbetaln(a2, b2) - xbetaln(a1, b1)
        kl21 = (a2 - a1) * (xdigamma(a2) - xdigamma(a2 + b2)) + (b2 - b1) * (xdigamma(b2) - xdigamma(a2 + b2)) + xbetaln(a1, b1) - xbetaln(a2, b2)
        jd = kl12 + kl21
        return jd

    def _compute_distribution_overlap(self, a1: np.ndarray, b1: np.ndarray, a2: np.ndarray, b2: np.ndarray, use_gpu: bool = False) -> np.ndarray:
        """Compute distribution overlap between two Beta distributions."""
        jsd_metric = self.compute_jensen_shannon_divergence(a1, b1, a2, b2, use_gpu)
        if use_gpu and GPU_AVAILABLE:
            xp = cp
        else:
            xp = np
        overlap = 1.0 - jsd_metric  # Simpler mapping, since jsd_metric is in [0, 1]
        return xp.clip(overlap, 0.0, 1.0)

    def _approx_overlap_fast(self, a1: np.ndarray, b1: np.ndarray, a2: np.ndarray, b2: np.ndarray, use_gpu: bool) -> np.ndarray:
        """Approximate distribution overlap using Jeffreys divergence for fast ranking."""
        jd = self._compute_jeffreys_divergence(a1, b1, a2, b2, use_gpu)
        return np.exp(-jd / 2)  # Approximation based on divergence

    def _compute_cohen_d(self, mean1: np.ndarray, mean2: np.ndarray, var1: Optional[np.ndarray], var2: Optional[np.ndarray], use_gpu: bool = False) -> np.ndarray:
        """Compute Cohen's d effect size."""
        if var1 is None or var2 is None:
            return np.zeros_like(mean1, dtype=np.float32)
        if use_gpu and GPU_AVAILABLE:
            xp = cp
        else:
            xp = np
        # Clip variances to prevent overflow when summing
        max_reasonable_var = 1e12
        var1 = xp.clip(var1, 1e-10, max_reasonable_var)
        var2 = xp.clip(var2, 1e-10, max_reasonable_var)

        pooled_var = (var1 + var2) / 2
        # Ensure pooled_var is positive and not too small to avoid sqrt issues
        pooled_var = xp.maximum(pooled_var, 1e-10)
        cohen_d = xp.abs(mean1 - mean2) / xp.sqrt(pooled_var)
        return cohen_d

    def _single_dmp_auc(self, a1: float, b1: float, a2: float, b2: float, use_gpu: bool) -> float:
        """Compute AUC for a single DMP using LLR moments."""
        mu1, var1 = compute_beta_llr_moments(np.array([a1]), np.array([b1]), np.array([a1-a2]), np.array([b1-b2]), use_gpu)
        mu2, var2 = compute_beta_llr_moments(np.array([a2]), np.array([b2]), np.array([a1-a2]), np.array([b1-b2]), use_gpu)
        d = abs(mu1 - mu2) / np.sqrt(var1 + var2 + 1e-10)
        return float(norm.cdf(d))

    def _compute_separation_stat(self, results: List[DMPFilterResult], use_gpu: bool) -> np.ndarray:
        """Compute (μ_d - μ_h)^2 / (σ_d^2 + σ_h^2) for ranking DMPs based on analytical separation."""
        a1 = np.array([r.alpha1 for r in results])
        b1 = np.array([r.beta1 for r in results])
        a2 = np.array([r.alpha2 for r in results])
        b2 = np.array([r.beta2 for r in results])
        directions = np.array([r.direction for r in results])
        # Flip for hypo
        mask_flip = directions == -1
        a1_flip = np.where(mask_flip, a2, a1)
        b1_flip = np.where(mask_flip, b2, b1)
        a2_flip = np.where(mask_flip, a1, a2)
        b2_flip = np.where(mask_flip, b1, b2)
        mu_d, var_d = compute_beta_llr_moments(a1_flip, b1_flip, a1-a2, b1-b2, use_gpu)
        mu_h, var_h = compute_beta_llr_moments(a2_flip, b2_flip, a1-a2, b1-b2, use_gpu)

        # Clip variances to prevent overflow when summing
        max_reasonable_var = 1e12
        var_d = np.clip(var_d, 1e-10, max_reasonable_var)
        var_h = np.clip(var_h, 1e-10, max_reasonable_var)

        d2 = (mu_d - mu_h)**2 / (var_d + var_h + 1e-10)  # Avoid division by zero
        return d2

    def _compute_bhattacharyya_coeff(self, a1: np.ndarray, b1: np.ndarray, a2: np.ndarray, b2: np.ndarray, use_gpu: bool) -> np.ndarray:
        """Compute Bhattacharyya coefficient for Beta distributions."""
        if use_gpu and GPU_AVAILABLE:
            import cupyx.scipy.special
            xp = cp
            xbetaln = cupyx.scipy.special.betaln
        else:
            xp = np
            xbetaln = betaln
        bc = xp.exp(xbetaln((a1 + a2)/2, (b1 + b2)/2) - 0.5 * (xbetaln(a1, b1) + xbetaln(a2, b2)))
        return bc

    def refine_directional_auc(self, results: List['DMPFilterResult'], top_k: int = 50000) -> List['DMPFilterResult']:
        """Compute signed AUC and composite weight for DMPs."""
        gamma = self.gamma
        for i, r in enumerate(results):
            if all(v is not None for v in (r.alpha1, r.beta1, r.alpha2, r.beta2)):
                auc = self._single_dmp_auc(r.alpha1, r.beta1, r.alpha2, r.beta2, self.use_gpu)
                r.signed_auc = 2.0 * auc - 1.0 if auc is not None else 0.0
                r.direction = 1 if r.signed_auc > 0 else (-1 if r.signed_auc < 0 else 0)
                jsd_metric = r.JD if r.JD is not None else 0.0
                r.w = float(jsd_metric * (abs(r.signed_auc) ** float(gamma)))
            else:
                r.signed_auc = 0.0
                r.direction = 0
                r.w = 0.0
        return results

    def save_results(self, results: List[DMPFilterResult], statistics: Dict[str, Union[str, int, float, bool, Dict[str, Union[str, int, float]]]], output_prefix: str, output_dir: Path) -> Dict[str, Path]:
        """Save filtered DMP results to files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_files = {}
        
        # Save filtered DMPs as CSV
        if results:
            csv_file = output_dir / f"{output_prefix}_filtered_dmps.csv"
            data = []
            for r in results:
                if r.selected:
                    data.append({
                        'position': r.position,
                        'p_value': r.p_value,
                        'q_value': r.q_value,
                        'Δμ': r.Δμ,
                        'distribution_overlap': r.distribution_overlap,
                        'JD': r.JD,
                        'cohen_d': r.cohen_d,
                        'auc_score': r.auc_score,
                        'mean1': r.mean1,
                        'mean2': r.mean2,
                        'alpha1': r.alpha1,
                        'beta1': r.beta1,
                        'alpha2': r.alpha2,
                        'beta2': r.beta2,
                        'selection_reason': r.selection_reason
                    })
            df = pd.DataFrame(data)
            df.to_csv(csv_file, index=False)
            saved_files['filtered_dmps_csv'] = csv_file
        
        # Save filtering statistics
        stats_file = output_dir / f"{output_prefix}_filtering_stats.json"
        import json
        with open(stats_file, 'w') as f:
            json.dump(statistics, f, indent=2, default=str)
        saved_files['filtering_stats'] = stats_file
        
        # Save summary report
        summary_file = output_dir / f"{output_prefix}_filtering_summary.txt"
        with open(summary_file, 'w') as f:
            f.write("MethylDetector DMP Filtering Summary\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Selection Method: {statistics['method']}\n")
            f.write(f"Input DMPs: {statistics['input_dmps']}\n")
            f.write(f"Selected DMPs: {statistics['selected_dmps']}\n")
            f.write(f"Selection Rate: {statistics['selection_rate']:.1%}\n\n")
            f.write("Thresholds Used:\n")
            for key, value in statistics['thresholds'].items():
                f.write(f"  {key}: {value}\n")
            if 'metrics' in statistics:
                f.write("\nSelected DMP Metrics:\n")
                for key, value in statistics['metrics'].items():
                    f.write(f"  {key}: {value:.4f}\n")
        saved_files['filtering_summary'] = summary_file
        
        logger.info(f"Filtered DMP results saved to {output_dir}")
        return saved_files

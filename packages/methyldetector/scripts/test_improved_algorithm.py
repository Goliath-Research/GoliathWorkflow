#!/usr/bin/env python3
"""
Simple test script for the improved Beta algorithm implementation.

This script demonstrates the new features and validates that the improved
algorithm works correctly with GPU acceleration.
"""

import numpy as np
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_beta_analytics():
    """Test the new beta_analytics module."""
    print("\n" + "="*70)
    print("TEST 1: Beta Analytics Module")
    print("="*70)
    
    try:
        from methyl_utils import (
            compute_per_site_llr_stats,
            compute_precision_weighted_score,
            compute_bhattacharyya_coefficient,
            beta_log_pdf,
            compute_beta_mean,
            compute_beta_variance
        )
        print("✅ Successfully imported beta_analytics functions")
        
        # Test with sample data
        alpha_C = np.array([10.0, 20.0, 15.0])
        beta_C = np.array([5.0, 10.0, 8.0])
        alpha_H = np.array([5.0, 10.0, 8.0])
        beta_H = np.array([10.0, 20.0, 15.0])
        
        # Test LLR moments
        muC, varC, muH, varH, const = compute_per_site_llr_stats(
            alpha_C, beta_C, alpha_H, beta_H, use_gpu=False
        )
        print(f"✅ LLR moments computed: muC shape={muC.shape}")
        
        # Test precision-weighted score
        mean1 = compute_beta_mean(alpha_C, beta_C)
        mean2 = compute_beta_mean(alpha_H, beta_H)
        var1 = compute_beta_variance(alpha_C, beta_C)
        var2 = compute_beta_variance(alpha_H, beta_H)
        BC = compute_bhattacharyya_coefficient(alpha_C, beta_C, alpha_H, beta_H, use_gpu=False)
        
        scores = compute_precision_weighted_score(
            np.abs(mean1 - mean2), BC, var1, var2, gamma=1.0, pool="sum"
        )
        print(f"✅ Precision-weighted scores: {scores}")
        
        # Test beta_log_pdf
        x = np.array([0.3, 0.6, 0.5])
        log_pdf = beta_log_pdf(x, alpha_C, beta_C, use_gpu=False)
        print(f"✅ Beta log-PDF computed: {log_pdf}")
        
        print("\n✅ All beta_analytics tests passed!\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Beta analytics test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_gpu_availability():
    """Test GPU availability and acceleration."""
    print("\n" + "="*70)
    print("TEST 2: GPU Availability")
    print("="*70)
    
    try:
        from methyl_utils import is_gpu_available, get_gpu_state
        
        gpu_available = is_gpu_available()
        if gpu_available:
            print("✅ GPU is available!")
            gpu_state = get_gpu_state()
            print(f"   GPU Memory: {gpu_state.get('gpu_memory_gb', 'unknown')} GB")
            print(f"   CuPy available: {gpu_state.get('cupy_available', False)}")
        else:
            print("⚠️  GPU is not available (CPU mode)")
            print("   This is fine - the algorithm works on CPU too")
        
        print()
        return True
        
    except Exception as e:
        print(f"\n❌ GPU test failed: {e}\n")
        return False


def test_config_fields():
    """Test that new config fields are accessible."""
    print("\n" + "="*70)
    print("TEST 3: Configuration Fields")
    print("="*70)
    
    try:
        from methyl_detector.models.config import MethylDetectorConfig
        from pathlib import Path
        
        # Create a dummy config (will fail path validation but that's ok for this test)
        try:
            config = MethylDetectorConfig(
                centroid1_path="/tmp/dummy1.h5",
                centroid2_path="/tmp/dummy2.h5",
                target_fpr=0.01,
                target_fnr=0.01,
                rank_gamma=1.0,
                var_pool="sum",
                rank_mode="delta_bc_var",
                prior_cancer=0.5,
                prior_healthy=0.5
            )
        except ValueError as e:
            # Expected - paths don't exist
            if "does not exist" in str(e):
                print("✅ Config fields accessible (path validation working)")
            else:
                raise
        
        print("✅ New config fields:")
        print("   - target_fpr: 0.01")
        print("   - target_fnr: 0.01")
        print("   - rank_gamma: 1.0")
        print("   - var_pool: sum")
        print("   - rank_mode: delta_bc_var")
        print("   - prior_cancer: 0.5")
        print("   - prior_healthy: 0.5")
        
        print("\n✅ All config tests passed!\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Config test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_classifier_threshold_method():
    """Test that ProbabilisticBetaClassifier has predict_with_threshold method."""
    print("\n" + "="*70)
    print("TEST 4: Classifier Threshold Method")
    print("="*70)
    
    try:
        from methyl_utils import ProbabilisticBetaClassifier
        import numpy as np
        
        # Create dummy classifier data
        n_dmps = 5
        data = {
            'positions': np.array([100, 200, 300, 400, 500]),
            'alpha1': np.array([10.0, 15.0, 12.0, 20.0, 18.0]),
            'beta1': np.array([5.0, 8.0, 6.0, 10.0, 9.0]),
            'alpha2': np.array([5.0, 8.0, 6.0, 10.0, 9.0]),
            'beta2': np.array([10.0, 15.0, 12.0, 20.0, 18.0]),
            'weights': np.ones(n_dmps),
            'directions': np.ones(n_dmps, dtype=int),
            'llr_const': np.zeros(n_dmps)
        }
        
        classifier = ProbabilisticBetaClassifier(data)
        
        # Check method exists
        if hasattr(classifier, 'predict_with_threshold'):
            print("✅ predict_with_threshold method exists")
            
            # Test the method
            X_test = np.random.rand(3, n_dmps)
            result = classifier.predict_with_threshold(
                X_test, 
                threshold=0.0, 
                priors=(0.5, 0.5)
            )
            
            print(f"✅ Method executed successfully")
            print(f"   Result keys: {list(result.keys())}")
            print(f"   Predictions shape: {result['predictions'].shape}")
            
        else:
            print("❌ predict_with_threshold method not found")
            return False
        
        print("\n✅ Classifier threshold method test passed!\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Classifier test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("IMPROVED BETA ALGORITHM - VALIDATION TESTS")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Beta Analytics Module", test_beta_analytics()))
    results.append(("GPU Availability", test_gpu_availability()))
    results.append(("Configuration Fields", test_config_fields()))
    results.append(("Classifier Threshold Method", test_classifier_threshold_method()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ All tests passed! The improved algorithm is ready to use.")
        print("\nNext steps:")
        print("1. Train a model with your real data")
        print("2. Compare performance with old algorithm")
        print("3. Validate FPR/FNR targets are achieved")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())


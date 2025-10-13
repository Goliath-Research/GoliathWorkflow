#!/usr/bin/env python3
"""
Test script to verify that required MethylUtils statistical functions are implemented.

Run this script to check if MethylUtils provides all the functions required by MethylDetector.
"""

def test_methylutils_functions():
    """Test that all required statistical functions are available in MethylUtils."""
    print("Testing MethylUtils statistical functions...")

    try:
        import methyl_utils
        print("✓ MethylUtils imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import MethylUtils: {e}")
        return False

    required_functions = [
        'compute_beta_llr_moments',
        'compute_distribution_overlap',
        'compute_jeffreys_divergence'
    ]

    missing_functions = []
    for func_name in required_functions:
        if hasattr(methyl_utils, func_name):
            print(f"✓ {func_name} is available")
        else:
            print(f"✗ {func_name} is missing")
            missing_functions.append(func_name)

    if missing_functions:
        print(f"\n❌ The following functions are missing from MethylUtils: {missing_functions}")
        print("Please implement these functions in MethylUtils before using MethylDetector.")
        return False
    else:
        print("\n✅ All required functions are available in MethylUtils!")
        return True

def test_function_signatures():
    """Test that the functions have the expected signatures."""
    import methyl_utils
    import numpy as np

    print("\nTesting function signatures...")

    try:
        # Test compute_beta_llr_moments
        func = methyl_utils.compute_beta_llr_moments
        result = func(np.array([1.0]), np.array([2.0]), np.array([0.5]), np.array([0.3]), use_gpu=False)
        if len(result) == 2:
            print("✓ compute_beta_llr_moments signature looks correct")
        else:
            print("✗ compute_beta_llr_moments returned unexpected result format")
    except Exception as e:
        print(f"✗ compute_beta_llr_moments test failed: {e}")

    try:
        # Test compute_distribution_overlap
        func = methyl_utils.compute_distribution_overlap
        result = func(np.array([1.0]), np.array([2.0]), np.array([1.5]), np.array([2.5]), use_gpu=False)
        print("✓ compute_distribution_overlap signature looks correct")
    except Exception as e:
        print(f"✗ compute_distribution_overlap test failed: {e}")

    try:
        # Test compute_jeffreys_divergence
        func = methyl_utils.compute_jeffreys_divergence
        result = func(np.array([1.0]), np.array([2.0]), np.array([1.5]), np.array([2.5]), use_gpu=False)
        print("✓ compute_jeffreys_divergence signature looks correct")
    except Exception as e:
        print(f"✗ compute_jeffreys_divergence test failed: {e}")

if __name__ == "__main__":
    success = test_methylutils_functions()
    if success:
        test_function_signatures()
    print("\n" + "="*50)
    if success:
        print("🎉 MethylUtils is ready for MethylDetector!")
    else:
        print("❌ MethylUtils needs to be updated before using MethylDetector.")

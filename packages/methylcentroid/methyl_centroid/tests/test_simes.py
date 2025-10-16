#!/usr/bin/env python3

import math

def calculate_simes_p_value(p_values):
    """
    Calculate the combined p-value using the General Simes formula.

    The Simes test combines multiple p-values by taking:
    p_simes = min_{i=1 to k} (k * p_{(i)} / i)

    where p_{(i)} is the i-th smallest p-value in the set of k p-values.

    Args:
        p_values: List of p-values to combine

    Returns:
        Combined p-value using Simes method
    """
    if not p_values:
        return 1.0

    # Remove any NaN or invalid p-values
    valid_p_values = [p for p in p_values if isinstance(p, (int, float)) and not math.isnan(p) and 0 <= p <= 1]

    if not valid_p_values:
        return 1.0

    k = len(valid_p_values)
    if k == 1:
        return valid_p_values[0]

    # Sort p-values in ascending order (p_{(1)} <= p_{(2)} <= ... <= p_{(k)})
    sorted_p_values = sorted(valid_p_values)

    # Calculate Simes combined p-value: min_{i=1 to k} (k * p_{(i)} / i)
    simes_values = [k * sorted_p_values[i] / (i + 1) for i in range(k)]
    p_simes = min(simes_values)

    # Ensure the result is bounded [0, 1]
    return min(max(p_simes, 0.0), 1.0)

def test_simes():
    # Test cases
    test_cases = [
        # Single p-value
        ([0.01], 0.01),
        # Two p-values
        ([0.01, 0.02], min(2*0.01/1, 2*0.02/2)),  # Should be min(0.02, 0.02) = 0.02
        # Three p-values - example from literature
        ([0.01, 0.03, 0.05], min(3*0.01/1, 3*0.03/2, 3*0.05/3)),  # Should be min(0.03, 0.045, 0.05) = 0.03
        # All large p-values
        ([0.5, 0.6, 0.7], min(3*0.5/1, 3*0.6/2, 3*0.7/3)),  # Should be min(1.5, 0.9, 0.7) = 0.7
        # Edge case: very small p-values
        ([0.001, 0.002, 0.003], min(3*0.001/1, 3*0.002/2, 3*0.003/3)),  # Should be min(0.003, 0.003, 0.003) = 0.003
    ]

    print("Testing Simes p-value calculation:")
    print("=" * 50)

    for i, (p_values, expected) in enumerate(test_cases):
        result = calculate_simes_p_value(p_values)
        print(f"Test {i+1}: p_values={p_values}")
        print(f"  Expected: {expected:.6f}")
        print(f"  Got:      {result:.6f}")

        # Calculate the individual Simes components for clarity
        k = len(p_values)
        sorted_p = sorted(p_values)
        components = [k * sorted_p[j] / (j + 1) for j in range(k)]
        print(f"  Components: {[f'{c:.6f}' for c in components]}")
        print(f"  Min component: {min(components):.6f}")

        if abs(result - expected) < 1e-6:
            print("  ✓ PASS")
        else:
            print("  ✗ FAIL")
        print()

if __name__ == "__main__":
    test_simes()

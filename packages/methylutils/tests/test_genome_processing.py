#!/usr/bin/env python3
"""
Genome Processing Test Suite
============================

Comprehensive test suite for MethylUtils genome-scale processing capabilities.
Tests GPU acceleration, memory management, chunk processing, and performance.
"""

import pytest
import numpy as np
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

# Import MethylUtils components
try:
    import methyl_utils
    from methyl_utils import (
        PositionAligner, get_memory_manager, get_performance_profiler,
        get_monitor, DistanceCalculator, MethylSample
    )
    from methyl_utils.gpu_detection import is_gpu_available
    from methyl_utils.memory_manager import MemoryManager
    METHYLUTILS_AVAILABLE = True
except ImportError as e:
    METHYLUTILS_AVAILABLE = False
    pytest.skip(f"MethylUtils not available: {e}", allow_module_level=True)


class TestGenomeProcessing:
    """Test suite for genome-scale processing functionality."""

    @pytest.fixture
    def sample_genome_data(self):
        """Create sample genome methylation data for testing."""
        np.random.seed(42)  # For reproducible tests

        # Create sample data: 1M positions with methylation data
        n_positions = 1_000_000

        data = {
            'positions': np.arange(n_positions, dtype=np.uint32),
            'methylated': np.random.randint(0, 1000, n_positions, dtype=np.uint32),
            'unmethylated': np.random.randint(0, 1000, n_positions, dtype=np.uint32),
            'total': np.random.randint(1, 2000, n_positions, dtype=np.uint8)
        }

        return data

    @pytest.fixture
    def memory_manager(self):
        """Get memory manager instance."""
        return get_memory_manager()

    @pytest.fixture
    def performance_profiler(self):
        """Get performance profiler instance."""
        return get_performance_profiler()

    @pytest.fixture
    def monitor(self):
        """Get monitoring instance."""
        return get_monitor()

    def test_gpu_availability(self):
        """Test GPU detection and availability."""
        gpu_available = is_gpu_available()

        if gpu_available:
            # If GPU is available, test basic GPU functionality
            from methyl_utils.gpu_detection import get_gpu_info
            gpu_info = get_gpu_info()

            assert gpu_info is not None
            assert 'memory_total' in gpu_info
            assert gpu_info['memory_total'] > 0
        else:
            # GPU not available - this is acceptable for CI/testing
            pytest.skip("GPU not available for testing")

    def test_memory_manager_initialization(self, memory_manager):
        """Test memory manager initialization and basic functionality."""
        assert memory_manager is not None

        # Test memory usage retrieval
        usage = memory_manager.get_memory_usage()
        assert 'system_memory_gb' in usage
        assert 'gpu_memory_gb' in usage
        assert usage['system_memory_gb'] > 0

    def test_chunk_size_calculation(self, memory_manager, sample_genome_data):
        """Test optimal chunk size calculation for genome data."""
        total_positions = len(sample_genome_data['positions'])

        # Test chunk size calculation
        chunk_size = memory_manager.calculate_optimal_chunk_size(
            total_positions=total_positions,
            data_structure="centroid",
            maximize_gpu_usage=True
        )

        # Chunk size should be reasonable
        assert chunk_size > 0
        assert chunk_size <= total_positions
        assert chunk_size >= 10_000_000  # Minimum for GPU efficiency

        # Test different data structures
        for data_structure in ["basic_sample", "centroid"]:
            chunk_size = memory_manager.calculate_optimal_chunk_size(
                total_positions=total_positions,
                data_structure=data_structure
            )
            assert chunk_size > 0

    def test_memory_cleanup_operations(self, memory_manager):
        """Test GPU memory cleanup operations."""
        if not is_gpu_available():
            pytest.skip("GPU not available for memory cleanup testing")

        # Test cleanup operations don't raise exceptions
        memory_manager.force_gpu_cleanup()
        memory_manager.cleanup_gpu_after_operation("test_cleanup")

        # Test memory threshold monitoring
        threshold_reached = memory_manager.monitor_gpu_memory_threshold(50.0)
        assert isinstance(threshold_reached, bool)

    def test_distance_calculations(self, sample_genome_data):
        """Test statistical distance calculations."""
        calculator = DistanceCalculator()

        # Create sample beta parameters
        n_samples = 1000
        alpha1 = np.random.beta(2, 5, n_samples)
        beta1 = np.random.beta(3, 4, n_samples)
        alpha2 = np.random.beta(2.5, 4.5, n_samples)
        beta2 = np.random.beta(3.5, 3.5, n_samples)

        # Test different distance metrics
        metrics = ['kl_divergence', 'jeffreys', 'bhattacharyya_distance',
                  'hellinger_distance', 'wasserstein_distance', 'jensen_shannon_distance']

        for metric in metrics:
            start_time = time.time()

            if metric == 'jensen_shannon_distance':
                # Test weighted version too
                distances = calculator.compute_distance(alpha1, beta1, alpha2, beta2, metric)
                weighted_distances = calculator.compute_weighted_jensen_shannon_distance(
                    alpha1, beta1, alpha2, beta2, alpha1  # Using alpha1 as weights
                )
                assert len(weighted_distances) == n_samples
            else:
                distances = calculator.compute_distance(alpha1, beta1, alpha2, beta2, metric)

            assert len(distances) == n_samples
            assert np.all(distances >= 0)  # Distances should be non-negative

            duration = time.time() - start_time
            print(".4f")

    def test_performance_profiling(self, performance_profiler, sample_genome_data):
        """Test performance profiling functionality."""
        # Start profiling
        performance_profiler.start_monitoring()

        # Simulate some work
        start_time = time.time()

        # Simple computation to profile
        data = sample_genome_data['positions'][:100000]
        result = np.sum(data ** 2)

        duration = time.time() - start_time

        # Stop profiling
        performance_profiler.stop_monitoring()

        # Get performance report
        report = performance_profiler.get_performance_report()

        assert 'cpu_usage' in report
        assert 'memory_usage' in report
        assert isinstance(report, dict)

    def test_monitoring_system(self, monitor, sample_genome_data):
        """Test monitoring system functionality."""
        # Start monitoring
        monitor.start_monitoring()

        try:
            # Record some test operations
            monitor.start_operation("test_distance_calculation")

            # Simulate work
            time.sleep(0.01)
            positions_processed = len(sample_genome_data['positions'])

            monitor.end_operation("test_distance_calculation", 0.01, "success")
            monitor.record_positions_processed(positions_processed)
            monitor.record_chunk_processing(0.01)

            # Check health status
            health_status = monitor.get_health_status()
            assert 'status' in health_status
            assert 'health_score' in health_status
            assert health_status['status'] in ['healthy', 'degraded']

            # Check metrics export
            metrics_text = monitor.get_metrics_text()
            assert isinstance(metrics_text, str)

        finally:
            # Stop monitoring
            monitor.stop_monitoring()

    def test_methyl_sample_creation(self, sample_genome_data):
        """Test MethylSample data structure creation and operations."""
        # Create MethylSample from test data
        sample = MethylSample(
            positions=sample_genome_data['positions'],
            mC=sample_genome_data['methylated'],
            uC=sample_genome_data['unmethylated'],
            tnc=sample_genome_data['total']
        )

        assert len(sample) == len(sample_genome_data['positions'])
        assert sample.positions.dtype == np.uint32
        assert sample.mC.dtype == np.uint32
        assert sample.uC.dtype == np.uint32
        assert sample.tnc.dtype == np.uint8

        # Test methylation level calculation
        methylation_levels = sample.calculate_methylation_levels()
        assert len(methylation_levels) == len(sample)
        assert np.all(methylation_levels >= 0)
        assert np.all(methylation_levels <= 1)

    @pytest.mark.parametrize("chunk_size", [100000, 500000, 1000000])
    def test_chunk_processing(self, memory_manager, sample_genome_data, chunk_size):
        """Test chunk-based processing of genome data."""
        positions = sample_genome_data['positions']
        total_positions = len(positions)

        chunks_processed = 0
        total_processed = 0

        # Process data in chunks
        for start_idx in range(0, total_positions, chunk_size):
            end_idx = min(start_idx + chunk_size, total_positions)

            # Extract chunk
            chunk_positions = positions[start_idx:end_idx]
            chunk_size_actual = len(chunk_positions)

            # Simulate processing
            with memory_manager.gpu_operation_context(f"chunk_{chunks_processed}"):
                # Simulate GPU work
                time.sleep(0.001)  # Minimal delay for testing

                # Verify chunk integrity
                assert len(chunk_positions) > 0
                assert len(chunk_positions) <= chunk_size
                assert chunk_positions[0] == start_idx

            total_processed += chunk_size_actual
            chunks_processed += 1

        assert total_processed == total_positions
        assert chunks_processed == (total_positions + chunk_size - 1) // chunk_size

    def test_memory_threshold_monitoring(self, memory_manager):
        """Test memory threshold monitoring and cleanup."""
        if not is_gpu_available():
            pytest.skip("GPU not available for memory threshold testing")

        # Test threshold monitoring at different levels
        for threshold in [10, 50, 90]:
            reached = memory_manager.monitor_gpu_memory_threshold(threshold)
            assert isinstance(reached, bool)

        # Test cleanup operations
        memory_manager.force_gpu_cleanup()
        memory_manager.cleanup_gpu_after_operation("threshold_test")

    def test_error_handling_and_recovery(self, memory_manager, monitor):
        """Test error handling and recovery mechanisms."""
        # Test with invalid inputs
        with pytest.raises(ValueError):
            memory_manager.calculate_optimal_chunk_size(
                total_positions=-1,
                data_structure="invalid_structure"
            )

        # Test monitoring error recovery
        monitor.record_operation("test_error", 0.1, "error")
        monitor.errors_total.labels(error_type='test_error').inc()

        # Verify system remains functional after errors
        health_status = monitor.get_health_status()
        assert 'status' in health_status

    @pytest.mark.benchmark
    def test_performance_benchmarks(self, benchmark, sample_genome_data):
        """Performance benchmarks for critical operations."""
        data = sample_genome_data['positions'][:100000]

        # Benchmark distance calculation
        def benchmark_distance_calculation():
            calculator = DistanceCalculator()
            alpha1 = np.random.beta(2, 5, 1000)
            beta1 = np.random.beta(3, 4, 1000)
            alpha2 = np.random.beta(2.5, 4.5, 1000)
            beta2 = np.random.beta(3.5, 3.5, 1000)

            return calculator.compute_distance(
                alpha1, beta1, alpha2, beta2, 'jensen_shannon_distance'
            )

        result = benchmark(benchmark_distance_calculation)
        assert len(result) == 1000

    def test_integration_workflow(self, sample_genome_data, memory_manager, monitor):
        """Test complete integration workflow from data to results."""
        monitor.start_monitoring()

        try:
            # 1. Create sample data
            sample = MethylSample(
                positions=sample_genome_data['positions'][:100000],
                mC=sample_genome_data['methylated'][:100000],
                uC=sample_genome_data['unmethylated'][:100000],
                tnc=sample_genome_data['total'][:100000]
            )

            # 2. Calculate optimal chunk size
            chunk_size = memory_manager.calculate_optimal_chunk_size(
                total_positions=len(sample),
                data_structure="centroid"
            )

            # 3. Process in chunks
            results = []
            for i in range(0, len(sample), chunk_size):
                chunk_end = min(i + chunk_size, len(sample))

                with memory_manager.gpu_operation_context(f"integration_chunk_{i//chunk_size}"):
                    monitor.start_operation("methylation_analysis")

                    # Simulate analysis
                    chunk_data = sample[i:chunk_end]
                    methylation_levels = chunk_data.calculate_methylation_levels()

                    monitor.end_operation("methylation_analysis", 0.01, "success")
                    monitor.record_positions_processed(len(chunk_data))

                    results.append(np.mean(methylation_levels))

            # 4. Verify results
            assert len(results) > 0
            assert all(isinstance(r, (int, float)) for r in results)

            # 5. Check monitoring data
            health_status = monitor.get_health_status()
            assert health_status['status'] in ['healthy', 'degraded']

        finally:
            monitor.stop_monitoring()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])

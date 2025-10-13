"""
Centralized GPU detection and management module.

This module provides a single source of truth for GPU availability and capabilities
across the entire application ecosystem. Uses nvidia-ml-py as the primary detection method
(NVIDIA's official NVML Python bindings).
"""

import logging
import time
import warnings
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Initialize logger
logger = logging.getLogger(__name__)

# Global GPU state
_GPU_STATE: Optional[Dict[str, Any]] = None
_GPU_INITIALIZED: bool = False

def _initialize_gpu_state() -> Dict[str, Any]:
    """
    Initialize and test GPU capabilities using nvidia-ml-py as primary method.

    Returns:
        Dictionary containing GPU state information
    """
    global _GPU_STATE, _GPU_INITIALIZED
    
    if _GPU_INITIALIZED:
        return _GPU_STATE
    
    gpu_state = {
        'available': False,
        'cupy_available': False,
        'cudf_available': False,
        'cupyx_scipy_available': False,
        'cupyx_scipy_integrate_available': False,
        'cupyx_scipy_special_available': False,
        'cupyx_scipy_stats_available': False,
        'pynvml_available': False,
        'memory_gb': 0.0,
        'device_count': 0,
        'gpu_name': None,
        'cuda_version': None,
        'compute_capability': None,
        'error_message': None
    }
    
    # Primary detection pynvml
    try:
        import pynvml as nvml
        nvml.nvmlInit()
        gpu_state['pynvml_available'] = True
        gpu_state['available'] = True

        device_count = nvml.nvmlDeviceGetCount()
        gpu_state['device_count'] = device_count

        if device_count > 0:
            # Get detailed GPU information
            handle = nvml.nvmlDeviceGetHandleByIndex(0)

            # GPU name
            gpu_name_raw = nvml.nvmlDeviceGetName(handle)
            gpu_state['gpu_name'] = gpu_name_raw.decode('utf-8') if isinstance(gpu_name_raw, bytes) else gpu_name_raw

            # Memory info
            mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_state['memory_gb'] = mem_info.total / (1024**3)

            # CUDA version
            try:
                driver_version_raw = nvml.nvmlSystemGetDriverVersion()
                gpu_state['cuda_version'] = driver_version_raw.decode('utf-8') if isinstance(driver_version_raw, bytes) else str(driver_version_raw)
            except:
                gpu_state['cuda_version'] = "Unknown"

            # Compute capability
            try:
                major, minor = nvml.nvmlDeviceGetCudaComputeCapability(handle)
                gpu_state['compute_capability'] = f"{major}.{minor}"
            except:
                gpu_state['compute_capability'] = "Unknown"

            logger.info(f"GPU detected via nvidia-ml-py: {gpu_state['gpu_name']}")
            logger.info(f"GPU memory: {gpu_state['memory_gb']:.1f} GB")
            logger.info(f"CUDA version: {gpu_state['cuda_version']}")
            logger.info(f"Compute capability: {gpu_state['compute_capability']}")

    except ImportError:
        logger.debug("nvidia-ml-py not available, falling back to CuPy detection")
    except Exception as e:
        logger.warning(f"nvidia-ml-py initialization failed: {e}")
        gpu_state['error_message'] = f"nvidia-ml-py failed: {e}"
    
    # Test CuPy availability and functionality
    try:
        import cupy as cp
        gpu_state['cupy_available'] = True
        
        # Test if GPU is actually available and functional
        if cp.is_available():
            gpu_state['available'] = True
            
            # If we don't have pynvml info, get basic info from CuPy
            if not gpu_state['pynvml_available']:
                try:
                    gpu_state['device_count'] = cp.cuda.runtime.getDeviceCount()
                    gpu_state['gpu_name'] = cp.cuda.runtime.getDeviceProperties(0)['name'].decode()
                    gpu_state['memory_gb'] = cp.cuda.runtime.memGetInfo()[1] / (1024**3)
                    gpu_state['cuda_version'] = str(cp.cuda.runtime.driverGetVersion())
                except:
                    gpu_state['gpu_name'] = "Unknown GPU"
                    gpu_state['memory_gb'] = 0.0
                    gpu_state['cuda_version'] = "Unknown"
            
            # Test basic GPU operations
            try:
                test_array = cp.array([1.0, 2.0, 3.0])
                result = cp.sum(test_array)
                del test_array, result
                cp.get_default_memory_pool().free_all_blocks()
                logger.info("GPU functionality test passed")
            except Exception as e:
                gpu_state['available'] = False
                gpu_state['error_message'] = f"GPU test failed: {e}"
                logger.warning(f"GPU test failed: {e}")
        else:
            gpu_state['error_message'] = "CuPy available but no GPU detected"
            logger.debug("CuPy available but no GPU detected")
            
    except ImportError:
        gpu_state['error_message'] = "CuPy not available"
        logger.debug("CuPy not available")
    except Exception as e:
        gpu_state['error_message'] = f"CuPy import failed: {e}"
        logger.warning(f"CuPy import failed: {e}")
    
    # Test cuDF availability
    if gpu_state['cupy_available']:
        try:
            import importlib.util
            if importlib.util.find_spec("cudf") is not None:
                gpu_state['cudf_available'] = True
        except Exception as e:
            logger.warning(f"cuDF availability check failed: {e}")
    
    # Test cupyx.scipy availability
    if gpu_state['cupy_available']:
        try:
            import cupyx.scipy
            gpu_state['cupyx_scipy_available'] = True
            
            # Test specific cupyx.scipy modules
            try:
                import cupyx.scipy.integrate
                if hasattr(cupyx.scipy.integrate, 'quad'):
                    gpu_state['cupyx_scipy_integrate_available'] = True
            except ImportError:
                pass
            
            try:
                import cupyx.scipy.special
                gpu_state['cupyx_scipy_special_available'] = True
            except ImportError:
                pass
            
            try:
                import cupyx.scipy.stats
                gpu_state['cupyx_scipy_stats_available'] = True
            except ImportError:
                pass
                
        except ImportError:
            logger.debug("cupyx.scipy not available")
        except Exception as e:
            logger.warning(f"cupyx.scipy import failed: {e}")
    
    _GPU_STATE = gpu_state
    _GPU_INITIALIZED = True
    
    # Log final state
    if gpu_state['available']:
        logger.info(f"GPU acceleration available: {gpu_state['device_count']} device(s), "
                   f"~{gpu_state['memory_gb']:.1f}GB memory")
    else:
        logger.info("GPU acceleration not available - using CPU-only mode")
        if gpu_state['error_message']:
            logger.debug(f"GPU unavailable reason: {gpu_state['error_message']}")
    
    return gpu_state

def is_gpu_available() -> bool:
    """
    Check if GPU acceleration is available.
    
    Returns:
        True if GPU is available and functional, False otherwise
    """
    state = _initialize_gpu_state()
    return state['available']

def is_cupy_available() -> bool:
    """
    Check if CuPy is available (regardless of GPU).
    
    Returns:
        True if CuPy can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cupy_available']

def is_cudf_available() -> bool:
    """
    Check if cuDF is available.
    
    Returns:
        True if cuDF can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cudf_available']

def is_cupyx_scipy_available() -> bool:
    """
    Check if cupyx.scipy is available.
    
    Returns:
        True if cupyx.scipy can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cupyx_scipy_available']

def is_cupyx_scipy_integrate_available() -> bool:
    """
    Check if cupyx.scipy.integrate is available.
    
    Returns:
        True if cupyx.scipy.integrate can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cupyx_scipy_integrate_available']

def is_cupyx_scipy_special_available() -> bool:
    """
    Check if cupyx.scipy.special is available.
    
    Returns:
        True if cupyx.scipy.special can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cupyx_scipy_special_available']

def is_cupyx_scipy_stats_available() -> bool:
    """
    Check if cupyx.scipy.stats is available.
    
    Returns:
        True if cupyx.scipy.stats can be imported, False otherwise
    """
    state = _initialize_gpu_state()
    return state['cupyx_scipy_stats_available']

def get_gpu_memory_gb() -> float:
    """
    Get available GPU memory in GB.
    
    Returns:
        GPU memory in GB, or 0.0 if not available
    """
    state = _initialize_gpu_state()
    return state['memory_gb']

def get_gpu_device_count() -> int:
    """
    Get number of available GPU devices.
    
    Returns:
        Number of GPU devices, or 0 if not available
    """
    state = _initialize_gpu_state()
    return state['device_count']

def get_gpu_state() -> Dict[str, Any]:
    """
    Get complete GPU state information.
    
    Returns:
        Dictionary containing all GPU state information
    """
    return _initialize_gpu_state().copy()

def get_gpu_error_message() -> Optional[str]:
    """
    Get error message if GPU is not available.
    
    Returns:
        Error message string, or None if GPU is available
    """
    state = _initialize_gpu_state()
    return state['error_message']

def get_cupy():
    """
    Get CuPy module if available.

    Returns:
        CuPy module if available, None otherwise
    """
    if not is_gpu_available():
        return None

    try:
        import cupy as cp
        return cp
    except ImportError:
        return None

def cleanup_gpu_memory() -> bool:
    """
    Clean up GPU memory.
    
    Returns:
        True if cleanup was successful, False otherwise
    """
    if not is_cupy_available():
        return False
    
    try:
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
        cp.get_default_pinned_memory_pool().free_all_blocks()
        logger.debug("GPU memory cleaned up successfully")
        return True
    except Exception as e:
        logger.warning(f"GPU memory cleanup failed: {e}")
        return False

def reset_gpu_state() -> None:
    """
    Reset GPU state (useful for testing or after GPU changes).
    """
    global _GPU_STATE, _GPU_INITIALIZED
    _GPU_STATE = None
    _GPU_INITIALIZED = False
    logger.debug("GPU state reset")

def print_gpu_status() -> None:
    """
    Print detailed GPU status information.
    """
    state = get_gpu_state()
    
    print("=" * 50)
    print("GPU STATUS REPORT")
    print("=" * 50)
    
    if state['available']:
        print(f"✅ GPU Acceleration: ENABLED")
        print(f"   Device: {state['gpu_name']}")
        print(f"   Memory: {state['memory_gb']:.1f} GB")
        print(f"   CUDA Version: {state['cuda_version']}")
        print(f"   Compute Capability: {state['compute_capability']}")
        print(f"   Device Count: {state['device_count']}")
    else:
        print(f"❌ GPU Acceleration: DISABLED")
        if state['error_message']:
            print(f"   Reason: {state['error_message']}")
    
    print(f"\nLibrary Availability:")
    print(f"   CuPy: {'✅' if state['cupy_available'] else '❌'}")
    print(f"   cuDF: {'✅' if state['cudf_available'] else '❌'}")
    print(f"   cupyx.scipy: {'✅' if state['cupyx_scipy_available'] else '❌'}")
    print(f"   pynvml: {'✅' if state['pynvml_available'] else '❌'}")
    
    if state['cupyx_scipy_available']:
        print(f"\nCuPy SciPy Modules:")
        print(f"   integrate: {'✅' if state['cupyx_scipy_integrate_available'] else '❌'}")
        print(f"   special: {'✅' if state['cupyx_scipy_special_available'] else '❌'}")
        print(f"   stats: {'✅' if state['cupyx_scipy_stats_available'] else '❌'}")
    
    print("=" * 50)

def get_gpu_capabilities() -> Dict[str, Any]:
    """
    Get detailed GPU capabilities information.
    
    Returns:
        Dictionary with GPU capabilities
    """
    state = get_gpu_state()
    
    return {
        'nvidia_gpu_available': state['available'],
        'cupy_available': state['cupy_available'],
        'cudf_available': state['cudf_available'],
        'cupyx_scipy_available': state['cupyx_scipy_available'],
        'pynvml_available': state['pynvml_available'],
        'device_count': state['device_count'],
        'memory_gb': state['memory_gb'],
        'gpu_name': state['gpu_name'],
        'cuda_version': state['cuda_version'],
        'compute_capability': state['compute_capability'],
        'error_message': state['error_message']
    }

def create_gpu_array(array: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Create GPU array if possible, otherwise return CPU array.
    
    Args:
        array: Input numpy array
        
    Returns:
        Tuple of (array, is_gpu) where is_gpu indicates if it's on GPU
    """
    if not is_gpu_available():
        return array, False
    
    try:
        cp = get_cupy()
        if cp is not None:
            gpu_array = cp.asarray(array)
            return gpu_array, True
    except Exception as e:
        logger.warning(f"Failed to create GPU array: {e}")
    
    return array, False

def to_cpu_array(array) -> np.ndarray:
    """
    Convert array to CPU numpy array.
    
    Args:
        array: Input array (numpy or CuPy)
        
    Returns:
        CPU numpy array
    """
    if hasattr(array, 'get'):  # CuPy array
        return array.get()
    return np.asarray(array)

def get_memory_info() -> Dict[str, int]:
    """
    Get current GPU memory usage information.
    
    Returns:
        Dictionary with memory usage info
    """
    if not is_gpu_available():
        return {'gpu_memory_used': 0, 'gpu_memory_total': 0, 'gpu_memory_free': 0}
    
    try:
        cp = get_cupy()
        if cp is not None:
            mempool = cp.get_default_memory_pool()
            used_bytes = mempool.used_bytes()
            total_bytes = mempool.total_bytes()
            free_bytes = total_bytes - used_bytes
            
            return {
                'gpu_memory_used': used_bytes,
                'gpu_memory_total': total_bytes,
                'gpu_memory_free': free_bytes
            }
    except Exception as e:
        logger.warning(f"Failed to get GPU memory info: {e}")
    
    return {'gpu_memory_used': 0, 'gpu_memory_total': 0, 'gpu_memory_free': 0}

def compare_implementations(cpu_func, gpu_func, *args, **kwargs):
    """
    Compare CPU and GPU implementations side by side.
    
    Args:
        cpu_func: CPU implementation function
        gpu_func: GPU implementation function
        *args, **kwargs: Arguments to pass to both functions
        
    Returns:
        Dictionary with results and timing information
    """
    results = {
        'cpu_result': None,
        'gpu_result': None,
        'cpu_time': 0,
        'gpu_time': 0,
        'gpu_available': is_gpu_available(),
        'difference': None
    }
    
    # Run CPU implementation
    start_time = time.time()
    try:
        results['cpu_result'] = cpu_func(*args, **kwargs)
        results['cpu_time'] = time.time() - start_time
    except Exception as e:
        results['cpu_error'] = str(e)
    
    # Run GPU implementation if available
    if results['gpu_available']:
        start_time = time.time()
        try:
            results['gpu_result'] = gpu_func(*args, **kwargs)
            results['gpu_time'] = time.time() - start_time
        except Exception as e:
            results['gpu_error'] = str(e)
    
    # Calculate difference if both succeeded
    if results['cpu_result'] is not None and results['gpu_result'] is not None:
        if isinstance(results['cpu_result'], (int, float)) and isinstance(results['gpu_result'], (int, float)):
            results['difference'] = abs(results['cpu_result'] - results['gpu_result'])
        else:
            results['difference'] = "Non-numeric results"
    
    return results

# Convenience aliases for backward compatibility
GPU_AVAILABLE = is_gpu_available
RAPIDS_AVAILABLE = lambda: is_cupy_available() and is_cudf_available()

# Initialize GPU state on import
_initialize_gpu_state()

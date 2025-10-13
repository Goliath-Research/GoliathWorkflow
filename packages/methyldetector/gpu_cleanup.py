#!/usr/bin/env python3
"""
GPU Memory Cleanup Utility for MethylDetector

This script helps monitor and clean up GPU memory usage,
especially useful when processes are interrupted and leave
GPU memory allocated.

Now leverages MethylUtils' advanced GPU detection and memory management.
"""

import subprocess
import sys
import time

# Import MethylUtils for advanced GPU management
try:
    from methyl_utils.gpu_detection import (
        get_gpu_state, 
        get_memory_info, 
        cleanup_gpu_memory as methyl_utils_cleanup
    )
    from methyl_utils.memory_manager import get_memory_manager, force_gpu_cleanup
    METHYL_UTILS_AVAILABLE = True
except ImportError:
    METHYL_UTILS_AVAILABLE = False

def get_gpu_info():
    """Get current GPU memory usage using MethylUtils if available."""
    if METHYL_UTILS_AVAILABLE:
        # Use MethylUtils' advanced GPU detection
        gpu_state = get_gpu_state()
        if gpu_state['available']:
            print(f"GPU: {gpu_state['gpu_name']} ({gpu_state['memory_gb']:.1f}GB)")
            print(f"CUDA: {gpu_state['cuda_version']}, Compute: {gpu_state['compute_capability']}")
            
            # Get detailed memory info
            memory_info = get_memory_info()
            if memory_info['gpu_memory_total'] > 0:
                used_gb = memory_info['gpu_memory_used'] / (1024**3)
                total_gb = memory_info['gpu_memory_total'] / (1024**3)
                free_gb = memory_info['gpu_memory_free'] / (1024**3)
                usage_percent = (used_gb / total_gb) * 100 if total_gb > 0 else 0
                print(f"Memory: {used_gb:.2f}GB / {total_gb:.2f}GB ({usage_percent:.1f}% used)")
                print(f"Free: {free_gb:.2f}GB")
            else:
                print("Memory info not available")
        else:
            print("GPU not available")
            if gpu_state['error_message']:
                print(f"Reason: {gpu_state['error_message']}")
    else:
        # Fallback to nvidia-smi
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for i, line in enumerate(lines):
                    used, total = map(int, line.split(', '))
                    print(f"GPU {i}: {used}MB / {total}MB ({used/total*100:.1f}% used)")
            else:
                print("Failed to get GPU info")
        except FileNotFoundError:
            print("nvidia-smi not found. Make sure NVIDIA drivers are installed.")

def get_gpu_processes():
    """Get processes using GPU memory."""
    try:
        result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory', 
                               '--format=csv,noheader'], capture_output=True, text=True)
        if result.returncode == 0:
            if result.stdout.strip():
                print("GPU Processes:")
                print("PID\tProcess\t\tMemory")
                print("-" * 40)
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        pid, name, memory = parts[0], parts[1], parts[2]
                        print(f"{pid}\t{name}\t\t{memory}")
            else:
                print("No GPU processes found")
        else:
            print("Failed to get GPU processes")
    except FileNotFoundError:
        print("nvidia-smi not found. Make sure NVIDIA drivers are installed.")

def kill_methyl_detector_processes():
    """Kill all running methyl_detector processes including Docker exec processes."""
    try:
        # First, get all processes and kill by PID (most reliable)
        print("🔄 Killing processes by PID (most reliable method)...")
        killed_pids = []
        
        # Get all methyl_detector related processes
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, text=True
        )
        
        if result.stdout:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'methyl_detector' in line and 'grep' not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            # Check if process is still running
                            check_result = subprocess.run(
                                ["ps", "-p", str(pid)], 
                                capture_output=True, text=True
                            )
                            
                            if check_result.returncode == 0:  # Process exists
                                # Try graceful kill first
                                subprocess.run(["kill", str(pid)], capture_output=True, timeout=2)
                                time.sleep(0.5)
                                
                                # Check if still running and force kill if needed
                                check_result = subprocess.run(
                                    ["ps", "-p", str(pid)], 
                                    capture_output=True, text=True
                                )
                                
                                if check_result.returncode == 0:  # Still running
                                    subprocess.run(["kill", "-9", str(pid)], capture_output=True)
                                    print(f"  Force killed PID {pid}")
                                else:
                                    print(f"  Gracefully killed PID {pid}")
                                
                                killed_pids.append(pid)
                        except (ValueError, IndexError, subprocess.TimeoutExpired):
                            pass
        
        # Also try pattern-based killing as backup
        print("🔄 Pattern-based cleanup (backup method)...")
        subprocess.run(
            ["pkill", "-f", "docker exec.*methyl_detector"],
            capture_output=True, text=True
        )
        subprocess.run(
            ["pkill", "-f", "python -m methyl_detector"],
            capture_output=True, text=True
        )
        
        if killed_pids:
            print(f"✅ Killed {len(killed_pids)} processes: {killed_pids}")
        else:
            print("✅ No methyl_detector processes found to kill")
        
    except Exception as e:
        print(f"Error killing processes: {e}")

def cleanup_gpu_memory():
    """Clean up GPU memory using MethylUtils if available."""
    if METHYL_UTILS_AVAILABLE:
        # Use MethylUtils' advanced memory management
        try:
            # Use the memory manager for comprehensive cleanup
            memory_manager = get_memory_manager()
            memory_manager.force_gpu_cleanup()
            print("✅ GPU memory cleaned up using MethylUtils (comprehensive)")
        except Exception as e:
            # Fallback to basic cleanup
            try:
                methyl_utils_cleanup()
                print("✅ GPU memory cleaned up using MethylUtils (basic)")
            except Exception as e2:
                print(f"Error with MethylUtils cleanup: {e2}")
    else:
        # Fallback to direct CuPy cleanup
        try:
            import cupy as cp
            # Clean up all memory pools
            cp.get_default_memory_pool().free_all_blocks()
            cp.get_default_pinned_memory_pool().free_all_blocks()
            print("✅ GPU memory cleaned up (CuPy fallback)")
        except ImportError:
            print("CuPy not available for memory cleanup")
        except Exception as e:
            print(f"Error cleaning GPU memory: {e}")

def docker_cleanup():
    """Clean up Docker containers running methyl_detector."""
    try:
        print("🔄 Stopping Docker containers...")
        stopped_containers = []
        
        # Get running containers
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.ID}}"],
            capture_output=True, text=True
        )
        
        if result.stdout:
            lines = result.stdout.split('\n')
            for line in lines:
                if line.strip() and 'methyl' in line.lower():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        container_name = parts[0]
                        container_id = parts[1]
                        print(f"  Stopping container: {container_name} ({container_id})")
                        
                        # Try graceful stop first
                        stop_result = subprocess.run(
                            ["docker", "stop", container_id], 
                            capture_output=True, text=True, timeout=10
                        )
                        
                        # If graceful stop fails, force kill
                        if stop_result.returncode != 0:
                            print(f"    Graceful stop failed, force killing...")
                            subprocess.run(
                                ["docker", "kill", container_id], 
                                capture_output=True, text=True
                            )
                        
                        stopped_containers.append(container_name)
        
        if stopped_containers:
            print(f"✅ Stopped {len(stopped_containers)} containers: {stopped_containers}")
        else:
            print("✅ No methyl_detector containers found to stop")
        
    except Exception as e:
        print(f"Error in Docker cleanup: {e}")

def emergency_cleanup():
    """Emergency cleanup for interrupted processes."""
    print("🚨 Performing emergency GPU cleanup...")
    cleanup_gpu_memory()
    kill_methyl_detector_processes()
    docker_cleanup()
    print("✅ Emergency cleanup completed")

def main():
    """Main function."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "info":
            print("=== GPU Memory Info ===")
            get_gpu_info()
            print("\n=== GPU Processes ===")
            get_gpu_processes()
            
        elif command == "kill":
            print("Killing methyl_detector processes...")
            kill_methyl_detector_processes()
            print("\n=== GPU Memory After Cleanup ===")
            get_gpu_info()
            
        elif command == "cleanup":
            print("Cleaning up GPU memory...")
            cleanup_gpu_memory()
            print("\n=== GPU Memory After Cleanup ===")
            get_gpu_info()
            
        elif command == "full":
            print("=== Full GPU Cleanup ===")
            kill_methyl_detector_processes()
            cleanup_gpu_memory()
            print("\n=== Final GPU Status ===")
            get_gpu_info()
            
        elif command == "emergency":
            print("=== Emergency GPU Cleanup ===")
            emergency_cleanup()
            print("\n=== Final GPU Status ===")
            get_gpu_info()
            
        elif command == "docker":
            print("=== Docker Cleanup ===")
            docker_cleanup()
            print("\n=== Final GPU Status ===")
            get_gpu_info()
            
        else:
            print("Unknown command. Use: info, kill, cleanup, full, emergency, or docker")
    else:
        print("GPU Cleanup Utility for MethylDetector")
        print("Usage: python gpu_cleanup.py [command]")
        print("\nCommands:")
        print("  info      - Show GPU memory usage and processes")
        print("  kill      - Kill all methyl_detector processes")
        print("  cleanup   - Clean up GPU memory using CuPy")
        print("  full      - Kill processes and clean memory")
        print("  emergency - Emergency cleanup for interrupted processes")
        print("  docker    - Stop Docker containers running methyl_detector")
        print("\nExample: python gpu_cleanup.py emergency")

if __name__ == "__main__":
    main()

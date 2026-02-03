"""
Monitor module for tracking Parabricks fq2bam processing progress.

This module provides functionality to monitor and log the progress of
Parabricks fq2bam alignment processing, estimating completion based on
input size and processing rates.
"""

import subprocess
import threading
import time
import re
from typing import List, Optional
from pathlib import Path


def run_with_logging(
    command: List[str],
    sample_name: str,
    total_input_size: int,
    log_file: Optional[str] = None
) -> int:
    """
    Run a command with progress monitoring and logging.

    Args:
        command: Command to execute as list of strings
        sample_name: Name of the sample being processed
        total_input_size: Total input size in bytes for progress estimation
        log_file: Optional log file path

    Returns:
        Exit code of the command
    """
    print(f"Starting monitoring for sample: {sample_name}")
    print(f"Total input size: {total_input_size:,} bytes")

    # Start the subprocess
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    start_time = time.time()
    processed_bytes = 0

    try:
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())

                # Parse progress from Parabricks output
                # Look for lines like: "# 10  0  1  0  0   0 pool:  1 9906648 bases/GPU/minute: 59439888.0"
                match = re.search(r'pool:\s+\d+\s+(\d+)\s+bases/GPU/minute:', output)
                if match:
                    current_bases = int(match.group(1))
                    processed_bytes = current_bases

                    # Calculate progress
                    progress_pct = min(100.0, (processed_bytes / total_input_size) * 100)

                    elapsed_time = time.time() - start_time
                    if elapsed_time > 0:
                        rate_bps = processed_bytes / elapsed_time
                        eta_seconds = (total_input_size - processed_bytes) / rate_bps if rate_bps > 0 else 0

                        print(".1f"
                              ".1f")

                # Check for completion markers
                if "Done." in output:
                    print(f"Sample {sample_name} processing completed successfully")
                    break

    except KeyboardInterrupt:
        print(f"\nMonitoring interrupted for sample {sample_name}")
        process.terminate()
        return 1

    # Wait for process to complete
    return_code = process.wait()

    if return_code == 0:
        total_time = time.time() - start_time
        rate_mbps = (processed_bytes / total_time) / (1024 * 1024) if total_time > 0 else 0
        print(f"Sample {sample_name} completed in {total_time:.1f} seconds")
        print(".2f")
    else:
        print(f"Sample {sample_name} failed with return code {return_code}")

    return return_code


def estimate_progress_from_output(line: str, total_input_size: int) -> Optional[dict]:
    """
    Parse a line of Parabricks output to estimate progress.

    Args:
        line: Single line of output from Parabricks
        total_input_size: Total expected input size in bytes

    Returns:
        Dict with progress information or None if not a progress line
    """
    # Match lines like: "# 10  0  1  0  0   0 pool:  1 9906648 bases/GPU/minute: 59439888.0"
    pattern = r'# \d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+pool:\s+\d+\s+(\d+)\s+bases/GPU/minute:\s+([\d.]+)'
    match = re.search(pattern, line)

    if match:
        processed_bases = int(match.group(1))
        rate_bases_per_minute = float(match.group(2))

        progress_pct = min(100.0, (processed_bases / total_input_size) * 100)
        rate_bps = rate_bases_per_minute / 60.0  # Convert to bases per second

        return {
            'processed_bases': processed_bases,
            'progress_pct': progress_pct,
            'rate_bps': rate_bps,
            'rate_bases_per_minute': rate_bases_per_minute
        }

    return None


def parse_fq2bam_progress(output_line: str) -> Optional[dict]:
    """
    Parse fq2bam phase progress from Parabricks output.

    Args:
        output_line: Line from Parabricks stderr/stdout

    Returns:
        Dict with phase information or None
    """
    # Phase markers
    if "GPU-PBBWA mem, Sorting Phase-I" in output_line:
        return {'phase': 'phase1', 'description': 'GPU-PBBWA mem, Sorting Phase-I'}
    elif "Sorting Phase-II" in output_line:
        return {'phase': 'phase2', 'description': 'Sorting Phase-II'}
    elif any(marker in output_line for marker in ["Done.", "100.0"]):
        return {'phase': 'complete', 'description': 'Processing complete'}

    return None
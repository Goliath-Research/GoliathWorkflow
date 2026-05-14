#!/usr/bin/env python3
"""
Script to run MethylDetector using the project's virtual environment.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_methyldetector():
    """Run MethylDetector using the project's virtual environment."""

    # Get the current directory and venv path
    current_dir: Path = Path(__file__).parent
    venv_python: Path = current_dir / ".venv" / "bin" / "python"

    # Check if virtual environment exists
    if not venv_python.exists():
        print(f"❌ Virtual environment not found at: {venv_python}")
        print("Please ensure the virtual environment is properly set up.")
        sys.exit(1)

    # Set PYTHONPATH to include packages
    packages_dir: Path = current_dir / "packages"
    env: dict[str, str] = os.environ.copy()
    env['PYTHONPATH'] = f"{packages_dir}:{packages_dir}/methylutils:{packages_dir}/methyldetector"

    # Ensure CUDA headers are found for CuPy JIT compilation (cuda_fp16.h, etc.)
    cuda_paths: list[str] = ["/usr/local/cuda-13.0",
                  "/usr/local/cuda-13", "/usr/local/cuda"]
    for cuda_path in cuda_paths:
        if (Path(cuda_path) / "include" / "cuda_fp16.h").exists():
            env.setdefault("CUDA_HOME", cuda_path)
            env.setdefault("CUDA_PATH", cuda_path)
            break

    # Run the command with all arguments passed through
    # Use methyl_detector.cli (not .cli.main) to avoid runpy warning: cli/__init__.py
    # imports .main, so executing .cli.main as __main__ would load it twice.
    cmd: list[str] = [str(venv_python), "-m", "methyl_detector.cli"] + sys.argv[1:]

    try:
        result = subprocess.run(cmd, env=env, cwd=current_dir)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️  MethylDetector interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running MethylDetector: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_methyldetector()

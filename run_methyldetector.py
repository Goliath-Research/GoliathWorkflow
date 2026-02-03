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
    current_dir = Path(__file__).parent
    venv_python = current_dir / ".venv" / "bin" / "python"

    # Check if virtual environment exists
    if not venv_python.exists():
        print(f"❌ Virtual environment not found at: {venv_python}")
        print("Please ensure the virtual environment is properly set up.")
        sys.exit(1)

    # Set PYTHONPATH to include packages
    packages_dir = current_dir / "packages"
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{packages_dir}:{packages_dir}/methylutils:{packages_dir}/methyldetector"

    # Run the command with all arguments passed through
    cmd = [str(venv_python), "-m", "methyl_detector.cli.main"] + sys.argv[1:]

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
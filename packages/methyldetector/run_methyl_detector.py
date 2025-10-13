#!/usr/bin/env python3
"""
Convenient runner script for MethylDetector.

Usage:
    python run_methyl_detector.py --config path/to/config.json [--verbose]

This script automatically sets up the Python path and runs the MethylDetector CLI.
"""

import sys
import os
from pathlib import Path

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent

    # Add the script directory to Python path for imports
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    # Also add MethylUtils if it's in a sibling directory
    methyl_utils_dir = script_dir.parent / "MethylUtils"
    if methyl_utils_dir.exists() and str(methyl_utils_dir) not in sys.path:
        sys.path.insert(0, str(methyl_utils_dir))

    # Import and run the CLI
    try:
        from methyl_detector.cli.main import main
        main()
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure MethylUtils is available in the Python path.")
        print("You can also try: python -m methyl_detector.cli.main")
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Debug script to inspect what's in the pickle file and what modules it references.
"""

import pickle
import sys
from pathlib import Path

# Add methyl_utils to path
sys.path.insert(0, str(Path(__file__).parent))

class DebugUnpickler(pickle.Unpickler):
    """Debug unpickler that shows what modules are being referenced."""

    def find_class(self, module, name):
        print(f"DEBUG: Trying to import {module}.{name}")
        try:
            result = super().find_class(module, name)
            print(f"DEBUG: Successfully imported {module}.{name}")
            return result
        except ImportError as e:
            print(f"DEBUG: Failed to import {module}.{name}: {e}")
            raise

def inspect_pickle():
    model_path = Path('/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/detection/single/pb-ch-1-CG/classifier_model.pkl')

    print(f"Inspecting pickle file: {model_path}")
    print(f"File exists: {model_path.exists()}")

    if not model_path.exists():
        print("File does not exist!")
        return

    try:
        with open(model_path, 'rb') as f:
            print("Attempting to load with debug unpickler...")
            classifier = DebugUnpickler(f).load()
            print(f"Successfully loaded: {classifier}")
    except Exception as e:
        print(f"Failed to load: {e}")

if __name__ == '__main__':
    inspect_pickle()

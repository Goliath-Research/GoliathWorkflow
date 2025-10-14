#!/usr/bin/env python3
"""
Standalone script to validate configuration files without importing full methylcentroid module.
"""

import json
import sys
from pathlib import Path

# Import directly from the config module file to avoid __init__.py imports
import importlib.util
config_path = Path(__file__).parent / "packages" / "methylcentroid" / "methylcentroid" / "config.py"
spec = importlib.util.spec_from_file_location("config", config_path)
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)

MethylCentroidConfig = config_module.MethylCentroidConfig
BatchProcessingConfig = config_module.BatchProcessingConfig

def validate_batch_config(config_path: Path):
    """Validate a batch configuration file."""
    print(f"\n{'='*60}")
    print(f"Validating: {config_path.name}")
    print('='*60)
    
    try:
        # Load JSON
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        # Validate with Pydantic
        config = BatchProcessingConfig.model_validate(data)
        
        print("✅ Configuration is valid!")
        print(f"\nMetadata (from base_config):")
        print(f"  Laboratory: {config.base_config.laboratory}")
        print(f"  Disease: {config.base_config.disease}")
        print(f"  Group: {config.base_config.group}")
        print(f"  Batch: {config.base_config.batch}")
        
        print(f"\nProcessing details:")
        print(f"  Chromosomes: {len(config.chromosomes)} chromosomes")
        print(f"  Contexts: {config.contexts}")
        print(f"  Samples: {len(config.base_config.add_samples)} samples")
        
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def validate_single_config(config_path: Path):
    """Validate a single MethylCentroid configuration file."""
    print(f"\n{'='*60}")
    print(f"Validating: {config_path.name}")
    print('='*60)
    
    try:
        # Load JSON
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        # Validate with Pydantic
        config = MethylCentroidConfig.model_validate(data)
        
        print("✅ Configuration is valid!")
        print(f"\nMetadata:")
        print(f"  Laboratory: {config.laboratory}")
        print(f"  Disease: {config.disease}")
        print(f"  Group: {config.group}")
        print(f"  Batch: {config.batch}")
        
        print(f"\nProcessing details:")
        print(f"  Chromosome: {config.chrom}")
        print(f"  Context: {config.ctx}")
        print(f"  Samples: {len(config.samples) + len(config.add_samples)} samples")
        
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main validation function."""
    # Test the batch config files
    config_dir = Path(__file__).parent / "packages" / "methylcentroid" / "methylcentroid" / "configs"
    
    configs_to_test = [
        config_dir / "pb-cancer_batch_config.json",
        config_dir / "pb-cancer_batch12_config.json",
    ]
    
    all_valid = True
    for config_path in configs_to_test:
        if config_path.exists():
            if not validate_batch_config(config_path):
                all_valid = False
        else:
            print(f"⚠️  Config file not found: {config_path}")
            all_valid = False
    
    print(f"\n{'='*60}")
    if all_valid:
        print("✅ All configurations are valid!")
    else:
        print("❌ Some configurations failed validation")
    print('='*60)
    
    return 0 if all_valid else 1

if __name__ == '__main__':
    sys.exit(main())


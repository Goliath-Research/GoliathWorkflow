#!/usr/bin/env python3
"""
Test script for methyl_detector that generates configs for all chromosome/context combinations.

This script takes a single config.json file (created for one chromosome/context combination)
and generates configs for all 68 combinations of chromosomes (1-22, X) and contexts (CG, CHG, CHH).
It then executes the md script for each generated config.

Usage:
    python test_all_combinations.py <config.json>
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


def get_all_combinations(chromosomes: List[str] = None) -> List[Tuple[str, str]]:
    """Generate combinations of chromosomes and contexts."""
    if chromosomes is None:
        chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']  # 1-22, X, Y
    contexts = ['CG', 'CHG', 'CHH']
    
    combinations = []
    for chrom in chromosomes:
        for ctx in contexts:
            combinations.append((chrom, ctx))
    
    return combinations


def modify_config_for_combination(config: Dict[str, Any], chromosome: str, context: str) -> Dict[str, Any]:
    """Modify the config to use the specified chromosome and context."""
    # Create a deep copy of the config
    new_config = config.copy()
    
    # Handle different config formats
    if 'chromosome' in new_config and 'contexts' in new_config:
        # Format 1: Uses chromosome and contexts fields
        new_config['chromosome'] = chromosome
        new_config['contexts'] = [context]
    elif 'centroid1_path' in new_config and 'centroid2_path' in new_config:
        # Format 2: Uses specific centroid paths
        old_path = Path(new_config['centroid1_path'])
        # Replace the chromosome-context part in the filename
        new_filename = old_path.name.replace(old_path.stem.split('-')[0] + '-' + old_path.stem.split('-')[1], 
                                           f"{chromosome}-{context}")
        new_config['centroid1_path'] = str(old_path.parent / new_filename)
        
        old_path = Path(new_config['centroid2_path'])
        new_filename = old_path.name.replace(old_path.stem.split('-')[0] + '-' + old_path.stem.split('-')[1], 
                                           f"{chromosome}-{context}")
        new_config['centroid2_path'] = str(old_path.parent / new_filename)
    
    return new_config


def save_config(config: Dict[str, Any], output_path: str) -> None:
    """Save the config to a JSON file."""
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)


def execute_md_script_with_config(config_dict: Dict[str, Any], md_script_path: str) -> subprocess.CompletedProcess:
    """Execute the md script with a config dictionary (no temporary file)."""
    import tempfile
    import json
    import os
    import time
    
    # Create temporary config file in current directory (accessible to Docker container)
    # Use a unique name to avoid conflicts in parallel execution
    import uuid
    temp_filename = f"temp_config_{uuid.uuid4().hex[:8]}.json"
    temp_config_path = os.path.join(os.getcwd(), temp_filename)
    
    try:
        # Write config to temporary file
        with open(temp_config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        # Verify file was created
        if not os.path.exists(temp_config_path):
            raise RuntimeError(f"Failed to create temporary config file: {temp_config_path}")
        
        # Small delay to ensure file is written
        time.sleep(0.1)
        
        cmd = [md_script_path, temp_filename]  # Use relative path, not absolute
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result
    finally:
        # Clean up temporary file after execution completes
        try:
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)
        except OSError:
            pass  # File might already be deleted


def main():
    parser = argparse.ArgumentParser(
        description="Generate configs for all chromosome/context combinations and execute md script"
    )
    parser.add_argument(
        "config_file",
        help="Path to the original config.json file"
    )
    parser.add_argument(
        "--md-script",
        default="./md",
        help="Path to the md script (default: ./md)"
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save generated configs (default: same as input config)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate configs but don't execute md script"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel executions (default: 1)"
    )
    parser.add_argument(
        "--chromosomes",
        nargs="+",
        help="Specific chromosomes to process (e.g., --chromosomes 1 2 3 X). Default: all chromosomes 1-22, X, Y"
    )
    parser.add_argument(
        "--contexts",
        nargs="+",
        help="Specific contexts to process (e.g., --contexts CG CHG). Default: extract from original config"
    )
    
    args = parser.parse_args()
    
    # Validate input config file
    if not os.path.exists(args.config_file):
        print(f"Error: Config file '{args.config_file}' not found.")
        sys.exit(1)
    
    # Validate md script
    if not args.dry_run and not os.path.exists(args.md_script):
        print(f"Error: MD script '{args.md_script}' not found.")
        sys.exit(1)
    
    # Load the original config
    try:
        with open(args.config_file, 'r') as f:
            original_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read config file: {e}")
        sys.exit(1)
    
    # Determine output directory for configs
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(args.config_file).parent
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine chromosomes to process
    if args.chromosomes:
        chromosomes = args.chromosomes
        print(f"Processing specified chromosomes: {chromosomes}")
    else:
        chromosomes = None  # Will use default (1-22, X, Y)
        print("Processing all chromosomes: 1-22, X, Y")
    
    # Get all combinations
    combinations = get_all_combinations(chromosomes)
    
    # Extract the original chromosome and context from the input config filename
    input_config_path = Path(args.config_file)
    input_filename = input_config_path.stem  # Get filename without extension
    
    # Try to extract chromosome-context from the original config or filename
    import re
    
    # First try to get from config content
    if 'chromosome' in original_config and 'contexts' in original_config:
        original_chromosome = original_config['chromosome']
        original_context = original_config['contexts'][0] if original_config['contexts'] else 'CG'
        print(f"Detected original config for {original_chromosome}-{original_context} from config content")
    else:
        # Fallback: try to extract from filename
        match = re.search(r'(\d+|X|Y)-(CG|CHG|CHH)', input_filename)
        if match:
            original_chromosome, original_context = match.groups()
            print(f"Detected original config for {original_chromosome}-{original_context} from filename")
        else:
            print("Warning: Could not detect chromosome-context from config or filename. Will generate all combinations.")
            original_chromosome, original_context = "1", "CG"  # Default fallback
    
    # Remove the original combination from the list
    combinations = [(c, ctx) for c, ctx in combinations if not (c == original_chromosome and ctx == original_context)]
    
    # Filter contexts if specified
    if args.contexts:
        print(f"Processing specified contexts: {args.contexts}")
        combinations = [(c, ctx) for c, ctx in combinations if ctx in args.contexts]
    
    print(f"Generating configs for {len(combinations)} additional chromosome/context combinations...")
    
    # Generate configs and collect execution info
    config_files = []
    
    # Add the original config to the execution list
    config_files.append((original_config, original_chromosome, original_context))
    
    for i, (chromosome, context) in enumerate(combinations, 1):
        print(f"[{i:2d}/{len(combinations)}] Processing {chromosome}-{context}...")
        
        # Modify config for this combination
        modified_config = modify_config_for_combination(original_config, chromosome, context)
        
        config_files.append((modified_config, chromosome, context))
    
    print(f"\nGenerated {len(config_files)} total configs (including original)")
    
    if args.dry_run:
        print("Dry run completed. No md scripts executed.")
        return
    
    # Execute md scripts
    print(f"\nExecuting md scripts...")
    if args.parallel == 1:
        # Sequential execution
        for i, (config_dict, chromosome, context) in enumerate(config_files, 1):
            print(f"[{i:2d}/{len(config_files)}] Executing {chromosome}-{context}...")
            result = execute_md_script_with_config(config_dict, args.md_script)
            
            if result.returncode == 0:
                print(f"  ✅ {chromosome}-{context} completed successfully")
            else:
                print(f"  ❌ {chromosome}-{context} failed with return code {result.returncode}")
                if result.stderr:
                    print(f"  Error: {result.stderr.strip()}")
    else:
        # Parallel execution (basic implementation)
        import concurrent.futures
        import threading
        
        def execute_single(config_info):
            config_dict, chromosome, context = config_info
            result = execute_md_script_with_config(config_dict, args.md_script)
            return (chromosome, context, result)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
            # Submit all tasks
            future_to_config = {
                executor.submit(execute_single, config_info): config_info 
                for config_info in config_files
            }
            
            # Process completed tasks
            completed = 0
            for future in concurrent.futures.as_completed(future_to_config):
                completed += 1
                chromosome, context, result = future.result()
                
                if result.returncode == 0:
                    print(f"[{completed:2d}/{len(config_files)}] ✅ {chromosome}-{context} completed successfully")
                else:
                    print(f"[{completed:2d}/{len(config_files)}] ❌ {chromosome}-{context} failed with return code {result.returncode}")
                    if result.stderr:
                        print(f"  Error: {result.stderr.strip()}")
    
    print("\nAll executions completed.")


if __name__ == "__main__":
    main()

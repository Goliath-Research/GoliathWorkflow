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


def get_all_combinations() -> List[Tuple[str, str]]:
    """Generate all 68 combinations of chromosomes and contexts."""
    chromosomes = [str(i) for i in range(1, 23)] + ['X']  # 1-22, X
    contexts = ['CG', 'CHG', 'CHH']
    
    combinations = []
    for chrom in chromosomes:
        for context in contexts:
            combinations.append((chrom, context))
    
    return combinations


def modify_config_for_combination(config: Dict[str, Any], chromosome: str, context: str) -> Dict[str, Any]:
    """Modify the config to use the specified chromosome and context."""
    # Create a deep copy of the config
    new_config = config.copy()
    
    # Update centroid paths
    if 'centroid1_path' in new_config:
        old_path = Path(new_config['centroid1_path'])
        # Replace the chromosome-context part in the filename
        new_filename = old_path.name.replace(old_path.stem.split('-')[0] + '-' + old_path.stem.split('-')[1], 
                                           f"{chromosome}-{context}")
        new_config['centroid1_path'] = str(old_path.parent / new_filename)
    
    if 'centroid2_path' in new_config:
        old_path = Path(new_config['centroid2_path'])
        # Replace the chromosome-context part in the filename
        new_filename = old_path.name.replace(old_path.stem.split('-')[0] + '-' + old_path.stem.split('-')[1], 
                                           f"{chromosome}-{context}")
        new_config['centroid2_path'] = str(old_path.parent / new_filename)

    
    return new_config


def save_config(config: Dict[str, Any], output_path: str) -> None:
    """Save the config to a JSON file."""
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)


def execute_md_script(config_path: str, md_script_path: str) -> subprocess.CompletedProcess:
    """Execute the md script with the given config."""
    cmd = [md_script_path, config_path]
    return subprocess.run(cmd, capture_output=True, text=True)


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
        help="Number of parallel executions (default: 6)"
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
    
    # Get all combinations
    combinations = get_all_combinations()
    
    # Extract the original chromosome and context from the input config filename
    input_config_path = Path(args.config_file)
    input_filename = input_config_path.stem  # Get filename without extension
    
    # Try to extract chromosome-context from the original filename
    # Look for patterns like "1-CG", "X-CHG", etc.
    import re
    match = re.search(r'(\d+|X)-(CG|CHG|CHH)', input_filename)
    if match:
        original_chromosome, original_context = match.groups()
        print(f"Detected original config for {original_chromosome}-{original_context}")
        # Remove the original combination from the list
        combinations = [(c, ctx) for c, ctx in combinations if not (c == original_chromosome and ctx == original_context)]
    else:
        print("Warning: Could not detect chromosome-context from input filename. Will generate all combinations.")
        original_chromosome, original_context = "1", "CG"  # Default fallback
    
    print(f"Generating configs for {len(combinations)} additional chromosome/context combinations...")
    
    # Generate configs and collect execution info
    config_files = []
    
    # Add the original config to the execution list
    config_files.append((str(input_config_path), original_chromosome, original_context))
    
    for i, (chromosome, context) in enumerate(combinations, 1):
        print(f"[{i:2d}/{len(combinations)}] Processing {chromosome}-{context}...")
        
        # Modify config for this combination
        modified_config = modify_config_for_combination(original_config, chromosome, context)
        
        # Use the same naming pattern as the input config
        # Replace the chromosome-context part in the filename
        new_filename = input_filename.replace(f"{original_chromosome}-{original_context}", f"{chromosome}-{context}")
        config_filename = f"{new_filename}.json"
        config_path = output_dir / config_filename
        save_config(modified_config, str(config_path))
        
        config_files.append((str(config_path), chromosome, context))
    
    print(f"\nGenerated {len(config_files)} total config files (including original) in {output_dir}")
    
    if args.dry_run:
        print("Dry run completed. No md scripts executed.")
        return
    
    # Execute md scripts
    print(f"\nExecuting md scripts...")
    if args.parallel == 1:
        # Sequential execution
        for i, (config_path, chromosome, context) in enumerate(config_files, 1):
            print(f"[{i:2d}/{len(config_files)}] Executing {chromosome}-{context}...")
            result = execute_md_script(config_path, args.md_script)
            
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
            config_path, chromosome, context = config_info
            result = execute_md_script(config_path, args.md_script)
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

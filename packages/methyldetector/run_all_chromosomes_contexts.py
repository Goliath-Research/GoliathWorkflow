#!/usr/bin/env python3
"""
Run MethylDetector for all chromosome-context combinations.

This script generates config files and executes MethylDetector in Docker
for each chromosome and methylation context combination.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any

# Configuration
CHROMOSOMES = list(range(1, 23)) + ['X', 'Y']  # 1-22, X, Y
CONTEXTS = ['CG', 'CHG', 'CHH']

# Paths (adjust these to match your setup)
BASE_CONFIG_TEMPLATE = {
    "centroid1_path": "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/centroids/pb-healthy/{chrom}-{ctx}.h5",
    "centroid2_path": "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/centroids/pb-cancer/{chrom}-{ctx}.h5",
    "output_dir": "/home/ubuntu/Work/samples/humans/psomagen/AN00025834/data/detection/pb-ch",
    "alpha": 0.01,
    "min_delta_mean": 0.2,
    "max_bc": 0.6,
    "target_auc": 0.9999,
    "min_dmps_for_export": 1000,
    "gamma": 1.5,
    "use_gpu": True,
    "random_state": 42
}

# Docker settings
DOCKER_CONTAINER = "epimethyl"
WORK_DIR = "/home/ubuntu/MethylDetector"
CONFIG_DIR = Path("/home/ubuntu/MethylDetector/configs")
PYTHON_SCRIPT = "run_methyl_detector.py"


def create_config(chrom: str, ctx: str, template: Dict[str, Any]) -> Path:
    """
    Create a config JSON file for a specific chromosome and context.
    
    Args:
        chrom: Chromosome identifier (1-22, X, Y)
        ctx: Methylation context (CG, CHG, CHH)
        template: Base configuration template
        
    Returns:
        Path to the created config file
    """
    config = template.copy()
    
    # Update paths with chromosome and context
    config['centroid1_path'] = config['centroid1_path'].format(chrom=chrom, ctx=ctx)
    config['centroid2_path'] = config['centroid2_path'].format(chrom=chrom, ctx=ctx)
    
    # Create config file
    config_filename = f"pb-ch-{chrom}-{ctx}_config.json"
    config_path = CONFIG_DIR / config_filename
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Created config: {config_filename}")
    return config_path


def check_centroid_exists(centroid_path: str) -> bool:
    """
    Check if centroid file exists (convert Docker path to host path if needed).
    
    Args:
        centroid_path: Path to centroid file
        
    Returns:
        True if file exists, False otherwise
    """
    # Convert to host path (assumes /home/ubuntu/Work is mounted)
    host_path = Path(centroid_path)
    return host_path.exists()


def run_methyldetector(config_path: Path, chrom: str, ctx: str, dry_run: bool = False) -> bool:
    """
    Run MethylDetector in Docker container for a specific config.
    
    Args:
        config_path: Path to config JSON file
        chrom: Chromosome identifier
        ctx: Methylation context
        dry_run: If True, only print command without executing
        
    Returns:
        True if successful, False otherwise
    """
    # Docker path to config (inside container)
    docker_config_path = f"/home/ubuntu/MethylDetector/configs/{config_path.name}"
    
    # Build docker exec command
    cmd = [
        "docker", "exec",
        "-w", WORK_DIR,
        DOCKER_CONTAINER,
        "python", PYTHON_SCRIPT,
        docker_config_path
    ]
    
    print(f"\n{'='*70}")
    print(f"🧬 Processing: Chromosome {chrom} - Context {ctx}")
    print(f"{'='*70}")
    print(f"Command: {' '.join(cmd)}")
    
    if dry_run:
        print("⚠️  DRY RUN - Command not executed")
        return True
    
    try:
        # Execute command
        result = subprocess.run(
            cmd,
            capture_output=False,  # Show output in real-time
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ SUCCESS: {chrom}-{ctx} completed")
            return True
        else:
            print(f"❌ FAILED: {chrom}-{ctx} exited with code {result.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: {chrom}-{ctx} failed with error: {e}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {chrom}-{ctx}: {e}")
        return False


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run MethylDetector for all chromosome-context combinations"
    )
    parser.add_argument(
        '--chromosomes',
        nargs='+',
        default=None,
        help='Specific chromosomes to process (default: all 1-22, X, Y)'
    )
    parser.add_argument(
        '--contexts',
        nargs='+',
        choices=['CG', 'CHG', 'CHH'],
        default=None,
        help='Specific contexts to process (default: all CG, CHG, CHH)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate configs and print commands without executing'
    )
    parser.add_argument(
        '--check-files',
        action='store_true',
        help='Check if centroid files exist before processing'
    )
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue processing even if some chromosomes fail'
    )
    
    args = parser.parse_args()
    
    # Use specified chromosomes/contexts or defaults
    chromosomes = args.chromosomes if args.chromosomes else CHROMOSOMES
    contexts = args.contexts if args.contexts else CONTEXTS
    
    # Ensure config directory exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("MethylDetector Batch Processing")
    print("=" * 70)
    print(f"Chromosomes: {', '.join(map(str, chromosomes))}")
    print(f"Contexts: {', '.join(contexts)}")
    print(f"Total combinations: {len(chromosomes) * len(contexts)}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 70)
    
    # Track results
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    # Process each combination
    for chrom in chromosomes:
        for ctx in contexts:
            try:
                # Create config file
                config_path = create_config(chrom, ctx, BASE_CONFIG_TEMPLATE)
                
                # Check if centroid files exist (if requested)
                if args.check_files:
                    config = json.loads(config_path.read_text())
                    centroid1_exists = check_centroid_exists(config['centroid1_path'])
                    centroid2_exists = check_centroid_exists(config['centroid2_path'])
                    
                    if not (centroid1_exists and centroid2_exists):
                        print(f"⚠️  SKIPPING {chrom}-{ctx}: Centroid files not found")
                        if not centroid1_exists:
                            print(f"    Missing centroid1 (pb-healthy): {config['centroid1_path']}")
                        if not centroid2_exists:
                            print(f"    Missing centroid2 (pb-cancer): {config['centroid2_path']}")
                        results['skipped'].append(f"{chrom}-{ctx}")
                        continue
                
                # Run MethylDetector
                success = run_methyldetector(config_path, chrom, ctx, dry_run=args.dry_run)
                
                if success:
                    results['success'].append(f"{chrom}-{ctx}")
                else:
                    results['failed'].append(f"{chrom}-{ctx}")
                    if not args.continue_on_error and not args.dry_run:
                        print("\n❌ Stopping due to error (use --continue-on-error to continue)")
                        break
                        
            except Exception as e:
                print(f"❌ Error processing {chrom}-{ctx}: {e}")
                results['failed'].append(f"{chrom}-{ctx}")
                if not args.continue_on_error and not args.dry_run:
                    break
        else:
            continue
        break
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Successful: {len(results['success'])}")
    if results['success']:
        for item in results['success']:
            print(f"   • {item}")
    
    print(f"\n❌ Failed: {len(results['failed'])}")
    if results['failed']:
        for item in results['failed']:
            print(f"   • {item}")
    
    if results['skipped']:
        print(f"\n⚠️  Skipped: {len(results['skipped'])}")
        for item in results['skipped']:
            print(f"   • {item}")
    
    print("=" * 70)
    
    # Exit with appropriate code
    if results['failed'] and not args.dry_run:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()


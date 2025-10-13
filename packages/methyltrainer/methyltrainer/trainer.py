"""
Core training functionality for MethylTrainer
"""

import pickle
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from methyl_utils import (
    MethylSample,
    train_classifier_from_centroids,
    FilterConfig,
    get_logger
)

from .config import TrainingConfig

# Set up logging
logger = get_logger(__name__)


def extract_chromosome_context_from_path(file_path: Path) -> tuple[Optional[str], Optional[str]]:
    """
    Extract chromosome and context from filename.
    
    Expected format: *chr1-CG*.h5 or *chr1_CG*.h5
    
    Args:
        file_path: Path to centroid file
    
    Returns:
        Tuple of (chromosome, context) or (None, None)
    """
    stem = file_path.stem
    
    # Try hyphen separator
    if '-' in stem:
        parts = stem.split('-')
        for i, part in enumerate(parts):
            if part.startswith('chr') and i + 1 < len(parts):
                chromosome = part
                context = parts[i + 1].split('_')[0].split('.')[0]
                return chromosome, context
    
    # Try underscore separator
    if '_' in stem:
        parts = stem.split('_')
        for i, part in enumerate(parts):
            if part.startswith('chr') and i + 1 < len(parts):
                chromosome = part
                context = parts[i + 1].split('-')[0].split('.')[0]
                return chromosome, context
    
    return None, None


def train_from_centroids(
    centroid1_path: Path,
    centroid2_path: Path,
    output_path: Path,
    config: Optional[TrainingConfig] = None,
    filter_config: Optional[FilterConfig] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Train a classifier from two centroid files.
    
    Args:
        centroid1_path: Path to first centroid HDF5 file
        centroid2_path: Path to second centroid HDF5 file
        output_path: Path to save trained model
        config: Optional TrainingConfig (overrides other configs)
        filter_config: Optional FilterConfig
        verbose: Enable verbose logging
    
    Returns:
        Model package dictionary
    
    Raises:
        FileNotFoundError: If centroid files don't exist
        ValueError: If training fails
    """
    # Validate input files
    if not centroid1_path.exists():
        raise FileNotFoundError(f"Centroid 1 not found: {centroid1_path}")
    if not centroid2_path.exists():
        raise FileNotFoundError(f"Centroid 2 not found: {centroid2_path}")
    
    # Use config if provided, otherwise use individual configs
    if config is not None:
        filter_config = config.to_filter_config()
        centroid1_name = config.centroid1_name or centroid1_path.stem
        centroid2_name = config.centroid2_name or centroid2_path.stem
        chromosome = config.chromosome
        context = config.context
    else:
        centroid1_name = centroid1_path.stem
        centroid2_name = centroid2_path.stem
        chromosome = None
        context = None
    
    # Try to extract chromosome and context from filename if not provided
    if chromosome is None or context is None:
        chr1, ctx1 = extract_chromosome_context_from_path(centroid1_path)
        chr2, ctx2 = extract_chromosome_context_from_path(centroid2_path)
        
        # Use extracted values if they match
        if chr1 == chr2 and chr1 is not None:
            chromosome = chr1
        if ctx1 == ctx2 and ctx1 is not None:
            context = ctx1
    
    logger.info("=" * 80)
    logger.info("MethylTrainer - Bayesian Classifier Training")
    logger.info("=" * 80)
    logger.info(f"Centroid 1: {centroid1_path}")
    logger.info(f"Centroid 2: {centroid2_path}")
    logger.info(f"Output: {output_path}")
    if chromosome:
        logger.info(f"Chromosome: {chromosome}")
    if context:
        logger.info(f"Context: {context}")
    logger.info("=" * 80)
    
    try:
        # Train classifier using methyl_utils function (handles loading, training, saving)
        logger.info("🚀 Starting training pipeline...")
        
        model_package = train_classifier_from_centroids(
            centroid1_path=centroid1_path,
            centroid2_path=centroid2_path,
            output_path=output_path,
            filter_config=filter_config,
            centroid1_name=centroid1_name,
            centroid2_name=centroid2_name,
            chromosome=chromosome,
            context=context
        )
        
        # Print summary
        metadata = model_package['metadata']
        logger.info("=" * 80)
        logger.info("✅ Training Complete!")
        logger.info("=" * 80)
        logger.info(f"Model: {output_path}")
        logger.info(f"DMPs: {metadata['n_dmps']}")
        logger.info(f"Chromosome: {metadata['chromosome']}")
        logger.info(f"Context: {metadata['context']}")
        
        if 'validation' in metadata:
            val = metadata['validation']
            if 'overall_accuracy' in val:
                logger.info(f"Validation Accuracy: {val['overall_accuracy']:.1%}")
            logger.info(f"Validation: {val.get('validation_method', 'performed')}")
        
        logger.info("=" * 80)
        
        return model_package
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        raise


def train_from_config_file(config_path: Path) -> Dict[str, Any]:
    """
    Train a classifier from a configuration file.
    
    Args:
        config_path: Path to JSON configuration file
    
    Returns:
        Model package dictionary
    """
    from .config import load_config_from_file
    
    logger.info(f"📄 Loading configuration from: {config_path}")
    config = load_config_from_file(config_path)
    
    return train_from_centroids(
        centroid1_path=Path(config.centroid1_path),
        centroid2_path=Path(config.centroid2_path),
        output_path=Path(config.output_path),
        config=config,
        verbose=config.verbose
    )


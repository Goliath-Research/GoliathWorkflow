#!/usr/bin/env python3
"""
Command-line entry point for MethylMapper Bedtools mapping.

This script provides bedtools-based DMP-to-feature mapping without requiring
Azure SQL Database. It maps DMPs to all genomic features (genes, transcripts,
exons, introns, etc.) with comprehensive weighting by statistical significance.
"""

from methyl_mapper.cli import main_bedtools

if __name__ == '__main__':
    main_bedtools()


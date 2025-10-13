#!/usr/bin/env python3
"""
Setup script for MethylEnricher
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="methylenricher",
    version="0.1.0",
    author="MethylDetector Team",
    description="Gene enrichment analysis tool for methylation DMPs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "gseapy>=1.1.0",
        "pandas>=1.3.0",
        "numpy>=1.20.0",
    ],
    entry_points={
        "console_scripts": [
            "methylenricher=methylenricher.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)


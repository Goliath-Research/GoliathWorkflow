#!/usr/bin/env python3
"""
MethylCentroid Setup Script
===========================

Setup script for MethylCentroid - High-performance methylation centroid calculation
with GPU acceleration and multi-metric outlier detection.
"""

from setuptools import setup, find_packages
import os
import sys

# Read version from pyproject.toml or use default
def get_version():
    """Get version from pyproject.toml"""
    try:
        with open('pyproject.toml', 'r') as f:
            for line in f:
                if line.strip().startswith('version'):
                    return line.split('=')[1].strip().strip('"\'')
    except:
        pass
    return '1.0.0'

# Read README
def get_long_description():
    """Read README.md for long description"""
    readme_file = 'README.md'
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

# Core dependencies (always required)
CORE_REQUIREMENTS = [
    'numpy>=1.21.6,<1.28.0',
    'scipy>=1.11.0,<1.12.0',
    'pandas>=2.0.0,<3.0.0',
    'pydantic>=2.0.0,<2.1.0',
    'tqdm>=4.67.1,<4.68.0',
    'psutil>=7.0.0,<7.1.0',
    'plotly>=6.3.0,<6.4.0',
    'statsmodels>=0.14.0,<0.15.0',
    'seaborn>=0.13.2,<0.14.0',
]

# Data processing dependencies
DATA_REQUIREMENTS = [
    'h5py>=3.13.0,<4.0.0',
    'hdf5plugin>=5.1.0,<6.0.0',
    'pysam',  # No version constraint for pysam
]

# Development dependencies
DEV_REQUIREMENTS = [
    'pytest>=7.0.0,<7.1.0',
    'pytest-cov>=4.0.0,<4.1.0',
    'black>=23.0.0,<23.1.0',
    'flake8>=6.0.0,<6.1.0',
    'mypy>=1.0.0,<1.1.0',
    'pre-commit>=3.0.0,<3.1.0',
]

# Note: methyl-utils should be installed separately
# It's expected to be available in the environment

setup(
    name="methylcentroid",
    version=get_version(),
    description="High-performance methylation centroid calculation with GPU acceleration",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="David Izada Rodriguez",
    author_email="dizada@epimethyl.com",
    url="https://github.com/your-repo/MethylCentroid",
    packages=find_packages(exclude=['tests', 'docs', 'scripts']),
    include_package_data=True,
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Mathematics",
    ],
    keywords="methylation bioinformatics genomics gpu cuda centroid outlier-detection",
    install_requires=CORE_REQUIREMENTS + DATA_REQUIREMENTS,
    extras_require={
        'dev': DEV_REQUIREMENTS,
        'all': CORE_REQUIREMENTS + DATA_REQUIREMENTS + DEV_REQUIREMENTS,
    },
    entry_points={
        'console_scripts': [
            'methylcentroid=methylcentroid.centroid_cli:main',
        ],
    },
    zip_safe=False,
)

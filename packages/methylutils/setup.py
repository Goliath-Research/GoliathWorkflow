#!/usr/bin/env python3
"""
MethylUtils Setup Script
=======================

Setup script for MethylUtils - Genome-scale methylation analysis toolkit.
Optimized for NVIDIA GH200 with 96GB GPU memory and 16 vCPU.
"""

from setuptools import setup, find_packages
import os
import sys

# Read version from __init__.py
def get_version():
    """Get version from methyl_utils/__init__.py"""
    version_file = os.path.join(os.path.dirname(__file__), 'methyl_utils', '__init__.py')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            for line in f:
                if line.startswith('__version__'):
                    return line.split('=')[1].strip().strip('"\'')

    # Fallback version
    return '1.0.0'

# Read README
def get_long_description():
    """Read README.md for long description"""
    readme_file = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

# Core dependencies (always required)
CORE_REQUIREMENTS = [
    'numpy>=1.24.0,<1.25.0',
    'scipy>=1.11.0,<1.12.0',
    'pandas>=2.0.0,<2.1.0',
    'pydantic>=2.0.0,<2.1.0',
    'pyyaml>=6.0.0,<6.1.0',
    'colorlog>=6.7.0,<6.8.0',
    'nvidia-ml-py>=12.535.0,<12.536.0',
]

# GPU dependencies (optional)
GPU_REQUIREMENTS = [
    'cupy-cuda12x>=12.1.0,<12.2.0',
    'cupyx>=12.1.0,<12.2.0',
    'torch>=2.0.0,<2.1.0',
    'torchvision>=0.15.0,<0.16.0',
    'torchaudio>=2.0.0,<2.1.0',
]

# HDF5 dependencies (optional)
HDF5_REQUIREMENTS = [
    'h5py>=3.9.0,<3.10.0',
    'hdf5plugin>=4.1.0,<4.2.0',
]

# Production monitoring dependencies (optional)
MONITORING_REQUIREMENTS = [
    'prometheus-client>=0.17.0,<0.18.0',
    'psutil>=5.9.0,<5.10.0',
    'py-cpuinfo>=9.0.0,<9.1.0',
    'GPUtil>=1.4.0,<1.5.0',
    'memory-profiler>=0.61.0,<0.62.0',
    'line-profiler>=4.1.0,<4.2.0',
]

# Jupyter dependencies (optional)
JUPYTER_REQUIREMENTS = [
    'jupyterlab>=4.0.0,<4.1.0',
    'ipywidgets>=8.0.0,<8.1.0',
]

# Data science dependencies (optional)
DATASCIENCE_REQUIREMENTS = [
    'scikit-learn>=1.3.0,<1.4.0',
    'matplotlib>=3.7.0,<3.8.0',
    'seaborn>=0.12.0,<0.13.0',
    'plotly>=5.15.0,<5.16.0',
]

# Development dependencies
DEVELOPMENT_REQUIREMENTS = [
    'pytest>=7.4.0,<7.5.0',
    'pytest-cov>=4.1.0,<4.2.0',
    'pytest-xdist>=3.3.0,<3.4.0',
    'pytest-benchmark>=4.0.0,<4.1.0',
    'black>=23.7.0,<23.8.0',
    'flake8>=6.0.0,<6.1.0',
    'mypy>=1.5.0,<1.6.0',
    'pre-commit>=3.4.0,<3.5.0',
    'sphinx>=7.0.0,<7.1.0',
    'sphinx-rtd-theme>=1.2.0,<1.3.0',
]

# All dependencies combined
ALL_REQUIREMENTS = (
    CORE_REQUIREMENTS +
    GPU_REQUIREMENTS +
    HDF5_REQUIREMENTS +
    MONITORING_REQUIREMENTS +
    JUPYTER_REQUIREMENTS +
    DATASCIENCE_REQUIREMENTS +
    DEVELOPMENT_REQUIREMENTS
)

# Create requirements.txt from setup.py dependencies
def create_requirements_txt():
    """Create requirements.txt from setup.py dependencies"""
    requirements_txt = os.path.join(os.path.dirname(__file__), 'requirements.txt')

    with open(requirements_txt, 'w') as f:
        f.write('# MethylUtils Production Requirements\n')
        f.write('# ==================================\n')
        f.write('# Core dependencies for genome-scale methylation analysis\n')
        f.write('# Optimized for NVIDIA GH200 with 96GB GPU memory\n')
        f.write('\n')

        # Core requirements
        f.write('# Core Scientific Computing\n')
        for req in CORE_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        # Optional requirements
        f.write('# GPU Computing (optional)\n')
        for req in GPU_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        f.write('# HDF5 Support (optional)\n')
        for req in HDF5_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        f.write('# Production Monitoring (optional)\n')
        for req in MONITORING_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        f.write('# Data Science (optional)\n')
        for req in DATASCIENCE_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        f.write('# Jupyter Support (optional)\n')
        for req in JUPYTER_REQUIREMENTS:
            f.write(f'{req}\n')
        f.write('\n')

        f.write('# Development and Testing (optional)\n')
        for req in DEVELOPMENT_REQUIREMENTS:
            f.write(f'{req}\n')

# Generate requirements.txt if it doesn't exist
if not os.path.exists(os.path.join(os.path.dirname(__file__), 'requirements.txt')):
    create_requirements_txt()

setup(
    name="methylutils",
    version=get_version(),
    description="Genome-scale methylation analysis toolkit optimized for NVIDIA GH200",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="MethylUtils Team",
    author_email="team@methylutils.org",
    url="https://github.com/methylutils/methylutils",
    packages=find_packages(exclude=['tests', 'docs', 'examples']),
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
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Mathematics",
        "Topic :: System :: Distributed Computing",
    ],
    keywords="methylation genomics bioinformatics gpu cuda nvidia gh200",
    install_requires=CORE_REQUIREMENTS,
    extras_require={
        'gpu': GPU_REQUIREMENTS,
        'hdf5': HDF5_REQUIREMENTS,
        'monitoring': MONITORING_REQUIREMENTS,
        'jupyter': JUPYTER_REQUIREMENTS,
        'datascience': DATASCIENCE_REQUIREMENTS,
        'development': DEVELOPMENT_REQUIREMENTS,
        'all': ALL_REQUIREMENTS,
        'production': CORE_REQUIREMENTS + GPU_REQUIREMENTS + HDF5_REQUIREMENTS + MONITORING_REQUIREMENTS,
    },
    entry_points={
        'console_scripts': [
            'methylutils=methyl_utils.cli:main',
            'methylutils-deploy=methyl_utils.deployment:main',
        ],
    },
    project_urls={
        'Documentation': 'https://methylutils.readthedocs.io/',
        'Source': 'https://github.com/methylutils/methylutils',
        'Tracker': 'https://github.com/methylutils/methylutils/issues',
        'Changelog': 'https://github.com/methylutils/methylutils/blob/main/CHANGELOG.md',
    },
    zip_safe=False,
    # Platform-specific wheels for CUDA
    package_data={
        'methyl_utils': [
            '*.pyi',
            'py.typed',
        ],
    },
)

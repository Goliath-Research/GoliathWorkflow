#!/usr/bin/env python3
"""
Setup script for MethylClassifier
"""

from setuptools import setup, find_packages
import os

# Read the README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="methyl_classifier",
    version="0.1.0",
    author="MethylClassifier Development Team",
    author_email="",
    description="Command Line Tool for Methylation-Based Sample Classification",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/methyl_classifier",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
    python_requires=">=3.7",
    install_requires=[
        "numpy>=1.19.0",
        "scipy>=1.7.0",
        "pandas>=1.3.0",
        "h5py>=3.1.0",
        "matplotlib>=3.3.0",
        "seaborn>=0.11.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.9",
            "mypy>=0.800",
        ],
    },
    entry_points={
        "console_scripts": [
            "methyl_classifier=methyl_classifier.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)

"""
Setup script for shared GPU utilities package.
"""

from setuptools import setup, find_packages

setup(
    name="methyl-utils",
    version="1.0.0",
    description="Shared utilities for methyl-related applications (GPU detection, logging, etc.)",
    author="MethylCentroid Team",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "nvidia-ml-py>=12.535.0",
    ],
    extras_require={
        "gpu": [
            "cupy-cuda11x>=10.0.0",  # Adjust CUDA version as needed
        ],
        "rapids": [
            "cupy-cuda11x>=10.0.0",
            "cudf-cu11>=22.0.0",  # Adjust CUDA version as needed
        ],
        "dev": [
            "pytest>=6.0.0",
            "pytest-cov>=2.0.0",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
)

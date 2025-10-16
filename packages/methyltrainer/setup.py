"""Setup script for MethylTrainer"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="methyl_trainer",
    version="0.1.0",
    description="Train Bayesian classifiers from methylation centroids",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="MethylAnalysis Team",
    author_email="",
    url="https://github.com/your-org/methyl_trainer",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "scipy>=1.7.0",
        "h5py>=3.0.0",
        "methyl-utils>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "methyl_trainer=methyl_trainer.cli:main",
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
        "Programming Language :: Python :: 3.11",
    ],
    keywords="methylation epigenetics bioinformatics machine-learning",
)


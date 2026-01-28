#!/bin/bash
# Host environment setup script for CUDA 13.0 + RAPIDS 25.10 (conda)

set -e

echo "============================================="
echo "MethylPipeline Host Conda Setup"
echo "============================================="
echo ""

if ! command -v conda &> /dev/null; then
    echo "❌ Conda not found."
    echo "   Install Miniforge first:"
    echo "   https://github.com/conda-forge/miniforge"
    exit 1
fi

ENV_NAME="rapids-25.10"

echo "🐍 Creating conda environment: $ENV_NAME"
conda create -y -n "$ENV_NAME" -c rapidsai-nightly -c conda-forge -c nvidia \
  rapids=25.10 python=3.12 'cuda-version=13.0' \
  jupyter hdbscan umap-learn

echo "📦 Installing additional libraries..."
conda install -y -n "$ENV_NAME" -c conda-forge \
  h5py hdf5plugin zarr pyarrow psutil plotly matplotlib seaborn \
  click tqdm statsmodels sqlalchemy scikit-learn pydantic pyodbc pymssql

echo "✅ Conda environment ready."
echo ""
echo "Next steps:"
echo "  conda activate $ENV_NAME"
echo "  pip install -e packages/methylutils --no-deps"
echo "  pip install -e packages/methylcentroid --no-deps"
echo "  pip install -e packages/methyldetector --no-deps"
echo "  pip install -e packages/methylmapper --no-deps"
echo "  pip install -e packages/methylclassifier --no-deps"
echo "  pip install -e packages/methylenricher --no-deps"
echo "  pip install -e packages/methylcluster --no-deps"
echo ""

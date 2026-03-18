# MethylPipeline Development Container
FROM nvidia/cuda:13.0.0-devel-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    bedtools \
    git \
    hdf5-tools \
    libhdf5-dev \
    libzstd-dev \
    curl \
    gnupg \
    apt-transport-https \
    unixodbc-dev \
    bzip2 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver 18 for SQL Server
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

# Install Miniforge (conda) and RAPIDS nightly for CUDA 13.0
ENV CONDA_DIR=/opt/conda
RUN curl -fsSL https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p $CONDA_DIR && \
    rm /tmp/miniforge.sh
ENV PATH="${CONDA_DIR}/bin:${PATH}"

RUN conda install -y -n base -c conda-forge mamba && \
    mamba create -y -n rapids-25.10 -c rapidsai-nightly -c conda-forge -c nvidia \
        rapids=25.10 python=3.12 'cuda-version=13.0' \
        jupyter hdbscan umap-learn && \
    mamba install -y -n rapids-25.10 -c conda-forge \
        h5py hdf5plugin zarr pyarrow psutil plotly matplotlib seaborn \
        click tqdm statsmodels sqlalchemy scikit-learn pydantic pyodbc pymssql && \
    conda clean -ay

ENV CONDA_DEFAULT_ENV=rapids-25.10
ENV PATH="/opt/conda/envs/rapids-25.10/bin:/opt/conda/bin:${PATH}"

# Install Python utilities not provided by conda
RUN pip install --no-cache-dir --retries 3 nvidia-ml-py rich sqlmodel

# Install Poetry (used by install_all.sh if enabled)
RUN pip install --no-cache-dir --retries 3 poetry && \
    poetry config virtualenvs.create false && \
    poetry config cache-dir /tmp/poetry-cache && \
    mkdir -p /tmp/poetry-cache && chmod 777 /tmp/poetry-cache && \
    poetry --version

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Set environment variables for optimization
ENV CUDA_VISIBLE_DEVICES=0 \
    OMP_NUM_THREADS=8 \
    MKL_NUM_THREADS=8 \
    NUMEXPR_NUM_THREADS=8 \
    PYTHONUNBUFFERED=1 \
    HDF5_USE_FILE_LOCKING=FALSE \
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
    POETRY_HOME=/tmp/poetry \
    POETRY_CACHE_DIR=/tmp/poetry-cache \
    POETRY_CONFIG_DIR=/tmp/poetry-config 

# Verify HDF5 installation
RUN python3 -c "import h5py; print(f'HDF5 version: {h5py.version.hdf5_version}'); print(f'h5py version: {h5py.version.version}'); print('HDF5 verification successful')"

# Health check - basic Python/CUDA check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import cupy, h5py; print('CUDA and HDF5 container ready')"

# Switch to root user and ensure proper home directory
USER root
RUN mkdir -p /root && chown root:root /root
WORKDIR /root

# Default command
CMD ["python3", "-c", "print('MethylPipeline development container ready - mount the repo at /workspace and run bash scripts/install_all.sh')"]

# MethylUtils CUDA-Optimized Container
FROM nvidia/cuda:12.8.0-devel-ubuntu22.04

# Install system dependencies including python3-pip
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    build-essential \
    git \
    hdf5-tools \
    libhdf5-dev \
    libzstd-dev \
    curl \
    gnupg \
    apt-transport-https \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip setuptools wheel

# Install Microsoft ODBC Driver 18 for SQL Server
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages with CUDA support
# Install pip and Poetry
# Configure Poetry to not use virtualenvs and set cache to /tmp for non-root users
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry config cache-dir /tmp/poetry-cache && \
    mkdir -p /tmp/poetry-cache && chmod 777 /tmp/poetry-cache && \
    poetry --version

# Install CuPy with CUDA 12.1 support
RUN pip install cupy-cuda12x

# Install core scientific and utility libraries in one layer
RUN pip install --no-cache-dir --retries 3 \
    numpy scipy pandas numba h5py pydantic psutil pyarrow tqdm cupy-cuda12x \
    scikit-learn statsmodels sqlalchemy plotly matplotlib seaborn \
    click nvidia-ml-py cudf-cu12 sqlmodel pyodbc pymssql hdf5plugin zarr

# Install pydantic from source to avoid zlib issues
RUN pip install --no-cache-dir --retries 3 --timeout 300 --no-binary pydantic,pydantic-core pydantic

# Install HDF5 and data libraries
RUN pip install --no-cache-dir --retries 3 h5py hdf5plugin zarr

# Install visualization libraries
RUN pip install --no-cache-dir --retries 3 plotly matplotlib seaborn

# Install utility libraries one by one
RUN pip install --no-cache-dir --retries 3 psutil
RUN pip install --no-cache-dir --retries 3 click
RUN pip install --no-cache-dir --retries 3 tqdm
RUN pip install --no-cache-dir --retries 3 rich

# Install statistical libraries
RUN pip install --no-cache-dir --retries 3 statsmodels sqlalchemy scikit-learn hdbscan

# Install NVIDIA libraries
RUN pip install --no-cache-dir --retries 3 nvidia-ml-py>=12.535.0

# Install SQL drivers (pyodbc for ODBC, pymssql as fallback for ARM64)
RUN pip install pyodbc || echo "pyodbc installation failed" && \
    pip install pymssql

# Install RAPIDS for GPU data frames (before numba to avoid conflicts)
RUN pip install cudf-cu12 --no-cache-dir

# Install numba after RAPIDS to avoid version conflicts
RUN pip install numba

# Install sqlmodel after all other packages
RUN pip install --no-cache-dir --retries 3 sqlmodel

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

# Health check - basic Python/CUDA check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import cupy; print('CUDA container ready')"

# Switch to root user and ensure proper home directory
USER root
RUN mkdir -p /root && chown root:root /root
WORKDIR /root

# Default command
CMD ["python3", "-c", "print('MethylUtils CUDA container ready - run setup_methyl_packages.sh to install packages')"]

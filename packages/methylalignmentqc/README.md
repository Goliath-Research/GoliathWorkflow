# MethylAlignmentQC

A Python package to parse NVIDIA Clara Parabricks alignment metrics into an optimized **Columnar JSON** format.

## Installation

```bash
pip install .
```

## Usage

### CLI

```bash
methyl-qc --metrics_root /path/to/metrics
```

### Python API

```python
from methyl_alignment_qc import build_alignment_qc_json
# ...
```

## Features
- Parses Picard-style QC metrics.
- Output: Columnar JSON (Structure of Arrays) for ~63% size reduction.
- Validates against internal JSON Schema.

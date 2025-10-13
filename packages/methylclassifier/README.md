# MethylClassifier

A command-line tool for Bayesian classification of methylation samples using probabilistic beta classifiers. This tool can classify methylation samples against multiple centroids and supports various methylation data formats.

## Features

- **Bayesian Classification**: Uses probabilistic beta classifiers for robust methylation-based classification
- **Multi-Centroid Support**: Classify samples against multiple reference centroids
- **Flexible Input**: Supports both single .h5 files and directories containing multiple samples
- **Comprehensive Output**: Detailed classification results with statistical information
- **Debug Mode**: Enhanced debugging capabilities for troubleshooting classification issues
- **Batch Processing**: Efficiently process large numbers of samples

## Installation

### From Source
```bash
git clone https://github.com/your-org/methylclassifier.git
cd methylclassifier
pip install -e .
```

### Requirements
- Python 3.7+
- numpy
- scipy
- pandas
- h5py
- matplotlib
- seaborn

## Usage

### Basic Classification
```bash
# Classify a single sample
methylclassifier --model classifier.pkl --input sample.h5

# Classify all samples in a directory
methylclassifier --model classifier.pkl --input samples/ --output results.csv
```

### Advanced Options
```bash
# Enable debug output
methylclassifier --model classifier.pkl --input sample.h5 --debug

# Process without chromosome/context filtering
methylclassifier --model classifier.pkl --input samples/ --no-filter --output results.csv

# Specify custom output location
methylclassifier --model classifier.pkl --input sample.h5 --output /path/to/results.csv
```

## Command Line Arguments

- `--model, -m`: Path to trained classifier model (.pkl file) [required]
- `--input, -i`: Path to input .h5 file or directory containing .h5 files [required]
- `--output, -o`: Optional output CSV file for classification results
- `--debug, -d`: Enable debug output for detailed analysis
- `--no-filter`: Process all .h5 files without chromosome/context filtering

## Output Format

The tool generates detailed classification results including:

- Sample name and type
- Predicted class and probabilities
- Coverage statistics
- DMP (Differentially Methylated Position) usage
- Statistical properties for centroid samples

Results can be saved to CSV format for further analysis.

## Development

### Setup Development Environment
```bash
pip install -e ".[dev]"
```

### Run Tests
```bash
pytest
```

### Code Formatting
```bash
black methylclassifier/
flake8 methylclassifier/
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Citation

If you use MethylClassifier in your research, please cite:

```
MethylClassifier: A Command Line Tool for Methylation-Based Sample Classification
[Your citation information here]
```

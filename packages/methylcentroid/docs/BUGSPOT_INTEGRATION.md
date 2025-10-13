# BugSpot Integration with Pull Requests

This document explains how to use BugSpot for automatic bug detection in pull requests for the MethylCentroid project.

## Overview

BugSpot is integrated into our development workflow to automatically detect potential bugs, code smells, and performance issues before code is merged. It runs on every pull request and provides detailed feedback to help maintain code quality.

## How It Works

### 1. Automatic Analysis on Pull Requests

When you create a pull request, GitHub Actions automatically:

1. **Checks out your code** with full history
2. **Runs BugSpot analysis** on changed Python files
3. **Generates a report** with potential issues
4. **Comments on the PR** with findings
5. **Uploads detailed artifacts** for further review

### 2. Pre-commit Hooks

Before committing, BugSpot runs locally to catch issues early:

```bash
# Install pre-commit hooks
poetry install
pre-commit install

# Now BugSpot runs automatically on every commit
git add .
git commit -m "Your commit message"
```

## Running BugSpot Locally

### Basic Usage

```bash
# Analyze entire project
python scripts/bugspot_analyzer.py .

# Analyze specific file
python scripts/bugspot_analyzer.py methylcentroid/methyl_centroid.py

# Analyze specific directory
python scripts/bugspot_analyzer.py methylcentroid/
```

### Integration with Poetry

```bash
# Install dependencies
poetry install

# Run BugSpot analysis
poetry run python scripts/bugspot_analyzer.py .
```

## What BugSpot Detects

### 1. **Division by Zero**
- Detects potential division by zero operations
- Suggests adding proper checks

### 2. **Array Operations**
- Large hardcoded array indices
- Potential out-of-bounds access

### 3. **GPU Memory Management**
- Missing GPU memory cleanup
- Improper GPU resource handling

### 4. **File Operations**
- Files not properly closed
- Missing context managers

### 5. **NumPy Operations**
- Large array creation without memory consideration
- Potential memory issues

### 6. **HDF5 Operations**
- HDF5 files not properly closed
- Missing error handling

### 7. **Memory Leaks**
- Large data structures without cleanup
- Potential memory management issues

### 8. **Error Handling**
- Missing try-except blocks
- Unhandled exceptions

## Understanding BugSpot Reports

### Report Format

BugSpot generates JSON reports with the following structure:

```json
{
  "project": "MethylCentroid",
  "total_issues": 5,
  "issues": [
    {
      "type": "division_by_zero",
      "severity": "high",
      "message": "Potential division by zero",
      "file": "methylcentroid/methyl_centroid.py",
      "line": 42,
      "suggestion": "Add a check to ensure the denominator is not zero"
    }
  ]
}
```

### Severity Levels

- **High**: Critical issues that could cause crashes or data loss
- **Medium**: Issues that might cause problems in certain conditions
- **Low**: Code smells or potential improvements

## Fixing BugSpot Issues

### 1. Division by Zero

**Issue:**
```python
result = numerator / denominator  # Potential division by zero
```

**Fix:**
```python
if denominator != 0:
    result = numerator / denominator
else:
    result = 0  # or handle appropriately
```

### 2. File Operations

**Issue:**
```python
file = open('data.txt', 'r')
data = file.read()
# Missing file.close()
```

**Fix:**
```python
with open('data.txt', 'r') as file:
    data = file.read()
```

### 3. GPU Memory Management

**Issue:**
```python
import cupy as cp
data = cp.array(large_dataset)
# Missing memory cleanup
```

**Fix:**
```python
import cupy as cp
data = cp.array(large_dataset)
try:
    # Process data
    result = process_gpu_data(data)
finally:
    del data
    cp.get_default_memory_pool().free_all_blocks()
```

### 4. Error Handling

**Issue:**
```python
data = h5py.File('data.h5', 'r')
```

**Fix:**
```python
try:
    with h5py.File('data.h5', 'r') as data:
        # Process data
        pass
except FileNotFoundError:
    print("Data file not found")
except Exception as e:
    print(f"Error reading data: {e}")
```

## Configuration

### BugSpot Configuration (.bugspotrc)

The `.bugspotrc` file configures BugSpot behavior:

```json
{
  "project": "MethylCentroid",
  "language": "python",
  "analysis": {
    "patterns": ["*.py"],
    "exclude": ["**/__pycache__/**", "**/tests/**"]
  },
  "rules": {
    "enabled": ["potential-bug", "code-smell", "performance-issue"],
    "severity": {
      "potential-bug": "medium",
      "code-smell": "low"
    }
  }
}
```

### GitHub Actions Configuration

The `.github/workflows/bugspot.yml` file configures automatic analysis:

- Runs on pull requests and pushes to main/develop
- Uses Python 3.11
- Installs dependencies with Poetry
- Runs custom BugSpot analyzer
- Comments results on PRs

## Best Practices

### 1. **Run BugSpot Before Submitting PRs**
```bash
# Always run locally first
python scripts/bugspot_analyzer.py .
```

### 2. **Address High and Medium Severity Issues**
- Fix high severity issues before submitting PRs
- Address medium severity issues when possible
- Document why low severity issues are acceptable

### 3. **Use Pre-commit Hooks**
```bash
# Install pre-commit hooks
pre-commit install

# This will run BugSpot automatically on commits
```

### 4. **Review BugSpot Comments on PRs**
- Check the automatic BugSpot comments
- Address any issues found
- Discuss issues that can't be fixed immediately

### 5. **Customize Rules for Your Code**
- Update `.bugspotrc` for project-specific needs
- Add ignore patterns for false positives
- Adjust severity levels as needed

## Troubleshooting

### Common Issues

1. **False Positives**
   - Add ignore patterns in `.bugspotrc`
   - Document why certain patterns are acceptable

2. **Performance Issues**
   - BugSpot analysis can be slow on large files
   - Consider analyzing only changed files in PRs

3. **Missing Dependencies**
   - Ensure all dependencies are installed: `poetry install`
   - Check Python version compatibility

### Getting Help

- Check the BugSpot report artifacts in GitHub Actions
- Review the custom analyzer code in `scripts/bugspot_analyzer.py`
- Update configuration in `.bugspotrc` as needed

## Integration with Other Tools

BugSpot works alongside other code quality tools:

- **Black**: Code formatting
- **Flake8**: Linting
- **MyPy**: Type checking
- **Pre-commit**: Automated checks

All tools run together in the pre-commit hooks and GitHub Actions workflow.

## Contributing to BugSpot Rules

To add new detection rules:

1. Edit `scripts/bugspot_analyzer.py`
2. Add new check methods
3. Update the main analysis function
4. Test with your changes
5. Submit a PR with the improvements

## Conclusion

BugSpot integration helps maintain code quality by catching potential issues early in the development process. By running automatically on pull requests and locally before commits, it ensures that code quality issues are addressed before they reach production. 
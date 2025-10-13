# MethylClassifier Repository Setup Guide

This guide will help you create the new MethylClassifier repository in Azure DevOps using the same credentials and setup as MethylUtils.

## Prerequisites

- Azure CLI installed (`az` command available)
- SSH keys configured for Azure DevOps
- Access to EpiMethyl Azure DevOps organization

## Option 1: Automated Setup (Recommended)

Run the automated setup script:

```bash
cd /home/ubuntu/MethylClassifier
./setup_repository.sh
```

The script will:
1. Authenticate with Azure CLI
2. Create the repository in Azure DevOps
3. Initialize git locally
4. Configure user settings
5. Commit all files
6. Push to the remote repository

## Option 2: Manual Setup

If you prefer to do it step by step:

### Step 1: Authenticate with Azure CLI

```bash
az login
```

This will open a browser window for authentication. Use your EpiMethyl credentials.

### Step 2: Create the Repository

```bash
az repos create \
  --organization https://dev.azure.com/EpiMethyl \
  --project Development \
  --name MethylClassifier \
  --open-source true
```

### Step 3: Initialize Git Repository

```bash
cd /home/ubuntu/MethylClassifier

# Initialize git
git init

# Configure user (same as MethylUtils)
git config user.name "David Izada Rodriguez"
git config user.email "dizada@epimethyl.com"

# Add all files
git add .

# Initial commit
git commit -m "Initial commit: MethylClassifier CLI application

- Standalone command-line tool for methylation-based sample classification
- Supports Bayesian classification with multiple centroids
- Modular architecture with abstract data loading
- Compatible with existing methyl_utils classifiers
- Comprehensive CLI with detailed output and debugging"
```

### Step 4: Connect to Azure DevOps

Get the SSH clone URL from the Azure DevOps web interface:

1. Go to: https://dev.azure.com/EpiMethyl/Development/_git/MethylClassifier
2. Click "Clone" in the top-right
3. Copy the SSH URL (should be: `git@ssh.dev.azure.com:v3/EpiMethyl/Development/MethylClassifier`)

Then add the remote and push:

```bash
# Add remote
git remote add origin git@ssh.dev.azure.com:v3/EpiMethyl/Development/MethylClassifier

# Push to main branch
git push -u origin main
```

## Verification

After setup, verify everything is working:

```bash
# Check repository status
git status
git remote -v

# Visit the repository
# https://dev.azure.com/EpiMethyl/Development/_git/MethylClassifier
```

## Repository Structure

Your new repository will contain:

- `methylclassifier/` - Main Python package
- `tests/` - Test suite
- `setup.py` - Package configuration
- `requirements.txt` - Dependencies
- `README.md` - Documentation
- `setup_repository.sh` - Setup automation script
- `REPOSITORY_SETUP.md` - This guide

## Next Steps

1. **Set up CI/CD Pipeline**: Consider creating an Azure Pipeline for automated testing
2. **Configure Branch Policies**: Set up branch protection and review requirements
3. **Add Collaborators**: Grant access to team members as needed
4. **Create Documentation**: Update README with usage examples and API documentation

## Troubleshooting

### SSH Key Issues
If you get SSH-related errors:
```bash
# Check SSH keys
ls -la ~/.ssh/

# Test SSH connection to Azure DevOps
ssh -T git@ssh.dev.azure.com
```

### Azure CLI Issues
If Azure CLI commands fail:
```bash
# Check login status
az account show

# Re-login if needed
az login
```

### Permission Issues
If you don't have permission to create repositories:
- Contact your Azure DevOps administrator
- Request repository creation permissions for the EpiMethyl organization

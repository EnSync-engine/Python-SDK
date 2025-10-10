#!/bin/bash

# EnSync SDK Deployment Script
# This script builds and deploys the ensync-sdk package to PyPI

set -e  # Exit on error

echo "=========================================="
echo "EnSync SDK Deployment Script"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "setup.py" ]; then
    echo "Error: setup.py not found. Please run this script from the project root."
    exit 1
fi

# Get the current version from setup.py
VERSION=$(grep "version=" setup.py | head -1 | sed 's/.*version="\(.*\)".*/\1/')
echo "Current version: $VERSION"
echo ""

# Confirm deployment
read -p "Deploy version $VERSION to PyPI? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "Step 1: Cleaning old builds..."
rm -rf dist/ build/ *.egg-info ensync.egg-info

echo "Step 2: Building package..."
python3 setup.py sdist bdist_wheel

echo ""
echo "Step 3: Checking package with twine..."
python3 -m twine check dist/*

echo ""
echo "Step 4: Uploading to PyPI..."
python3 -m twine upload dist/*

echo ""
echo "=========================================="
echo "✅ Deployment complete!"
echo "Version $VERSION is now available on PyPI"
echo "=========================================="
echo ""
echo "Install with: pip install ensync-sdk==$VERSION"

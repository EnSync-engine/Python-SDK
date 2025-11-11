#!/bin/bash

# EnSync SDK Multi-Package Deployment Script
# This script builds and deploys all three EnSync packages to PyPI

set -e  # Exit on error

echo "=========================================="
echo "EnSync SDK Multi-Package Deployment"
echo "=========================================="
echo ""

# Array of packages in dependency order (core must be first)
PACKAGES=("ensync-core" "ensync-sdk-ws" "ensync-sdk")

# Function to get version from setup.py
get_version() {
    local package_dir=$1
    grep "version=" "$package_dir/setup.py" | head -1 | sed 's/.*version="\(.*\)".*/\1/'
}

# Function to deploy a package
deploy_package() {
    local package_dir=$1
    local package_name=$(basename "$package_dir")
    
    echo ""
    echo "=========================================="
    echo "Deploying: $package_name"
    echo "=========================================="
    
    cd "$package_dir"
    
    # Get version
    VERSION=$(get_version ".")
    echo "Version: $VERSION"
    
    # Confirm deployment
    read -p "Deploy $package_name v$VERSION to PyPI? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping $package_name"
        cd ..
        return
    fi
    
    # Clean old builds
    echo "Cleaning old builds..."
    rm -rf dist/ build/ *.egg-info
    
    # Build package
    echo "Building package..."
    python3 -m build
    
    # Check package
    echo "Checking package with twine..."
    python3 -m twine check dist/*
    
    # Upload to PyPI
    echo "Uploading to PyPI..."
    python3 -m twine upload dist/*
    
    echo "✅ $package_name v$VERSION deployed successfully!"
    
    cd ..
}

# Check if we're in the right directory
if [ ! -d "ensync-core" ] || [ ! -d "ensync-sdk-ws" ] || [ ! -d "ensync-sdk" ]; then
    echo "Error: Package directories not found. Please run this script from the project root."
    exit 1
fi

# Check if twine is installed
if ! command -v twine &> /dev/null; then
    echo "Error: twine is not installed. Install it with: pip install twine"
    exit 1
fi

echo "This script will deploy packages in the following order:"
for package in "${PACKAGES[@]}"; do
    VERSION=$(get_version "$package")
    echo "  - $package (v$VERSION)"
done
echo ""
echo "⚠️  IMPORTANT: ensync-sdk-ws must be deployed first as other packages depend on it!"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Deploy each package
for package in "${PACKAGES[@]}"; do
    deploy_package "$package"
done

echo ""
echo "=========================================="
echo "✅ All packages deployed successfully!"
echo "=========================================="
echo ""
echo "Installation commands:"
echo "  For gRPC client:"
echo "    pip install ensync-sdk"
echo ""
echo "  For WebSocket client:"
echo "    pip install ensync-sdk-ws"
echo ""
echo "  Note: ensync-core is automatically installed as a dependency"
echo ""

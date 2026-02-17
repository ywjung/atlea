#!/bin/bash

# Setup script for Linux with NVIDIA GPU
# This script automates the installation process

set -e  # Exit on error

echo "================================================"
echo "RAG Chatbot - Linux NVIDIA GPU Setup"
echo "================================================"
echo ""

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "❌ Error: This script is for Linux systems only"
    exit 1
fi

# Check for NVIDIA GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  Warning: nvidia-smi not found. Make sure NVIDIA drivers are installed."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    echo ""
fi

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Error: Python $REQUIRED_VERSION or higher required (found $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python version: $PYTHON_VERSION"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
echo "✅ Virtual environment created"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel
echo "✅ Pip upgraded"
echo ""

# Install PyTorch with CUDA support
echo "Installing PyTorch with CUDA 12.1 support..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo "✅ PyTorch with CUDA installed"
echo ""

# Install other dependencies
echo "Installing other dependencies..."
pip install -r requirements-linux.txt
echo "✅ Dependencies installed"
echo ""

# Verify CUDA availability
echo "Verifying CUDA availability..."
python3 << EOF
import torch
cuda_available = torch.cuda.is_available()
print(f"CUDA available: {cuda_available}")
if cuda_available:
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
else:
    print("⚠️  Warning: CUDA not available. Will use CPU.")
EOF
echo ""

# Check Docker for PostgreSQL
echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
    echo "✅ Docker installed (re-login required for group membership)"
else
    echo "✅ Docker already installed"
fi
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p data model logs
echo "✅ Directories created"
echo ""

# Setup environment file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created (please edit with your settings)"
else
    echo "✅ .env file already exists"
fi
echo ""

# Start PostgreSQL via Docker
echo "Starting PostgreSQL..."
if docker-compose up -d postgres 2>/dev/null; then
    echo "✅ PostgreSQL started via Docker"
else
    echo "⚠️  Warning: Could not start PostgreSQL"
    echo "Start with: docker-compose up -d"
fi
echo ""

echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run server: python -m src.web_server"
echo ""
echo "For Docker deployment:"
echo "  docker-compose -f docker-compose.gpu.yml up -d"
echo ""
echo "For more information, see DEPLOYMENT_GUIDE.md"
echo ""

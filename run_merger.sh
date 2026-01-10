#!/bin/bash

# PDFInvoiceMerger macOS Launch Script

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Error: python3 is not installed. Please install Python 3."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing/Updating dependencies..."
pip install -r requirements.txt

# Run the application
echo "Starting PDFInvoiceMerger..."
python3 main.py

#!/bin/bash

# Create directory structure
mkdir -p src/models
mkdir -p src/services
mkdir -p src/utils

# Create __init__.py files
touch src/__init__.py
touch src/models/__init__.py
touch src/services/__init__.py
touch src/utils/__init__.py

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "Project structure set up complete!"
#!/bin/bash
# This script installs the Twilio Python SDK into a local
# Lambda layer.

set -e

# Get exact versions from your environment
pip freeze | grep -E "(twilio|PyJWT|requests|urllib3|certifi|charset-normalizer|idna)" > layer-requirements.txt

# Create layer structure
mkdir twilio-layer || cd twilio-layer
mkdir python   || true

# Install exact versions to layer
pip install -r ../layer-requirements.txt -t python/
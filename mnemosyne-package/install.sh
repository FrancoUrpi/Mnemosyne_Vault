#!/bin/bash
# Mnemosyne Knowledge Vault — One-Click Installer
#
# Usage: bash install.sh
#
# This script:
# 1. Patches Hermes Agent (adds vault tool support)
# 2. Installs vault tool, skill, CLI, and vault structure
# 3. Tells you to restart the agent

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "Mnemosyne Knowledge Vault — Installer"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Install PyYAML if missing
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "Installing PyYAML..."
    pip3 install pyyaml -q
fi

# Patch Hermes
echo ""
echo "Step 1/2: Patching Hermes Agent..."
python3 patch_hermes.py

# Install vault
echo ""
echo "Step 2/2: Installing vault..."
python3 setup_vault.py

echo ""
echo "============================================================"
echo "DONE! Restart the agent to activate the vault tool."
echo "============================================================"

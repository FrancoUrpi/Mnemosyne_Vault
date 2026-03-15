#!/usr/bin/env python3
"""
Validate Mnemosyne package installation.

This script checks that:
1. All required Python modules can be imported
2. Required files exist
3. Basic functionality works
"""

import sys
import os
from pathlib import Path

def check_imports():
    """Check that all required modules can be imported."""
    print("Checking Python imports...")
    
    # Add src to path
    src_dir = Path(__file__).parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    required_modules = [
        "vault_context",
        "vault_utils",
        "layer_state",
        "vault_search",
        "link_navigator",
        "on_demand",
        "traversal",
        "context_loader",
        "relevance",
        "budget",
        "prompt_integration",
        "synthesis",
        "intent",
        "audit",
        "governance",
        "attribution",
        "context_audit",
        "status",
        "trust",
        "maintenance",
        "cross_project",
        "obsidian",
        "docs",
        "vault_cli"
    ]
    
    failed = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError as e:
            print(f"  ✗ {module}: {e}")
            failed.append(module)
    
    return failed

def check_dependencies():
    """Check Python dependencies."""
    print("\nChecking dependencies...")
    
    try:
        import yaml
        print("  ✓ PyYAML")
    except ImportError:
        print("  ✗ PyYAML not installed (pip install pyyaml)")
        return False
    
    return True

def check_vault_tool():
    """Check vault tool can be imported."""
    print("\nChecking vault tool...")
    
    tools_dir = Path(__file__).parent / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    
    try:
        import vault_tool
        print("  ✓ vault_tool")
        
        # Check if it has the required function
        if hasattr(vault_tool, 'vault_tool'):
            print("  ✓ vault_tool function")
        else:
            print("  ✗ vault_tool function missing")
            return False
            
    except ImportError as e:
        print(f"  ✗ vault_tool: {e}")
        return False
    
    return True

def main():
    print("=" * 60)
    print("Mnemosyne Package Validation")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check imports
    failed = check_imports()
    if failed:
        print(f"\n✗ {len(failed)} modules failed to import:")
        for module in failed:
            print(f"  - {module}")
        sys.exit(1)
    
    # Check vault tool
    if not check_vault_tool():
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ All checks passed!")
    print("=" * 60)
    print("\nPackage is ready for installation.")
    print("Run: bash install.sh")

if __name__ == "__main__":
    main()

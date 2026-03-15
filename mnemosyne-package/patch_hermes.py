#!/usr/bin/env python3
"""
Patch Hermes Agent to enable Mnemosyne vault support.

This script applies three modifications:
1. model_tools.py — Add external tool discovery (~/.hermes/external_tools/)
2. toolsets.py — Add 'vault' to _HERMES_CORE_TOOLS and TOOLSETS
3. config.yaml — Add 'vault' to platform_toolsets (cli + telegram)

Usage:
    python3 patch_hermes.py [--hermes-path PATH] [--dry-run] [--revert]

Options:
    --hermes-path PATH  Path to hermes-agent directory (default: ~/.hermes/hermes-agent)
    --dry-run           Show what would be changed without modifying files
    --revert            Remove the patches (restore original files)

These patches are required for Mnemosyne to work. Without them, the vault
tool will not appear in the agent's tool list.
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime


# =============================================================================
# Patch Definitions
# =============================================================================

PATCH_MODEL_TOOLS_OLD = """\
    _discover_tools()

# MCP tool discovery"""

PATCH_MODEL_TOOLS_NEW = """\
    _discover_tools()

# External tool discovery (~/.hermes/external_tools/ for user-installed tools)
import importlib.util as _ext_util
_external_tools_dir = Path.home() / ".hermes" / "external_tools"
if _external_tools_dir.is_dir():
    for _py in sorted(_external_tools_dir.glob("*_tool.py")):
        try:
            _spec = _ext_util.spec_from_file_location(f"external_tools.{_py.stem}", _py)
            if _spec and _spec.loader:
                _mod = _ext_util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                logger.debug("Loaded external tool: %s", _py.name)
        except Exception as e:
            logger.warning("Failed to load external tool %s: %s", _py.name, e)

# MCP tool discovery"""

PATCH_MODEL_TOOLS_IMPORT = """\
import asyncio
import os
import logging
from typing import Dict, Any, List, Optional, Tuple"""

PATCH_MODEL_TOOLS_IMPORT_NEW = """\
import asyncio
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple"""


PATCH_TOOLSETS_OLD = """\
    # Planning & memory
    \"todo\", \"memory\",
    # Session history search"""

PATCH_TOOLSETS_NEW = """\
    # Planning & memory
    \"todo\", \"memory\",
    # Knowledge vault
    \"vault\",
    # Session history search"""


PATCH_TOOLSETS_SECTION_OLD = """\
    },
    
    \"session_search\": {"""

PATCH_TOOLSETS_SECTION_NEW = """\
    },
    
    \"vault\": {
        "description": "Mnemosyne Knowledge Vault — structured project memory with L1-L4 layers, research, decisions, and synthesis",
        "tools": ["vault"],
        "includes": []
    },
    
    "session_search": {"""


# --- config.yaml platform_toolsets patch ---

PATCH_CONFIG_CLI_OLD = """\
  cli:
  - browser
  - clarify
  - code_execution
  - cronjob
  - delegation
  - file
  - image_gen
  - memory
  - moa
  - rl
  - session_search
  - skills
  - terminal
  - todo
  - tts
  - vision
  - web"""

PATCH_CONFIG_CLI_NEW = """\
  cli:
  - browser
  - clarify
  - code_execution
  - cronjob
  - delegation
  - file
  - image_gen
  - memory
  - moa
  - rl
  - session_search
  - skills
  - terminal
  - todo
  - tts
  - vault
  - vision
  - web"""

PATCH_CONFIG_TG_OLD = """\
  telegram:
  - browser
  - clarify
  - code_execution
  - cronjob
  - delegation
  - file
  - image_gen
  - memory
  - session_search
  - skills
  - terminal
  - todo
  - tts
  - vision
  - web"""

PATCH_CONFIG_TG_NEW = """\
  telegram:
  - browser
  - clarify
  - code_execution
  - cronjob
  - delegation
  - file
  - image_gen
  - memory
  - session_search
  - skills
  - terminal
  - todo
  - tts
  - vault
  - vision
  - web"""


# =============================================================================
# Patch Application
# =============================================================================

def backup_file(path: Path) -> Path:
    """Create a timestamped backup of a file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".{timestamp}.bak")
    shutil.copy2(str(path), str(backup))
    return backup


def patch_model_tools(path: Path, dry_run: bool = False) -> bool:
    """Apply patches to model_tools.py."""
    content = path.read_text()
    
    # Check if already patched
    if "External tool discovery" in content and "_external_tools_dir" in content:
        print("  model_tools.py: Already patched ✓")
        return True
    
    # Check if patchable
    if PATCH_MODEL_TOOLS_OLD not in content:
        print("  model_tools.py: Cannot find patch target (code may have changed)")
        print("    Looking for: '_discover_tools()' followed by '# MCP tool discovery'")
        return False
    
    if PATCH_MODEL_TOOLS_IMPORT not in content:
        print("  model_tools.py: Cannot find import section to patch")
        return False
    
    if dry_run:
        print("  model_tools.py: Would add external tool discovery (+15 lines)")
        print("  model_tools.py: Would add 'from pathlib import Path' import")
        return True
    
    # Apply patches
    backup = backup_file(path)
    
    # Add Path import
    content = content.replace(PATCH_MODEL_TOOLS_IMPORT, PATCH_MODEL_TOOLS_IMPORT_NEW)
    
    # Add external tool discovery
    content = content.replace(PATCH_MODEL_TOOLS_OLD, PATCH_MODEL_TOOLS_NEW)
    
    path.write_text(content)
    print(f"  model_tools.py: Patched ✓ (backup: {backup.name})")
    return True


def patch_toolsets(path: Path, dry_run: bool = False) -> bool:
    """Apply patches to toolsets.py."""
    content = path.read_text()
    
    # Check if already patched
    if '"vault"' in content and "'vault'" in content:
        print("  toolsets.py: Already patched ✓")
        return True
    
    if '"vault"' in content:
        # Check if fully patched (both in CORE_TOOLS and TOOLSETS)
        if '"vault": {' in content or "'vault': {" in content:
            print("  toolsets.py: Already patched ✓")
            return True
    
    # Check if patchable
    core_ok = PATCH_TOOLSETS_OLD in content
    section_ok = PATCH_TOOLSETS_SECTION_OLD in content
    
    if not core_ok and not section_ok:
        print("  toolsets.py: Cannot find patch targets (code may have changed)")
        return False
    
    if dry_run:
        if core_ok:
            print("  toolsets.py: Would add 'vault' to _HERMES_CORE_TOOLS")
        if section_ok:
            print("  toolsets.py: Would add 'vault' toolset definition")
        return True
    
    # Apply patches
    backup = backup_file(path)
    
    if core_ok:
        content = content.replace(PATCH_TOOLSETS_OLD, PATCH_TOOLSETS_NEW)
    
    if section_ok:
        content = content.replace(PATCH_TOOLSETS_SECTION_OLD, PATCH_TOOLSETS_SECTION_NEW)
    
    path.write_text(content)
    print(f"  toolsets.py: Patched ✓ (backup: {backup.name})")
    return True


def patch_config_yaml(path: Path, dry_run: bool = False) -> bool:
    """Add 'vault' to platform_toolsets for cli and telegram in config.yaml."""
    content = path.read_text()

    # Check if already patched
    cli_patched = "vault" in content and PATCH_CONFIG_CLI_OLD not in content
    tg_patched = "vault" in content and PATCH_CONFIG_TG_OLD not in content

    # More precise: check if vault appears in both cli and telegram sections
    import re
    cli_section = re.search(r'cli:\n((?:  - \w+\n)+)', content)
    tg_section = re.search(r'telegram:\n((?:  - \w+\n)+)', content)
    cli_has_vault = cli_section and 'vault' in cli_section.group(1)
    tg_has_vault = tg_section and 'vault' in tg_section.group(1)

    if cli_has_vault and tg_has_vault:
        print("  config.yaml: Already patched ✓")
        return True

    if dry_run:
        if not cli_has_vault:
            print("  config.yaml: Would add 'vault' to cli platform_toolsets")
        if not tg_has_vault:
            print("  config.yaml: Would add 'vault' to telegram platform_toolsets")
        return True

    # Apply patches
    backup = backup_file(path)

    if not cli_has_vault and PATCH_CONFIG_CLI_OLD in content:
        content = content.replace(PATCH_CONFIG_CLI_OLD, PATCH_CONFIG_CLI_NEW)

    if not tg_has_vault and PATCH_CONFIG_TG_OLD in content:
        content = content.replace(PATCH_CONFIG_TG_OLD, PATCH_CONFIG_TG_NEW)

    path.write_text(content)
    print(f"  config.yaml: Patched ✓ (backup: {backup.name})")
    return True


def revert_file(path: Path) -> bool:
    """Revert a file to its most recent backup."""
    # Find most recent backup
    backups = sorted(path.parent.glob(f"{path.stem}.*.bak"), reverse=True)
    if not backups:
        print(f"  {path.name}: No backup found")
        return False
    
    backup = backups[0]
    shutil.copy2(str(backup), str(path))
    print(f"  {path.name}: Reverted from {backup.name} ✓")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Patch Hermes Agent for Mnemosyne support")
    parser.add_argument("--hermes-path", default="~/.hermes/hermes-agent",
                        help="Path to hermes-agent directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be changed")
    parser.add_argument("--revert", action="store_true",
                        help="Revert patches to original")
    args = parser.parse_args()
    
    hermes_path = Path(os.path.expanduser(args.hermes_path))
    
    print("=" * 60)
    if args.revert:
        print("Mnemosyne Hermes Patcher — REVERT")
    else:
        print("Mnemosyne Hermes Patcher")
    print("=" * 60)
    
    # Check hermes-agent exists
    if not hermes_path.exists():
        print(f"\nError: Hermes Agent not found at {hermes_path}")
        print("Install hermes-agent first: https://github.com/nous-hermes/hermes-agent")
        sys.exit(1)
    
    model_tools = hermes_path / "model_tools.py"
    toolsets = hermes_path / "toolsets.py"
    config_yaml = Path.home() / ".hermes" / "config.yaml"

    if not model_tools.exists() or not toolsets.exists():
        print(f"\nError: Required files not found in {hermes_path}")
        print(f"  model_tools.py: {'✓' if model_tools.exists() else '✗'}")
        print(f"  toolsets.py: {'✓' if toolsets.exists() else '✗'}")
        sys.exit(1)
    if not config_yaml.exists():
        print(f"\nWarning: config.yaml not found at {config_yaml}")
        print("  platform_toolsets patch will be skipped")
    
    print(f"\nHermes path: {hermes_path}")
    
    if args.dry_run:
        print("\nDRY RUN — no files will be modified\n")
    
    if args.revert:
        print("\nReverting patches...")
        revert_file(model_tools)
        revert_file(toolsets)
        revert_file(config_yaml)
        print("\nDone. Restart agent to apply.")
        return
    
    print("\nPatching files...")
    ok1 = patch_model_tools(model_tools, args.dry_run)
    ok2 = patch_toolsets(toolsets, args.dry_run)
    ok3 = patch_config_yaml(config_yaml, args.dry_run)
    
    print()
    print("=" * 60)
    if args.dry_run:
        print("Dry run complete. Run without --dry-run to apply.")
    elif ok1 and ok2 and ok3:
        print("✓ Patches applied successfully!")
        print()
        print("Next steps:")
        print("  1. Restart the Hermes agent")
        print("  2. Run: python3 setup_vault.py")
        print("  3. The 'vault' tool will appear in the tool list")
    else:
        print("✗ Some patches failed. Check errors above.")
        print("  You may need to apply patches manually.")
        print("  See MANUAL_PATCHES.md for instructions.")
        sys.exit(1)


if __name__ == "__main__":
    main()

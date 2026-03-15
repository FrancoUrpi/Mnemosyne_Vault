#!/usr/bin/env python3
"""
Mnemosyne Vault Setup Script

Initializes the Mnemosyne Knowledge Vault for use with Hermes Agent.

Usage:
    python3 setup_vault.py [--vault-path PATH] [--skip-deps]

What it does:
    1. Creates vault directory structure (~/.hermes/memory/)
    2. Installs vault_tool.py to external_tools/
    3. Installs mnemosyne skill to skills/
    4. Creates vault CLI wrapper
    5. Sets up Obsidian configuration
    6. Creates example project

Requirements:
    - Hermes Agent installed at ~/.hermes/hermes-agent/
    - PyYAML (pip install pyyaml)

After setup, restart the agent for the vault tool to appear.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SRC_DIR = SCRIPT_DIR / "src"
TEMPLATES_DIR = SCRIPT_DIR / "templates"

DEFAULT_VAULT = Path.home() / ".hermes" / "memory"
HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
HERMES_SKILLS = Path.home() / ".hermes" / "skills"
EXTERNAL_TOOLS = Path.home() / ".hermes" / "external_tools"
WORKSPACE = Path.home() / ".hermes" / "workspace"
HERMES_AGENT = Path.home() / ".hermes" / "hermes-agent"


def check_requirements():
    """Check that requirements are met."""
    errors = []

    # Check hermes-agent exists
    if not HERMES_AGENT.exists():
        errors.append(f"Hermes Agent not found at {HERMES_AGENT}")
    
    # Check toolsets.py has vault
    toolsets = HERMES_AGENT / "toolsets.py"
    if toolsets.exists():
        content = toolsets.read_text()
        if '"vault"' not in content and "'vault'" not in content:
            errors.append("toolsets.py missing 'vault' in _HERMES_CORE_TOOLS")
    
    # Check model_tools.py has external tool discovery
    model_tools = HERMES_AGENT / "model_tools.py"
    if model_tools.exists():
        content = model_tools.read_text()
        if "external_tools" not in content:
            errors.append("model_tools.py missing external tool discovery")

    # Check PyYAML
    try:
        import yaml
    except ImportError:
        errors.append("PyYAML not installed (pip install pyyaml)")

    return errors


def install_dependencies():
    """Install Python dependencies."""
    try:
        import yaml
        print("  PyYAML already installed")
    except ImportError:
        print("  Installing PyYAML...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
        print("  PyYAML installed")


def create_vault_structure(vault_path: Path):
    """Create the vault directory structure."""
    dirs = [
        vault_path / "projects",
        vault_path / "concepts",
        vault_path / "decisions",
        vault_path / "user" / ".private",
        vault_path / "archive",
        vault_path / "attribution",
        vault_path / "context_audit",
        vault_path / "trust",
        vault_path / "alerts",
        vault_path / "governance",
        vault_path / "docs",
        vault_path / "attachments",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # .gitignore
    gitignore = vault_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("""# Mnemosyne Vault
.obsidian/workspace*.json
*.tmp
""", encoding="utf-8")

    # _index.md
    index = vault_path / "_index.md"
    if not index.exists():
        index.write_text("""---
id: _index
type: index
layer: cross
updated: 2026-03-13
---

# Mnemosyne Knowledge Vault

## Projects
_(none yet)_

## Concepts
_(none yet)_

## User
- [[active_context|Current Context]]
""", encoding="utf-8")

    # _inbox.md
    inbox = vault_path / "_inbox.md"
    if not inbox.exists():
        inbox.write_text("""---
id: _inbox
type: context
layer: cross
---

# Inbox
Quick captures and unprocessed items.
""", encoding="utf-8")

    # user/active_context.md
    active = vault_path / "user" / "active_context.md"
    if not active.exists():
        active.write_text("""---
id: active_context
type: context
layer: cross
---

# Active Context
**Current project:** _(none)_
**Last activity:** _(never)_
""", encoding="utf-8")

    # user/preferences.md
    prefs = vault_path / "user" / "preferences.md"
    if not prefs.exists():
        prefs.write_text("""---
id: preferences
type: context
layer: cross
---

# User Preferences
_(to be filled by agent as it learns)_
""", encoding="utf-8")

    print(f"  Vault structure created at {vault_path}")


def install_scripts(vault_path: Path):
    """Install vault CLI scripts."""
    HERMES_SCRIPTS.mkdir(parents=True, exist_ok=True)

    # Copy vault_cli.py as 'vault' command
    cli_src = SRC_DIR / "vault_cli.py"
    cli_dest = HERMES_SCRIPTS / "vault"

    # Create wrapper script
    wrapper = f"""#!/bin/bash
# Mnemosyne Vault CLI
export PYTHONPATH="{SRC_DIR}:$PYTHONPATH"
python3 "{cli_src}" "$@"
"""
    cli_dest.write_text(wrapper, encoding="utf-8")
    cli_dest.chmod(0o755)

    print(f"  CLI installed to {cli_dest}")


def install_vault_tool():
    """Install vault_tool.py to external_tools directory for agent discovery."""
    EXTERNAL_TOOLS.mkdir(parents=True, exist_ok=True)

    # Look for vault_tool.py in common locations
    candidates = [
        SCRIPT_DIR.parent / "external_tools" / "vault_tool.py",
        SCRIPT_DIR / "vault_tool.py",
        SCRIPT_DIR / "src" / "vault_tool.py",
    ]
    
    tool_src = None
    for c in candidates:
        if c.exists():
            tool_src = c
            break
    
    tool_dest = EXTERNAL_TOOLS / "vault_tool.py"

    if tool_src:
        shutil.copy2(str(tool_src), str(tool_dest))
        print(f"  vault_tool.py installed to {tool_dest}")
    else:
        print(f"  WARNING: vault_tool.py not found — skipped")
        print(f"    Searched: {[str(c) for c in candidates]}")


def install_skill():
    """Install mnemosyne skill to skills directory."""
    skill_dir = HERMES_SKILLS / "mnemosyne"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "references").mkdir(exist_ok=True)

    # Copy SKILL.md
    skill_src = SCRIPT_DIR.parent / "skills" / "mnemosyne" / "SKILL.md"
    if not skill_src.exists():
        skill_src = SCRIPT_DIR / "skills" / "mnemosyne" / "SKILL.md"
    
    if skill_src.exists():
        shutil.copy2(str(skill_src), str(skill_dir / "SKILL.md"))
        print(f"  SKILL.md installed to {skill_dir}")
    else:
        print(f"  WARNING: SKILL.md not found — skipped")

    # Copy references
    ref_src = SCRIPT_DIR.parent / "skills" / "mnemosyne" / "references"
    if not ref_src.exists():
        ref_src = SCRIPT_DIR / "skills" / "mnemosyne" / "references"
    
    if ref_src.exists():
        for f in ref_src.glob("*.md"):
            shutil.copy2(str(f), str(skill_dir / "references" / f.name))
        print(f"  References installed to {skill_dir / 'references'}")
    else:
        print(f"  WARNING: references/ not found — skipped")


def install_agents_guide():
    """Copy AGENTS.md to workspace."""
    src = SCRIPT_DIR.parent / "AGENTS.md" if (SCRIPT_DIR.parent / "AGENTS.md").exists() else SCRIPT_DIR / "AGENTS.md"
    dest = WORKSPACE / "AGENTS.md"

    # AGENTS.md should already be in workspace from our write
    if dest.exists():
        print(f"  AGENTS.md already at {dest}")
    else:
        print(f"  AGENTS.md needs to be at {dest}")


def setup_obsidian(vault_path: Path):
    """Setup Obsidian configuration."""
    try:
        sys.path.insert(0, str(SRC_DIR))
        from obsidian import ObsidianCompat

        compat = ObsidianCompat(str(vault_path))
        if not compat.is_setup():
            compat.setup()
            print(f"  Obsidian config created")
        else:
            print(f"  Obsidian config already exists")
    except Exception as e:
        print(f"  Obsidian setup skipped: {e}")


def create_example_project(vault_path: Path):
    """Create an example project for reference."""
    try:
        sys.path.insert(0, str(SRC_DIR))
        from layer_state import LayerState

        example_path = vault_path / "projects" / "example"
        if not example_path.exists():
            LayerState.init_project(str(vault_path), "example")
            print(f"  Example project created")
        else:
            print(f"  Example project already exists")
    except Exception as e:
        print(f"  Example project skipped: {e}")


def verify_installation(vault_path: Path):
    """Verify the installation."""
    print("\nVerification:")

    # Check vault exists
    if vault_path.exists():
        print(f"  ✓ Vault at {vault_path}")
    else:
        print(f"  ✗ Vault not found")
        return False

    # Check key files
    key_files = ["_index.md", "_inbox.md", "user/active_context.md"]
    for f in key_files:
        if (vault_path / f).exists():
            print(f"  ✓ {f}")
        else:
            print(f"  ✗ {f} missing")

    # Check CLI
    cli = HERMES_SCRIPTS / "vault"
    if cli.exists():
        print(f"  ✓ CLI at {cli}")
    else:
        print(f"  ✗ CLI not found")

    # Check vault tool
    tool = Path.home() / ".hermes" / "external_tools" / "vault_tool.py"
    if tool.exists():
        print(f"  ✓ vault_tool.py at {tool}")
    else:
        print(f"  ✗ vault_tool.py not found")

    # Check Python imports
    try:
        sys.path.insert(0, str(SRC_DIR))
        from vault_utils import scan_vault
        files = scan_vault(str(vault_path))
        print(f"  ✓ Vault readable ({len(files)} files)")
    except Exception as e:
        print(f"  ✗ Import error: {e}")
        return False

    return True


def main():
    print("=" * 60)
    print("Mnemosyne Knowledge Vault — Setup")
    print("=" * 60)

    # Parse args
    vault_path = DEFAULT_VAULT
    skip_deps = "--skip-deps" in sys.argv
    if "--vault-path" in sys.argv:
        idx = sys.argv.index("--vault-path")
        vault_path = Path(sys.argv[idx + 1])

    print(f"\nVault path: {vault_path}")
    print(f"Source dir: {SCRIPT_DIR}")
    print()

    # Check requirements
    print("Checking requirements...")
    errors = check_requirements()
    if errors:
        print("\n  Issues found:")
        for e in errors:
            print(f"    ! {e}")
        
        if any("not found" in e.lower() for e in errors):
            print("\n  Hermes Agent must be installed first.")
            print("  See: https://github.com/nous-hermes/hermes-agent")
            sys.exit(1)
    else:
        print("  ✓ All requirements met")

    # Install dependencies
    if not skip_deps:
        print("\nInstalling dependencies...")
        install_dependencies()

    # Run setup
    print("\nCreating vault structure...")
    create_vault_structure(vault_path)

    print("\nInstalling vault tool...")
    install_vault_tool()

    print("\nInstalling mnemosyne skill...")
    install_skill()

    print("\nInstalling CLI scripts...")
    install_scripts(vault_path)

    print("\nSetting up Obsidian...")
    setup_obsidian(vault_path)

    print("\nCreating example project...")
    create_example_project(vault_path)

    # Verify
    success = verify_installation(vault_path)

    print()
    print("=" * 60)
    if success:
        print("✓ Mnemosyne vault setup complete!")
        print()
        print("Next steps:")
        print("  1. Restart the agent (or hermes instance)")
        print("  2. The 'vault' tool will appear in the tool list")
        print("  3. Try: vault(action='enter', project='example')")
        print("  4. Open ~/.hermes/memory/ in Obsidian for graph view")
    else:
        print("✗ Setup had issues. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

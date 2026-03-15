# Mnemosyne Installation Guide

## Prerequisites

- **Hermes Agent** installed at `~/.hermes/hermes-agent/`
- **Python 3.8+**
- **PyYAML** (`pip install pyyaml`)

## Quick Install (One Command)

```bash
# Clone or download this package to ~/.hermes/workspace/mnemosyne-dev
cd ~/.hermes/workspace/mnemosyne-dev

# Run the installer
bash install.sh
```

This will:
1. Patch Hermes Agent (adds vault tool support)
2. Install vault tool, skill, CLI, and vault structure
3. Tell you to restart the agent

## Manual Installation

### Step 1: Patch Hermes Agent

The vault tool requires patches to Hermes to enable external tool discovery:

```bash
python3 patch_hermes.py
```

This modifies three files:
- `model_tools.py` — Add external tool discovery from `~/.hermes/external_tools/`
- `toolsets.py` — Add `vault` to `_HERMES_CORE_TOOLS`
- `config.yaml` — Add `vault` to platform_toolsets (cli + telegram)

**Dry run first** to see what will be changed:
```bash
python3 patch_hermes.py --dry-run
```

**Revert if needed**:
```bash
python3 patch_hermes.py --revert
```

### Step 2: Install Vault Components

```bash
python3 setup_vault.py
```

This creates:
- `~/.hermes/external_tools/vault_tool.py` — Native vault tool
- `~/.hermes/skills/mnemosyne/` — Workflow guidance skill
- `~/.hermes/scripts/vault` — CLI wrapper
- `~/.hermes/memory/` — Vault storage directory
- Obsidian configuration

### Step 3: Restart Hermes Agent

Restart the agent for the `vault` tool to appear in the tool list.

### Step 4: Verify Installation

```bash
# Check vault structure
ls ~/.hermes/memory/

# Check vault tool
ls ~/.hermes/external_tools/vault_tool.py

# Check skill
ls ~/.hermes/skills/mnemosyne/SKILL.md

# Check CLI
ls ~/.hermes/scripts/vault
```

Or run the verification:
```bash
python3 setup_vault.py  # shows verification at end
```

## What Gets Installed

```
~/.hermes/
├── external_tools/vault_tool.py      # Native vault tool (auto-discovered)
├── skills/mnemosyne/                 # Workflow guidance skill
│   ├── SKILL.md
│   └── references/vault-commands.md
├── scripts/vault                     # CLI wrapper
└── memory/                           # Vault storage
    ├── projects/                     # Project files
    ├── decisions/                    # Decision audit trail
    ├── .obsidian/                    # Obsidian config
    └── ...
```

## Usage

### From the Agent

The `vault` tool appears automatically. Use it:

```
vault(action='enter', project='myproject')
vault(action='status')
vault(action='search', query='topic')
vault(action='decision', text='Use approach X because Y')
vault(action='synthesize')
```

### From CLI

```bash
vault enter myproject
vault status
vault search "topic"
vault decision "Use approach X"
vault synthesize
```

### From Python

```python
import sys
sys.path.insert(0, '~/.hermes/workspace/mnemosyne-dev/src')
from vault_context import VaultContextManager

vcm = VaultContextManager()
vcm.enter_project("myproject")
print(vcm.get_status())
```

## Creating a Project

```
vault(action='init', project='myproject')
vault(action='enter', project='myproject')
```

This creates:
```
~/.hermes/memory/projects/myproject/
├── _overview.md      # L1: Project overview, goals, constraints
├── _synthesis.md     # Cross-layer summary (auto-generated)
├── components/       # L2: Component specs
├── rules/            # L3: Constraints, specifications
└── research/         # L4: Research findings
```

## Layer System (L1-L4)

| Layer | Name | Purpose | Example |
|-------|------|---------|---------|
| L1 | Surface | Decisions, goals, status | Project overview |
| L2 | Components | Parts, interfaces | Electrode design |
| L3 | Rules | Constraints, specs | Material selection rules |
| L4 | Determinants | Research, physics | Gold oxidation analysis |

**Drill down** (L1→L4) to understand WHY decisions were made.
**Synthesize up** (L4→L1) to see the big picture.

## Obsidian Integration

Open `~/.hermes/memory/` as an Obsidian vault. Pre-configured with:
- Wiki-links (`[[file-id]]`)
- Graph view with color groups
- Backlinks panel
- Frontmatter as properties
- Templates folder

## Troubleshooting

### Vault tool not appearing

1. Check if patches were applied:
   ```bash
   grep "vault" ~/.hermes/hermes-agent/toolsets.py
   ```

2. Check if vault_tool.py exists:
   ```bash
   ls ~/.hermes/external_tools/vault_tool.py
   ```

3. Restart the agent completely.

### Import errors

Ensure PyYAML is installed:
```bash
pip install pyyaml
```

### Permission errors

Ensure scripts are executable:
```bash
chmod +x ~/.hermes/scripts/vault
```

### Manual patching

If automatic patching fails, see `MANUAL_PATCHES.md` for manual instructions.

## Uninstallation

### Remove vault tool and skill

```bash
rm -f ~/.hermes/external_tools/vault_tool.py
rm -rf ~/.hermes/skills/mnemosyne
rm -f ~/.hermes/scripts/vault
```

### Revert Hermes patches

```bash
python3 patch_hermes.py --revert
```

### Remove vault data (optional)

```bash
# WARNING: This deletes all vault data
rm -rf ~/.hermes/memory/
```

## Advanced Configuration

### Custom vault location

```bash
python3 setup_vault.py --vault-path /path/to/vault
```

### Skip dependency installation

```bash
python3 setup_vault.py --skip-deps
```

### Custom Hermes path

```bash
python3 patch_hermes.py --hermes-path /path/to/hermes-agent
```

## Development

### Project Structure

```
mnemosyne-dev/
├── README.md              # This file
├── AGENTS.md              # Agent-facing guide
├── ARCHITECTURE.md        # 4-layer architecture
├── setup_vault.py         # Installation script
├── patch_hermes.py        # Hermes patcher
├── src/                   # Python modules (24 files)
│   ├── vault_context.py   # Main integration point
│   ├── vault_utils.py     # Frontmatter, links, scanning
│   ├── layer_state.py     # Layer traversal
│   ├── vault_search.py    # Full-text search
│   ├── synthesis.py       # L4→L1 synthesis
│   └── ...                # 19 more modules
├── templates/             # File templates
│   ├── l1_overview.md
│   ├── l2_component.md
│   ├── l3_rule.md
│   ├── l4_research.md
│   ├── decision.md
│   └── synthesis.md
├── skills/mnemosyne/      # Skill files
│   ├── SKILL.md
│   └── references/
└── tools/vault_tool.py    # Vault tool
```

### Testing

```bash
cd ~/.hermes/workspace/mnemosyne-dev
python3 tests/test_week4.py     # Run specific suite
python3 tests/test_integration.py
```

## Requirements

- Python 3.8+
- PyYAML
- Hermes Agent (for tool registration)

## License

MIT License - See LICENSE file for details.

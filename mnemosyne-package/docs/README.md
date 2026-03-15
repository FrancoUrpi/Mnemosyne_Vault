# Mnemosyne — Agentic Knowledge Vault for Hermes

Persistent, structured memory for AI agents. Stores project context, research, decisions, and reasoning chains across conversations.

## What It Does

- **Persistent knowledge** — survives agent restarts, structured for retrieval
- **Layered context** — L1 (decisions) → L2 (components) → L3 (rules) → L4 (research)
- **Decision audit trail** — every decision logged with reasoning chain
- **Cross-session state** — vault state shared across conversations
- **Obsidian compatible** — open in Obsidian for graph visualization

## Quick Install

### Prerequisites

- Hermes Agent installed at `~/.hermes/hermes-agent/`
- Python 3.8+
- PyYAML (`pip install pyyaml`)

### Installation

```bash
# 1. Clone this repo to the Hermes workspace
git clone <repo-url> ~/.hermes/workspace/mnemosyne-dev

# 2. Patch Hermes Agent (adds vault tool support)
cd ~/.hermes/workspace/mnemosyne-dev
python3 patch_hermes.py

# 3. Run the installer
python3 setup_vault.py

# 4. Restart the agent
# The 'vault' tool will now appear in the tool list
```

**Step 2 is required.** Hermes doesn't have external tool discovery or vault support by default. The patcher adds:
- External tool loading from `~/.hermes/external_tools/` (model_tools.py)
- `vault` toolset registration (toolsets.py)

See `MANUAL_PATCHES.md` to apply patches by hand, or run with `--dry-run` first.

### What Gets Installed

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

### Verify Installation

```bash
python3 setup_vault.py  # shows verification at end
```

Or manually:
```bash
ls ~/.hermes/external_tools/vault_tool.py
ls ~/.hermes/skills/mnemosyne/SKILL.md
ls ~/.hermes/memory/.obsidian/app.json
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

## File Format

All vault files use YAML frontmatter + Markdown:

```markdown
---
id: file-id
type: research|component|rule|decision|overview
layer: L1|L2|L3|L4
project: project-name
created: 2026-03-14
updated: 2026-03-14
confidence: low|moderate|high
status: active|archived
tags: [tag1, tag2]
---

# Title

Content with [[wiki-links]].
```

## Architecture

See `ARCHITECTURE.md` for the full 4-layer integration design.

```
Layer 1: vault tool     — Agent's primary interface (ambient)
Layer 2: mnemosyne skill — Workflow guidance (triggered)
Layer 3: vault CLI      — Debugging (direct access)
Layer 4: Python API     — Programmatic (subagents, scripts)
```

All 4 layers call `VaultContextManager` — single source of truth.

## Project Structure

```
mnemosyne-dev/
├── README.md              # This file
├── AGENTS.md              # Agent-facing guide
├── ARCHITECTURE.md        # 4-layer architecture
├── DEVELOPMENT_LOG.md     # Full development history
├── setup_vault.py         # Installation script
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
└── tests/                 # Test suites (521 tests)
```

## Testing

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

See LICENSE file.

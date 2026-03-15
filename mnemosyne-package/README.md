# Mnemosyne — Agentic Knowledge Vault

Persistent, structured memory for AI agents. Stores project context, research, decisions, and reasoning chains across conversations.

## What It Does

- **Persistent knowledge** — survives agent restarts, structured for retrieval
- **Layered context** — L1 (decisions) → L2 (components) → L3 (rules) → L4 (research)
- **Decision audit trail** — every decision logged with reasoning chain
- **Cross-session state** — vault state shared across conversations
- **Obsidian compatible** — open in Obsidian for graph visualization

## Quick Start

```bash
# Install
bash install.sh

# Or manually
python3 patch_hermes.py
python3 setup_vault.py

# Restart the agent
# The 'vault' tool will now appear in the tool list
```

## Usage

### From the Agent

The `vault` tool appears automatically:

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

## Architecture

Mnemosyne uses a 4-layer integration architecture:

```
Layer 1: vault tool     — Agent's primary interface (ambient)
Layer 2: mnemosyne skill — Workflow guidance (triggered)
Layer 3: vault CLI      — Debugging (direct access)
Layer 4: Python API     — Programmatic (subagents, scripts)
```

All 4 layers call `VaultContextManager` — single source of truth.

## Layer System (L1-L4)

| Layer | Name | Purpose |
|-------|------|---------|
| L1 | Surface | Decisions, goals, status |
| L2 | Components | Parts, interfaces |
| L3 | Rules | Constraints, specs |
| L4 | Determinants | Research, physics |

**Drill down** (L1→L4) to understand WHY decisions were made.
**Synthesize up** (L4→L1) to see the big picture.

## File Format

All vault files use YAML frontmatter + Markdown:

```yaml
---
id: file-id
type: research|component|rule|decision|overview
layer: L1|L2|L3|L4
project: project-name
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: low|moderate|high
status: active|archived
tags: [tag1, tag2]
---
```

## Project Structure

```
mnemosyne-package/
├── README.md              # This file
├── DESCRIPTION.md         # Detailed project description
├── INSTALL.md             # Installation guide
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
├── tools/vault_tool.py    # Vault tool
└── docs/                  # Documentation
    ├── README.md
    └── ARCHITECTURE.md
```

## Requirements

- Python 3.8+
- PyYAML
- Hermes Agent (for tool registration)

## License

MIT License - See LICENSE file for details.

# Vault CLI Reference

Complete reference for the `vault` CLI command and `vault()` tool.

---

## Tool Interface (Agent)

The agent uses the `vault` tool directly:

```python
vault(action="enter", project="eeg")
vault(action="status")
vault(action="search", query="gold oxidation")
vault(action="drill", target="gold-oxidation-analysis")
vault(action="up")
vault(action="get", target="impedance-rules")
vault(action="decision", text="Use gold electrodes")
vault(action="synthesize")
vault(action="layers")
vault(action="state")
vault(action="init", project="new-project")
```

---

## CLI Interface (Terminal)

Direct terminal commands for debugging and scripting:

```bash
# Project management
vault enter <project>       # Enter project context
vault init <project>        # Create new project
vault status                # Show project health

# Navigation
vault drill [file_id]       # Drill down or into specific file
vault up                    # Synthesize up one layer
vault layers                # Show layer overview
vault state                 # Show current navigation state

# Search & retrieval
vault search <query>        # Full-text search
vault get <file_id>         # Read specific file

# Decision & synthesis
vault decision <text>       # Log a decision
vault synthesize            # Generate L4→L1 summary

# Maintenance
vault maintenance           # Run health check
vault prompt [project]      # Build vault context for prompt
vault check <area> <action> # Check authorization
```

---

## Vault File Structure

```
~/.hermes/memory/
├── _index.md                    # Navigation hub
├── _inbox.md                    # Quick captures
├── projects/
│   └── <project>/
│       ├── _overview.md         # L1: Goals, status, decisions
│       ├── _synthesis.md        # Cross-layer summary
│       ├── components/          # L2: Parts, interfaces
│       │   └── *.md
│       ├── rules/               # L3: Constraints, specs
│       │   └── *.md
│       └── research/            # L4: Research, principles
│           └── *.md
├── concepts/                    # Cross-project knowledge
├── decisions/                   # Decision audit trail
├── user/
│   ├── active_context.md        # Current session context
│   └── preferences.md           # User preferences
└── .vault_state.json            # Navigation state (auto-managed)
```

---

## File Frontmatter Format

```yaml
---
id: short-descriptive-id
type: overview | component | rule | research | decision | context
layer: L1 | L2 | L3 | L4 | cross
project: <project_name>
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: low | moderate | high
status: active | draft | archived | superseded
tags: [tag1, tag2]
---
```

---

## Layer System

| Layer | Name | Folder | Content |
|-------|------|--------|---------|
| L1 | SURFACE | (root) | Decisions, goals, status (_overview.md) |
| L2 | COMPONENTS | components/ | Parts, interfaces, subsystems |
| L3 | RULES | rules/ | Constraints, specifications, thresholds |
| L4 | DETERMINANTS | research/ | Research, principles, first causes |

**Navigation:**
- Drill down: L1→L2→L3→L4 (expand context)
- Synthesize up: L4→L3→L2→L1 (contract context)
- Lateral: Same layer, different files

---

## Wiki-Link Format

```markdown
[[file_id]]              — link to file
[[file_id|Display Text]] — link with custom text
```

**Link sections in files:**
```markdown
## Links
### Derived From
- [[source_file]] — what led here
### Supports
- [[target_file]] — what this leads to
### Related
- [[related_file]] — other relevant files
```

---

## Environment

- **Vault path:** `~/.hermes/memory/`
- **CLI location:** `~/.hermes/scripts/vault`
- **Python modules:** `~/.hermes/workspace/mnemosyne-dev/src/`
- **State file:** `~/.hermes/memory/.vault_state.json`
- **Obsidian config:** `~/.hermes/memory/.obsidian/`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `vault: command not found` | Run `python3 ~/.hermes/workspace/mnemosyne-dev/setup_vault.py` |
| `No module named 'vault_context'` | Check PYTHONPATH includes mnemosyne-dev/src/ |
| `No active project` | Run `vault enter <project>` first |
| State not persisting | Check `.vault_state.json` permissions |
| Broken links | Run `vault maintenance` |

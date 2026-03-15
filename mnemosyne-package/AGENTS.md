# Mnemosyne Knowledge Vault — Agent Guide

## What Is This?

Mnemosyne is your persistent knowledge vault. It stores project context, research, decisions, and reasoning chains across conversations. Unlike session memory, vault data survives restarts and is structured for retrieval.

## Quick Reference

### Primary Interface: `vault` Tool

The `vault` tool is always in your tool list. Use it for all vault operations:

```
vault(action='enter', project='name')     # Load project context
vault(action='status')                    # Project health + phase
vault(action='search', query='topic')     # Full-text search
vault(action='drill', target='file_id')   # Navigate deeper (L1→L4)
vault(action='up')                        # Synthesize higher (L4→L1)
vault(action='get', target='file_id')     # Read specific file
vault(action='decision', text='...')      # Log a decision
vault(action='synthesize')                # Generate cross-layer summary
vault(action='layers')                    # Show layer file counts
vault(action='state')                     # Current navigation state
vault(action='init', project='name')      # Create new project
```

### Workflow Guidance: `mnemosyne` Skill

For complex operations, load the `mnemosyne` skill (`skill_view(name='mnemosyne')`). It provides step-by-step playbooks for:

- Research & Write-Back (finding → L4 research file)
- Cross-Layer Analysis (reasoning chain output)
- Decision Logging (structured decision records)
- Synthesis (L4→L1 summary generation)
- Vault Maintenance (health checks, broken links)
- Creating New Projects

### CLI: `vault` Command

For debugging or direct user access:

```bash
vault enter eeg
vault status
vault search "gold oxidation"
vault drill gold-oxidation-analysis
vault decision "Use active shielding"
```

## Vault Structure

```
~/.hermes/memory/
├── _index.md              # Vault overview
├── _inbox.md              # Quick captures
├── user/
│   ├── active_context.md  # Current focus
│   └── preferences.md     # Learned preferences
├── projects/
│   └── <project>/
│       ├── _overview.md   # L1: Project overview
│       ├── _synthesis.md  # Cross-layer summary
│       ├── components/    # L2: Component specs
│       ├── rules/         # L3: Constraints/rules
│       └── research/      # L4: Research findings
├── decisions/             # Decision audit trail
├── concepts/              # Cross-project concepts
└── archive/               # Old/stale files
```

## Layer System (L1-L4)

Vault files are organized into abstraction layers:

| Layer | Name | Purpose | Example |
|-------|------|---------|---------|
| L1 | Surface | Decisions, goals, status | `_overview.md` |
| L2 | Components | Parts, interfaces | `eeg-electrodes` |
| L3 | Rules | Constraints, specs | `material-rules` |
| L4 | Determinants | Research, principles | `gold-oxidation-analysis` |

**Drill down** (L1→L4) to understand WHY decisions were made.
**Synthesize up** (L4→L1) to see the big picture.

## When To Use Vault

- User asks about projects, past decisions, or research
- User asks "what are we working on" or "what do we know about X"
- Starting work on a project (always enter first)
- Making decisions that should be recorded
- Research findings that should be preserved
- User references something from past work

**Priority:** Use vault BEFORE session_search for project/knowledge queries. Vault has structured project data. Session search has conversational narrative. Use both for complete picture.

## Decision Logging

When making a significant decision:

```
vault(action='decision', text='Use gold electrodes because they are electrochemically stable at scalp pH')
```

This creates a decision file with timestamp, project context, and reasoning chain.

## Autonomy Levels

| Level | Meaning |
|-------|---------|
| Autonomous | Act without asking |
| Notify | Act, then inform user |
| Approve | Ask before acting |
| Forbidden | Never do this |

Check with `vault(action='check', area='...', action='...')`.

## Tips

1. **Always enter a project first** — context is project-scoped
2. **Log decisions as you make them** — don't rely on memory
3. **Use layers** — drill down for details, synthesize for overview
4. **Search before asking** — the vault might already know
5. **Check status regularly** — health alerts indicate issues

## File Format

All vault files use YAML frontmatter:

```markdown
---
id: file-id
type: research|component|rule|decision|overview
layer: L1|L2|L3|L4
project: project-name
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: low|moderate|high
status: active|archived|superseded
tags: [tag1, tag2]
---

# Title

Content with [[wiki-links]] to related files.
```

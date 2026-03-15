# Mnemosyne Architecture

## Overview

Mnemosyne is an agentic knowledge vault that provides persistent, structured memory for AI agents. It integrates with Hermes through a 4-layer architecture that ensures the agent always has access to project knowledge, regardless of how it's invoked.

## Design Philosophy

Mnemosyne is **not a task** — it's a **behavior overlay**. It should be ambient ("you have a knowledge vault, use it"), not triggered. The architecture ensures:

1. **Discoverability** — Agent sees the vault tool every conversation
2. **Workflow guidance** — Complex operations have step-by-step playbooks
3. **Debuggability** — User can verify vault state directly
4. **Extensibility** — Subagents and scripts can access programmatically

## 4-Layer Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Hermes Agent Runtime                        │
├─────────────┬─────────────┬──────────────┬─────────────────────┤
│  Layer 1    │  Layer 2    │  Layer 3     │  Layer 4            │
│  Tool       │  Skill      │  CLI         │  Python API         │
│  (vault)    │(mnemosyne)  │(vault cmd)   │(VaultContextManager)│
├─────────────┴─────────────┴──────────────┴─────────────────────┤
│              VaultContextManager (single source of truth)       │
├────────────────────────────────────────────────────────────────┤
│  vault_utils │ layer_state │ vault_search │ link_navigator     │
│  on_demand   │ traversal   │ synthesis    │ intent             │
│  audit       │ governance  │ attribution  │ context_audit      │
│  status      │ trust       │ maintenance  │ cross_project      │
│  context_loader │ relevance │ budget     │ prompt_integration │
├────────────────────────────────────────────────────────────────┤
│                     Vault Filesystem                           │
│  ~/.hermes/memory/projects/.../*.md                            │
└────────────────────────────────────────────────────────────────┘
```

### Layer 1: Native Tool (`vault`)

**Purpose:** Primary agent interface. Always visible in tool list.

**Implementation:** `~/.hermes/external_tools/vault_tool.py`

**Why:** Tool is ambient — agent sees it every conversation without needing to trigger or remember. Solves discoverability.

**Registration:**
- Auto-discovered by `model_tools.py` external tool loader
- Registered in `_HERMES_CORE_TOOLS` in `toolsets.py`
- Registered in `ToolRegistry` via `tools.registry`

**State:** Persisted to `~/.hermes/memory/.vault_state.json` between calls.

### Layer 2: Skill (`mnemosyne`)

**Purpose:** Workflow guidance for complex operations.

**Implementation:** `~/.hermes/skills/mnemosyne/SKILL.md`

**Why:** Tool schema is static text — can't express multi-step procedures. Skill provides step-by-step playbooks for complex tasks.

**Workflows:**
- Research & Write-Back
- Cross-Layer Analysis
- Decision Logging
- Synthesis
- Vault Maintenance
- Create New Project

**Triggers:** Scoped to complex operations only (no overlap with tool).

### Layer 3: CLI (`vault` command)

**Purpose:** Debugging and direct user access.

**Implementation:** `~/.hermes/scripts/vault` (wrapper around `vault_cli.py`)

**Why:** User can verify vault state directly, debug issues, and perform operations without agent mediation.

**Commands:** enter, status, search, drill, up, get, decision, synthesize, state, layers, maintenance

**State:** Shares state with tool via `.vault_state.json`.

### Layer 4: Python API (`VaultContextManager`)

**Purpose:** Programmatic access for subagents and scripts.

**Implementation:** `~/.hermes/workspace/mnemosyne-dev/src/vault_context.py`

**Why:** Subagents, cronjobs, and custom scripts need direct Python access without CLI overhead.

**Usage:**
```python
from vault_context import VaultContextManager
vcm = VaultContextManager()
vcm.enter_project("eeg")
print(vcm.get_status())
```

## Data Flow

```
User/Agent Request
       │
       ▼
┌──────────────┐
│  vault_tool  │──── Tool handler
│  (Layer 1)   │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ VaultContextManager  │◄─── Skill workflows call tool
│  (Single source      │◄─── CLI calls this directly
│   of truth)          │◄─── Python API wraps this
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Core Modules        │
│  - layer_state       │  Layer traversal
│  - vault_search      │  Full-text search
│  - synthesis         │  L4→L1 summaries
│  - intent            │  Autonomy levels
│  - audit             │  Decision trail
│  - governance        │  Authorization
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Vault Filesystem    │
│  ~/.hermes/memory/   │
└──────────────────────┘
```

## Vault Layer System (L1-L4)

Internal vault files are organized into abstraction layers:

| Layer | Name | Folder | Purpose |
|-------|------|--------|---------|
| L1 | Surface | (root) | Project overview, decisions, status |
| L2 | Components | `components/` | Parts, interfaces, subsystems |
| L3 | Rules | `rules/` | Constraints, specifications |
| L4 | Determinants | `research/` | Research findings, physics, principles |

Files link across layers via `[[wiki-links]]`. Navigation supports:
- **Drill down:** L1→L2→L3→L4 (understand WHY)
- **Synthesize up:** L4→L3→L2→L1 (big picture)
- **Lateral:** Same layer, different files

## State Management

State is shared across all 4 layers via `~/.hermes/memory/.vault_state.json`:

```json
{
  "project": "eeg",
  "layer": "L3",
  "current_file": "material-rules"
}
```

- **Tool** reads/writes state on every call
- **CLI** reads/writes state on every call
- **Skill** operates through tool (inherits state)
- **Python API** manages state in-memory (VaultSessionState)

## Module Map

```
mnemosyne-dev/
├── src/
│   ├── vault_context.py      # Main integration (VaultContextManager)
│   ├── vault_utils.py        # Frontmatter, links, scanning
│   ├── layer_state.py        # Layer traversal state machine
│   ├── vault_search.py       # Full-text + metadata search
│   ├── link_navigator.py     # Wiki-link graph traversal
│   ├── on_demand.py          # Lazy-loading file retriever
│   ├── traversal.py          # Unified navigation interface
│   ├── context_loader.py     # Two-stage context loading
│   ├── relevance.py          # Topic relevance scoring
│   ├── budget.py             # Token budget management
│   ├── prompt_integration.py # System prompt builder
│   ├── synthesis.py          # L4→L1 synthesis engine
│   ├── intent.py             # Intent schema + autonomy
│   ├── audit.py              # Decision audit trail
│   ├── governance.py         # Autonomy enforcement
│   ├── attribution.py        # Chunk attribution tracking
│   ├── context_audit.py      # Context loading audit
│   ├── status.py             # Project health monitoring
│   ├── trust.py              # Trust-based autonomy
│   ├── maintenance.py        # Vault health maintenance
│   ├── cross_project.py      # Cross-project analysis
│   ├── obsidian.py           # Obsidian compatibility
│   ├── docs.py               # Documentation generator
│   └── vault_cli.py          # CLI wrapper
├── templates/                # File templates (L1-L4, decision, synthesis)
├── tests/                    # Test suites (389 tests)
└── AGENTS.md                 # Agent-facing guide
```

## Integration Points

### model_tools.py

External tool discovery (1 line change):
```python
# Load external tools from ~/.hermes/external_tools/
external_tools_dir = Path.home() / ".hermes" / "external_tools"
```

### toolsets.py

`vault` added to `_HERMES_CORE_TOOLS` set.

### ~/.hermes/skills/mnemosyne/

Skill files with workflow guidance and vault-commands reference.

## Testing

| Suite | Tests | Coverage |
|-------|-------|----------|
| Week 1: Foundation | 46 | vault_utils, layer_state |
| Week 2: Context | 57 | context_loader, relevance, budget, prompts |
| Week 3: Navigation | 99 | search, links, on_demand, traversal |
| Week 4: Synthesis | 73 | synthesis, intent, audit, governance |
| Week 5: Metrics | 69 | attribution, context_audit, status, trust |
| Week 6: Polish | 50 | maintenance, cross_project, obsidian, docs |
| Integration | 41 | vault_context, CLI, setup |
| Phase 1: Tool | 25 | vault_tool |
| Phase 2: Skill | 25 | mnemosyne SKILL.md |
| Phase 3: CLI | 25 | CLI verification |
| Phase 4: API | 57 | Python API cleanup |
| **Total** | **567** | **All passing** |

## Design Decisions

### Why 4 layers?

Each layer addresses a different failure mode:
- **Tool** solves discoverability (ambient visibility)
- **Skill** solves workflow complexity (step-by-step)
- **CLI** solves debugging (direct user access)
- **Python API** solves extensibility (subagents, scripts)

### Why not just AGENTS.md?

Tested: Agent bypassed vault entirely, using session_search + raw filesystem. AGENTS.md is passive context — system prompt directs agent to use session_search, which wins.

### Why not just a skill?

Skills depend on shallow trigger matching. Not semantic. Only active during loaded turn, not ambient. Estimated 60-80% effectiveness alone.

### Why not just a tool?

Tool handles simple calls but can't express complex multi-step workflows in its static schema. Schema is cached text, not procedures.

### Redundancy is intentional

- Tool + CLI + Python API all call VaultContextManager — different access patterns
- Tool schema + Skill triggers overlap on "when to use vault" — scoped differently
- No duplication of business logic — single source of truth

## File Format

All vault files use YAML frontmatter + Markdown body:

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

Body content with [[wiki-links]].
```

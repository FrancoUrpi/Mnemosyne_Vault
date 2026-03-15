# Mnemosyne — Agentic Knowledge Vault

## Overview

Mnemosyne is a persistent, structured memory system designed for AI agents. It provides a knowledge vault that stores project context, research findings, decisions, and reasoning chains across conversations, enabling agents to maintain continuity and build upon previous work.

## Core Philosophy

### Context Engineering over Context Compression

Mnemosyne was designed based on a fundamental insight: **AI agents need structured memory, not just more memory**. Traditional approaches to agent memory either:

1. **Store everything** (session logs, raw conversation history) — overwhelming the agent with irrelevant information
2. **Use simple compression** (summarization) — losing critical details and reasoning chains
3. **Rely on embedding search** (vector databases) — good for retrieval but poor for structured reasoning

Mnemosyne takes a different approach: **context engineering through layered abstraction**.

### The Layered Research Framework

The system organizes knowledge into four abstraction layers, each representing a different level of context scope:

```
L1: SURFACE         [Context: MINIMAL - the decision]
    ↓ expand context downward
L2: COMPONENTS      [Context: COMPONENT-LEVEL - parts, interfaces]
    ↓ expand context downward
L3: RULES           [Context: RULE-LEVEL - specs, limits]
    ↓ expand context downward
L4: DETERMINANTS    [Context: MAXIMAL - physics, principles, research]
```

This isn't compression — it's **context scoping**:
- **Active Context**: What's in the working memory right now
- **Inactive Context**: Available on demand, linked but not cluttering focus
- **Dependency Links**: Bidirectional connections between layers

When you move **down** layers, you **expand** context to include underlying reasoning.
When you move **up** layers, you **contract** context to operating conclusions, hiding underlying detail while keeping it retrievable.

## Comparison with Existing Tools

### vs. Session Search (Hermes' built-in)

| Feature | Session Search | Mnemosyne |
|---------|---------------|-----------|
| **Purpose** | Conversational recall | Structured project knowledge |
| **Structure** | Flat, chronological | Layered, hierarchical |
| **Retrieval** | Keyword/semantic search | Layer traversal + search |
| **Persistence** | Per-session | Cross-session |
| **Context** | Raw conversation snippets | Curated, confidence-scored |

**Why both?** Session search finds what was said; Mnemosyne stores what was decided and why.

### vs. Vector Databases (Chroma, Pinecone, etc.)

| Feature | Vector DBs | Mnemosyne |
|---------|-----------|-----------|
| **Data model** | Embeddings + metadata | Markdown files + wiki-links |
| **Query** | Similarity search | Layer traversal + full-text search |
| **Structure** | Flat collections | Hierarchical layers (L1-L4) |
| **Reasoning** | Implicit in embeddings | Explicit reasoning chains |
| **Human-readable** | No (binary vectors) | Yes (plain Markdown) |
| **Tool integration** | API calls | Native tool in agent |

**Key difference**: Vector databases are optimized for semantic similarity retrieval. Mnemosyne is optimized for **structured reasoning** and **decision traceability**.

### vs. Obsidian (Note-taking)

| Feature | Obsidian | Mnemosyne |
|---------|---------|-----------|
| **Primary user** | Humans | AI agents |
| **Access method** | GUI/CLI | Native tool API |
| **Structure** | User-defined | Enforced L1-L4 layers |
| **Automation** | Manual | Agent-driven |
| **Integration** | Plugins | Built into agent runtime |
| **Reasoning** | Optional | Core feature |

**Relationship**: Mnemosyne stores data in Obsidian-compatible format. You can open `~/.hermes/memory/` directly in Obsidian for graph visualization, while the agent uses the native `vault` tool.

### vs. Simple Memory Systems

| Feature | Simple Memory | Mnemosyne |
|---------|---------------|-----------|
| **Structure** | Key-value or list | Multi-layer hierarchy |
| **Confidence** | None | Inherited from source layers |
| **Decision trail** | None | Full audit with alternatives |
| **Synthesis** | Manual summarization | Automatic L4→L1 synthesis |
| **Maintenance** | None | Health monitoring, broken link detection |

## Why This Architecture?

### Problem 1: Agent Amnesia
AI agents lose all context between conversations. Mnemosyne solves this with persistent, structured storage that survives restarts.

### Problem 2: Context Overload
Even with persistent storage, agents can be overwhelmed by too much information. Mnemosyne solves this with **layered context scoping** — the agent sees only what's relevant at its current layer, with the ability to drill down when needed.

### Problem 3: Decision Traceability
When an agent makes a decision, users want to know why. Traditional memory systems lose the reasoning chain. Mnemosyne logs every decision with its full reasoning chain from L4 research up to L1 conclusion.

### Problem 4: Knowledge Fragmentation
Without structure, knowledge becomes fragmented — isolated facts without connections. Mnemosyne enforces [[wiki-links]] between files and tracks confidence inheritance through the layer chain.

## Context Engineering Principles

### 1. Two-Stage Context Loading
Instead of loading everything, Mnemosyne uses a two-stage approach:
1. **Stage 1**: Scan frontmatter (metadata) to assess relevance
2. **Stage 2**: Load full content only for relevant files

This prevents context overflow while ensuring important information isn't missed.

### 2. Relevance Scoring
Files are scored based on:
- **Recency (30%)**: How recently was this file updated?
- **Topic Match (50%)**: How well does it match the current topic?
- **User Priority (20%)**: Has the user explicitly referenced this?

### 3. Token Budget Management
The system tracks token usage with four degradation levels:
- **None**: Full context loaded
- **Squeeze**: Remove previews and non-essential metadata
- **Minimal**: Only L1 decisions and active thread files
- **Off**: No vault context loaded

### 4. Confidence Inheritance
When synthesizing from L4→L1, the system inherits the **lowest confidence** in the chain. This prevents overconfident conclusions from weak research.

## 4-Layer Integration Architecture

Mnemosyne integrates with Hermes through four complementary layers:

### Layer 1: Native Tool (`vault`)
**Purpose**: Primary agent interface. Always visible in tool list.
**Why**: Tool is ambient — agent sees it every conversation without needing to trigger or remember.

### Layer 2: Skill (`mnemosyne`)
**Purpose**: Workflow guidance for complex operations.
**Why**: Tool schema is static text — can't express multi-step procedures. Skill provides step-by-step playbooks.

### Layer 3: CLI (`vault` command)
**Purpose**: Debugging and direct user access.
**Why**: User can verify vault state directly without agent mediation.

### Layer 4: Python API (`VaultContextManager`)
**Purpose**: Programmatic access for subagents and scripts.
**Why**: Subagents, cronjobs, and custom scripts need direct Python access.

## Design Decisions

### Why Markdown + Wiki-Links?

1. **Human-readable**: Users can inspect, edit, and understand vault files directly
2. **Tool-agnostic**: Works with any text editor, Git, or note-taking app
3. **Obsidian-compatible**: Leverage existing graph visualization tools
4. **Future-proof**: Plain text survives tool obsolescence
5. **Diffable**: Changes are trackable in version control

### Why Not a Database?

1. **Simplicity**: No schema migrations, query languages, or server setup
2. **Portability**: Files can be copied, backed up, or synced with standard tools
3. **Transparency**: Users can see exactly what's stored
4. **Integration**: Works with existing file-based workflows

### Why Redundant Interfaces?

- Tool + CLI + Python API all call `VaultContextManager` — different access patterns
- Tool schema + Skill triggers overlap on "when to use vault" — scoped differently
- **No duplication of business logic** — single source of truth

## Use Cases

### 1. Long-term Project Tracking
Track a project across weeks or months, maintaining context of decisions, research, and progress.

### 2. Research Synthesis
Collect research findings (L4) and synthesize them into actionable rules (L3), component choices (L2), and decisions (L1).

### 3. Decision Audit Trail
When a user asks "why did we choose X?", the system can trace the full reasoning chain from underlying research up to the final decision.

### 4. Cross-Session Continuity
The agent can pick up where it left off in previous conversations, maintaining project context.

### 5. Knowledge Graph Visualization
Open the vault in Obsidian to visualize relationships between research, rules, components, and decisions.

## Technical Implementation

### File Format
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
status: active|archived|superseded
tags: [tag1, tag2]
---
```

### State Management
State is shared across all 4 layers via `~/.hermes/memory/.vault_state.json`:
```json
{
  "project": "eeg",
  "layer": "L3",
  "current_file": "material-rules"
}
```

### Module Architecture
```
vault_context.py      # Main integration (VaultContextManager)
├── vault_utils.py    # Frontmatter, links, scanning
├── layer_state.py    # Layer traversal state machine
├── vault_search.py   # Full-text + metadata search
├── link_navigator.py # Wiki-link graph traversal
├── on_demand.py      # Lazy-loading file retriever
├── traversal.py      # Unified navigation interface
├── context_loader.py # Two-stage context loading
├── relevance.py      # Topic relevance scoring
├── budget.py         # Token budget management
├── prompt_integration.py # System prompt builder
├── synthesis.py      # L4→L1 synthesis engine
├── intent.py         # Intent schema + autonomy
├── audit.py          # Decision audit trail
├── governance.py     # Autonomy enforcement
├── attribution.py    # Chunk attribution tracking
├── context_audit.py  # Context loading audit
├── status.py         # Project health monitoring
├── trust.py          # Trust-based autonomy
├── maintenance.py    # Vault health maintenance
├── cross_project.py  # Cross-project analysis
├── obsidian.py       # Obsidian compatibility
├── docs.py           # Documentation generator
└── vault_cli.py      # CLI wrapper
```

## Getting Started

See `INSTALL.md` for installation instructions.

## Philosophy

Mnemosyne is **not a task** — it's a **behavior overlay**. It should be ambient ("you have a knowledge vault, use it"), not triggered. The architecture ensures:

1. **Discoverability** — Agent sees the vault tool every conversation
2. **Workflow guidance** — Complex operations have step-by-step playbooks
3. **Debuggability** — User can verify vault state directly
4. **Extensibility** — Subagents and scripts can access programmatically

## License

MIT License - See LICENSE file for details.

---
name: mnemosyne
title: Mnemosyne Knowledge Vault
description: Complex workflows for the Mnemosyne Knowledge Vault — research write-back, cross-layer analysis, decision chains, synthesis, and maintenance.
version: 1.0.0
triggers:
  - save to vault
  - write to vault
  - log this decision
  - research and save
  - drill down to
  - show me the chain
  - why did we choose
  - what supports
  - synthesize
  - vault health
  - vault maintenance
  - check vault
  - write research
  - save findings
  - reasoning chain
  - decision chain
  - layer traversal
  - cross-layer
metadata:
  hermes:
    requires_tool: vault
    related_skills: [layered-research-framework]
---

# Mnemosyne Knowledge Vault — Workflow Guide

## Prerequisites

The `vault` tool must be available. If not, check:
```
vault(action='state')  — should return JSON, not error
```

For simple operations (enter, status, search), use the vault tool directly — no need to load this skill. This skill covers COMPLEX multi-step workflows.

---

## Workflow 1: Research & Write-Back

**When:** User asks to research a topic and save findings to the vault.

**Example:** "Research EEG amplifier circuits and save to vault"

### Steps

```
1. vault(action='enter', project='<project>')
2. Do web research using web_search tool
3. Create research file with proper frontmatter:
```

**File template:**
```markdown
---
id: <short_id>           # e.g., amplifier-circuits
type: research
layer: L4
project: <project>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
confidence: moderate     # low | moderate | high
status: active
tags: [<tag1>, <tag2>]
---

# <Title>

## Summary
One-paragraph overview of the finding.

## Key Findings
- Finding 1
- Finding 2
- Finding 3

## Content
Detailed analysis...

## Links
### Derived From
- [[<source_file>]] — what led to this research
### Supports
- [[<target_file>]] — what this research supports
### Related
- [[<related_file>]] — other relevant files
```

```
4. Write file to: ~/.hermes/memory/projects/<project>/research/<id>.md
5. vault(action='synthesize') — update cross-layer summary
6. Report what was saved and any links created
```

**Important:**
- Always include `## Links` section with `[[wiki-links]]`
- Link to at least one existing file (check `vault(action='layers')` first)
- Set confidence honestly — low/moderate/high
- Use tags that match existing vault tags when possible (check `vault(action='search', query='<topic>')` first)

---

## Workflow 2: Cross-Layer Analysis (Reasoning Chain)

**When:** User asks "why did we choose X?" or "show me the chain"

**Example:** "Show me the chain from the electrode decision to the underlying research"

### Steps

```
1. vault(action='enter', project='<project>')
2. vault(action='search', query='<decision/topic>')
3. Identify the L1 decision file
4. vault(action='drill', target='<decision_file_id>')
5. Read the file, note "Derived From" links
6. Follow each link: vault(action='get', target='<linked_file_id>')
7. Repeat until L4 research is reached
8. Present the chain: L1 → L2 → L3 → L4 with rationale at each step
```

**Output format:**
```
Reasoning Chain: <Decision>

L1 (Decision): <decision summary>
  ↓ based on
L2 (Component): <component choice>
  ↓ constrained by
L3 (Rules): <specifications/constraints>
  ↓ derived from
L4 (Research): <research/principles>

Confidence: <high/moderate/low>
Open questions: <any gaps in the chain>
```

**If the chain is broken (missing link):**
- Note where the gap is
- Flag as "research gap" rather than guessing
- Suggest: "We could research <topic> to fill this gap"

---

## Workflow 3: Decision Logging

**When:** User says "log this decision" or a significant choice is made

**Example:** "We've decided to go with dry electrodes with active shielding. Log this."

### Steps

```
1. vault(action='enter', project='<project>')
2. vault(action='search', query='<decision topic>')  — find related files
3. vault(action='decision', text='<decision summary>')
4. Write detailed decision file:
```

**Decision file template:**
```markdown
---
id: <decision_id>        # e.g., dry-electrodes-decision
type: decision
layer: L1
project: <project>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
confidence: <level>
status: active
tags: [decision, <topic>]
---

# Decision: <Title>

## Decision
<What was decided>

## Context
<Why this decision was needed>

## Reasoning Chain
- **L4 Research:** [[<research_file>]] — <summary>
- **L3 Rules:** [[<rule_file>]] — <summary>
- **L2 Component:** [[<component_file>]] — <summary>
- **L1 Decision:** This file

## Alternatives Considered
1. **<Alternative A>** — Rejected because <reason>
2. **<Alternative B>** — Rejected because <reason>

## Consequences
- <Expected outcome 1>
- <Expected outcome 2>

## Review Criteria
- <What would make us reconsider this decision>

## Links
### Derived From
- [[<research_file>]]
### Supports
- [[<component_file>]]
```

```
5. vault(action='synthesize')  — update project summary
6. Report decision logged with chain
```

---

## Workflow 4: Synthesis

**When:** User asks "synthesize everything about X" or "give me the big picture"

**Example:** "Synthesize everything we know about the EEG project"

### Steps

```
1. vault(action='enter', project='<project>')
2. vault(action='status')  — get overall health
3. vault(action='layers')  — see distribution
4. vault(action='drill')   — start at L1
5. Read _overview.md: vault(action='get', target='_overview')
6. For each layer, read key files:
   - L1: Overview, decisions
   - L2: Components
   - L3: Rules
   - L4: Research
7. vault(action='synthesize')  — run synthesis engine
8. Present structured summary
```

**Output format:**
```
## Synthesis: <Project>

### Status
- Phase: <phase>
- Health: <health>
- Criteria: <X/Y complete>

### Key Decisions
1. <Decision 1> [[<file>]]
2. <Decision 2> [[<file>]]

### Active Rules
- <Rule 1> [[<file>]]
- <Rule 2> [[<file>]]

### Components
- <Component 1> [[<file>]]
- <Component 2> [[<file>]]

### Research Foundation
- <Research 1> [[<file>]]
- <Research 2> [[<file>]]

### Open Questions
- <Question 1>
- <Question 2>

### Gaps
- <Missing research or incomplete chains>
```

---

## Workflow 5: Vault Maintenance

**When:** User asks "check vault health" or "fix vault issues"

### Steps

```
1. vault(action='status')  — overall health
2. vault(action='layers')  — check distribution
3. Run maintenance via CLI:
```
```
terminal("vault maintenance")
```
```
4. Check for broken links:
   - Read each file's Links section
   - Verify target files exist
5. Check for orphan files (no links in or out)
6. Check for stale files (not updated in 30+ days)
7. Report findings and suggest fixes
```

**Common fixes:**
- Broken link: Update or remove the [[link]]
- Orphan file: Add links to/from related files
- Stale file: Review and update, or archive
- Missing frontmatter: Add required fields

---

## Workflow 6: Create New Project

**When:** User wants to start tracking a new project in the vault

### Steps

```
1. vault(action='init', project='<project_name>')
2. vault(action='enter', project='<project_name>')
3. Edit the overview:
   - Write file to: ~/.hermes/memory/projects/<project>/_overview.md
   - Fill in: Objective, Success Criteria, Constraints
4. Create initial research/component files as needed
5. vault(action='synthesize')  — initial synthesis
6. Report project created with structure
```

---

## Pitfalls

### 1. Don't create files without links
Every vault file should have a `## Links` section with at least one `[[wiki-link]]`. Isolated files become orphans.

### 2. Don't guess confidence
If you're uncertain, set `confidence: low`. The synthesis engine inherits the LOWEST confidence in the chain. Inflating confidence propagates errors.

### 3. Don't skip the enter step
Always `vault(action='enter', project='...')` before other operations. This loads project context and sets the active project.

### 4. Don't use vague file IDs
Bad: `id: research1`
Good: `id: gold-oxidation-analysis`
IDs should be descriptive and unique.

### 5. Don't forget to synthesize
After creating/updating files, run `vault(action='synthesize')` to update cross-layer summaries.

### 6. Don't duplicate existing research
Before writing a new research file, search first: `vault(action='search', query='<topic>')`

### 7. Decision files need reasoning chains
A decision without a reasoning chain (L4→L3→L2→L1 links) is just an assertion. Always link to the research and rules that support the decision.

### 8. Layer confusion
- L1: Operating decisions ("Use gold electrodes")
- L2: Component specs ("Gold-plated copper substrate")
- L3: Rules/constraints ("Impedance < 50kΩ")
- L4: Research/principles ("Gold oxidation rates at scalp pH")

Don't put research in L1 or decisions in L4.

---

## Quick Reference: Vault Tool Actions

| Action | Params | Purpose |
|--------|--------|---------|
| `enter` | project (required) | Load project context |
| `status` | — | Project health, phase, criteria |
| `search` | query (required) | Full-text search |
| `drill` | target (optional) | Go deeper L1→L2→L3→L4 |
| `up` | — | Synthesize L4→L3→L2→L1 |
| `get` | target (required) | Read specific file |
| `decision` | text (required) | Log a decision |
| `synthesize` | — | Generate cross-layer summary |
| `layers` | — | Show layer file counts |
| `state` | — | Current navigation state |
| `init` | project (required) | Create new project |

For CLI reference, see `references/vault-commands.md`.

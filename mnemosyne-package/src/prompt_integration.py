#!/usr/bin/env python3
"""
Prompt Integration Module for Mnemosyne Knowledge Vault.

Builds vault context sections for injection into LLM system prompts.
Integrates context_loader, relevance scorer, and budget manager.

Usage:
    from prompt_integration import PromptBuilder

    builder = PromptBuilder(vault_path="~/.hermes/memory")
    vault_section = builder.build_vault_context(
        project="eeg",
        topic="electrode materials",
        model="kimi-k2.5"
    )
    # Inject vault_section into your system prompt
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass

from context_loader import ContextLoader, VaultContext
from budget import BudgetManager, DegradationLevel
from layer_state import LayerState, LAYER_INFO


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class PromptContext:
    """Complete prompt context with vault injection ready."""
    vault_section: str
    vault_context: VaultContext
    token_count: int
    file_count: int
    project: Optional[str]
    layer: Optional[str]
    degraded: bool


# ─── Prompt Builder ───────────────────────────────────────────────

class PromptBuilder:
    """
    Builds vault context sections for LLM system prompts.

    Handles:
    - Two-stage context loading
    - Budget management per model
    - Layer-aware context
    - Degradation when over budget
    - Multiple output formats
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.loader = ContextLoader(vault_path)
        self.layer_state = LayerState(vault_path)

    def build_vault_context(
        self,
        project: Optional[str] = None,
        topic: Optional[str] = None,
        model: str = "kimi-k2.5",
        layer: Optional[str] = None,
        extra_files: Optional[List[str]] = None,
        format: str = "full",
    ) -> PromptContext:
        """
        Build vault context section for system prompt.

        Args:
            project: Current project name
            topic: Current topic for relevance scoring
            model: Model name (determines budget)
            layer: Specific layer to focus on (optional)
            extra_files: File IDs to always include
            format: Output format ("full", "compact", "minimal")

        Returns:
            PromptContext with ready-to-inject vault section
        """
        # Determine budget from model
        budget_mgr = BudgetManager.for_model(model)
        vault_budget = budget_mgr.total_budget

        # Load context
        if layer:
            vault_ctx = self.loader.load_by_layer(
                layer=layer,
                project=project,
                budget_tokens=vault_budget,
            )
        else:
            vault_ctx = self.loader.load_context(
                project=project,
                topic=topic,
                budget_tokens=vault_budget,
                extra_files=extra_files,
            )

        # Format output
        if format == "full":
            vault_section = self._format_full(vault_ctx)
        elif format == "compact":
            vault_section = self._format_compact(vault_ctx)
        elif format == "minimal":
            vault_section = self._format_minimal(vault_ctx)
        else:
            vault_section = self._format_full(vault_ctx)

        return PromptContext(
            vault_section=vault_section,
            vault_context=vault_ctx,
            token_count=vault_ctx.total_tokens,
            file_count=vault_ctx.stage2_loaded,
            project=project,
            layer=layer,
            degraded=vault_ctx.truncated,
        )

    def build_layer_navigation(self, project: str) -> str:
        """Build a layer navigation guide for the current project."""
        if not project:
            return ""

        self.layer_state.set_project(project)
        layers = self.layer_state.available_layers()

        lines = []
        lines.append("## Vault Navigation")
        lines.append("")
        for layer in layers:
            marker = " [CURRENT]" if layer["current"] else ""
            lines.append(
                f"- **{layer['layer']}** ({layer['name']}): "
                f"{layer['description']} — {layer['file_count']} files{marker}"
            )
        lines.append("")
        lines.append("Navigation: drill_down (L1→L2→L3→L4), synthesize_up (L4→L3→L2→L1), lateral (same layer)")
        return "\n".join(lines)

    def build_system_prompt_extension(
        self,
        project: Optional[str] = None,
        topic: Optional[str] = None,
        model: str = "kimi-k2.5",
    ) -> str:
        """
        Build a complete system prompt extension with vault context + instructions.

        This is the main entry point — returns text ready to append to system prompt.
        """
        sections = []

        # Vault context
        ctx = self.build_vault_context(project=project, topic=topic, model=model)
        sections.append(ctx.vault_section)

        # Layer navigation (if in project)
        if project:
            nav = self.build_layer_navigation(project)
            sections.append(nav)

        # Usage instructions
        sections.append(self._build_usage_instructions())

        return "\n\n".join(sections)

    # ─── Format Options ───────────────────────────────────────────

    def _format_full(self, ctx: VaultContext) -> str:
        """Full format with all metadata."""
        lines = []
        lines.append("## Knowledge Vault Context")
        lines.append("")
        lines.append(f"**Project:** {ctx.project or '(none)'}")
        lines.append(f"**Topic:** {ctx.topic or '(general)'}")
        lines.append(f"**Budget:** {ctx.total_tokens}/{ctx.budget_tokens} tokens")
        lines.append(f"**Files:** {ctx.stage2_loaded} loaded from {ctx.stage1_scanned} scanned")

        if ctx.truncated:
            lines.append("")
            lines.append("⚠️ Context truncated — some files omitted due to budget limits.")
            lines.append("Use read_file tool to load specific files on demand.")

        lines.append("")
        lines.append("---")

        for f in ctx.files:
            lines.append("")
            lines.append(f"### {f.filename} [`{f.layer}/{f.file_type}`]")
            lines.append(f"*Relevance: {f.relevance_score:.2f} | Reason: {f.load_reason}*")
            lines.append("")
            lines.append(f.content)

        lines.append("")
        lines.append("---")
        lines.append(f"*End of vault context ({ctx.stage2_loaded} files, ~{ctx.total_tokens} tokens)*")

        return "\n".join(lines)

    def _format_compact(self, ctx: VaultContext) -> str:
        """Compact format — file summaries only."""
        lines = []
        lines.append("## Vault Context (Compact)")
        lines.append(f"Project: {ctx.project or 'none'} | Topic: {ctx.topic or 'general'}")
        lines.append(f"Files: {ctx.stage2_loaded} | Tokens: ~{ctx.total_tokens}/{ctx.budget_tokens}")
        lines.append("")

        for f in ctx.files:
            # Extract just the summary
            summary = self._extract_summary(f.content)
            if summary:
                lines.append(f"**{f.filename}** [{f.layer}]: {summary}")
            else:
                # First 100 chars
                preview = f.content[:100].replace("\n", " ")
                lines.append(f"**{f.filename}** [{f.layer}]: {preview}...")

        return "\n".join(lines)

    def _format_minimal(self, ctx: VaultContext) -> str:
        """Minimal format — just file list and metadata."""
        lines = []
        lines.append("## Vault Files Available")
        lines.append(f"Project: {ctx.project or 'none'}")

        for f in ctx.files:
            lines.append(f"- `{f.filename}` [{f.layer}/{f.file_type}] (relevance: {f.relevance_score:.2f})")

        lines.append("")
        lines.append("Use read_file tool to load specific files.")
        return "\n".join(lines)

    def _extract_summary(self, content: str) -> Optional[str]:
        """Extract summary section from content."""
        import re
        match = re.search(r'## Summary\s*\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
        if match:
            summary = match.group(1).strip()
            # Truncate if too long
            if len(summary) > 200:
                summary = summary[:200] + "..."
            return summary
        return None

    def _build_usage_instructions(self) -> str:
        """Build usage instructions for the agent."""
        return """## Vault Usage Instructions

**When to use vault context:**
- Answering questions about the current project
- Making decisions that reference existing research
- Understanding constraints and rules
- Following established patterns

**How to navigate:**
- "Why?" → Follow Derived From links (go deeper, L1→L2→L3→L4)
- "What else?" → Follow Related links (lateral exploration)
- "What does this affect?" → Follow Supports links (go up, L4→L3→L2→L1)

**When to load more files:**
- User asks about a specific topic not in current context
- Need deeper research (L4) to answer a question
- Checking constraints (L3) before making a decision
- Exploring related components (L2)

**File types:**
- `overview` (L1): Project goals, status, decisions
- `component` (L2): Parts, interfaces, specifications
- `rule` (L3): Constraints, thresholds, requirements
- `research` (L4): Principles, papers, analysis
- `decision`: Decision records with reasoning chains

**Remember:**
- Always link new files to existing ones with [[wiki-links]]
- Update the `updated` field when modifying files
- State confidence level in your responses
- Surface contradictions rather than picking sides"""


# ─── Standalone Functions ─────────────────────────────────────────

def build_context_for_hermes(
    project: Optional[str] = None,
    topic: Optional[str] = None,
    vault_path: str = "~/.hermes/memory",
) -> str:
    """
    Quick function to build vault context for Hermes agent.
    Returns ready-to-inject text.
    """
    builder = PromptBuilder(vault_path)
    return builder.build_system_prompt_extension(
        project=project,
        topic=topic,
    )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    builder = PromptBuilder(vault)

    if cmd == "build":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        topic = sys.argv[3] if len(sys.argv) > 3 else None
        fmt = sys.argv[4] if len(sys.argv) > 4 else "full"

        ctx = builder.build_vault_context(project=project, topic=topic, format=fmt)
        print(ctx.vault_section)
        print()
        print(f"[{ctx.file_count} files, ~{ctx.token_count} tokens]")

    elif cmd == "extension":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        topic = sys.argv[3] if len(sys.argv) > 3 else None

        ext = builder.build_system_prompt_extension(project=project, topic=topic)
        print(ext)

    elif cmd == "nav":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: prompt_integration.py nav <project>")
            sys.exit(1)
        print(builder.build_layer_navigation(project))

    elif cmd == "layers":
        project = sys.argv[2] if len(sys.argv) > 2 else "eeg"
        builder.layer_state.set_project(project)
        for layer in builder.layer_state.available_layers():
            marker = " <-- current" if layer["current"] else ""
            print(f"  {layer['layer']} | {layer['name']:12} | {layer['file_count']} files{marker}")

    else:
        print("Commands: build [project] [topic] [format], extension [project] [topic], nav <project>, layers [project]")

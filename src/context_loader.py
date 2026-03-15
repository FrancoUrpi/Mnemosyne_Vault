#!/usr/bin/env python3
"""
Context Loader for Mnemosyne Knowledge Vault.

Implements two-stage retrieval:
  Stage 1: Scan frontmatter of all files (fast, low cost)
  Stage 2: Load full content of most relevant files (targeted)

Usage:
    from context_loader import ContextLoader

    loader = ContextLoader(vault_path="~/.hermes/memory")
    context = loader.load_context(
        project="eeg",
        topic="electrode materials",
        budget_tokens=4000
    )
    print(context.to_prompt_section())
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from vault_utils import (
    scan_vault, read_vault_file, extract_links,
    find_by_layer, find_by_project
)
from relevance import RelevanceScorer, ScoredFile
from budget import BudgetManager, TokenEstimate


# ─── Constants ────────────────────────────────────────────────────

ALWAYS_LOAD = [
    "_index.md",
    "user/active_context.md",
]

PROJECT_ALWAYS_LOAD = [
    "_overview.md",
]

# Rough token estimation: 1 token ≈ 4 chars for English text
CHARS_PER_TOKEN = 4


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class LoadedFile:
    """A file loaded into context."""
    path: str
    filename: str
    file_id: str
    layer: str
    file_type: str
    content: str
    metadata: Dict
    token_estimate: int
    relevance_score: float
    load_reason: str  # "always", "project", "relevant", "linked"


@dataclass
class VaultContext:
    """Complete vault context ready for prompt injection."""
    project: Optional[str]
    topic: Optional[str]
    total_tokens: int
    budget_tokens: int
    files: List[LoadedFile]
    truncated: bool  # True if some files were cut due to budget
    stage1_scanned: int  # How many files scanned in stage 1
    stage2_loaded: int   # How many files loaded in stage 2
    load_time_ms: float

    def to_prompt_section(self) -> str:
        """Format context as a prompt section."""
        lines = []
        lines.append("=" * 60)
        lines.append("KNOWLEDGE VAULT CONTEXT")
        lines.append("=" * 60)
        lines.append(f"Project: {self.project or '(none)'}")
        lines.append(f"Topic: {self.topic or '(general)'}")
        lines.append(f"Files: {self.stage2_loaded} loaded / {self.stage1_scanned} scanned")
        lines.append(f"Tokens: ~{self.total_tokens} / {self.budget_tokens} budget")
        if self.truncated:
            lines.append("[WARNING: Context truncated due to budget]")
        lines.append("")

        for f in self.files:
            lines.append(f"--- {f.filename} [{f.layer}/{f.file_type}] ---")
            lines.append(f"Relevance: {f.relevance_score:.2f} | Reason: {f.load_reason}")
            lines.append(f.content)
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_compact(self) -> str:
        """Compact summary for logging."""
        files_str = ", ".join(f.filename for f in self.files)
        return (
            f"VaultContext(project={self.project}, topic={self.topic}, "
            f"files={self.stage2_loaded}, tokens={self.total_tokens}/{self.budget_tokens}, "
            f"truncated={self.truncated})"
        )

    def get_file_by_id(self, file_id: str) -> Optional[LoadedFile]:
        """Find a loaded file by ID."""
        for f in self.files:
            if f.file_id == file_id or f.filename == file_id:
                return f
        return None

    def get_files_by_layer(self, layer: str) -> List[LoadedFile]:
        """Get all loaded files at a specific layer."""
        return [f for f in self.files if f.layer == layer]


# ─── Context Loader ───────────────────────────────────────────────

class ContextLoader:
    """
    Two-stage vault context loader.

    Stage 1 (Scan): Read frontmatter of all vault files — fast, minimal cost.
    Stage 2 (Load): Load full content of most relevant files within budget.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.scorer = RelevanceScorer()
        self.budget = BudgetManager()

    def load_context(
        self,
        project: Optional[str] = None,
        topic: Optional[str] = None,
        budget_tokens: int = 4000,
        max_files: int = 8,
        extra_files: Optional[List[str]] = None,
    ) -> VaultContext:
        """
        Load vault context with two-stage retrieval.

        Args:
            project: Current project name (loads project overview)
            topic: Current topic for relevance scoring
            budget_tokens: Maximum tokens for vault context
            max_files: Maximum number of files to load
            extra_files: Specific file IDs to always include

        Returns:
            VaultContext with loaded files ready for prompt injection
        """
        import time
        start_time = time.time()

        extra_files = extra_files or []
        loaded_files = []
        total_tokens = 0
        truncated = False

        # ─── Stage 1: Scan all frontmatter ────────────────────────
        all_metadata = scan_vault(self.vault_path)
        stage1_count = len(all_metadata)

        # ─── Always-load files ────────────────────────────────────
        for rel_path in ALWAYS_LOAD:
            abs_path = os.path.join(self.vault_path, rel_path)
            if os.path.exists(abs_path):
                meta, body = read_vault_file(abs_path)
                tokens = self._estimate_tokens(body)
                loaded_files.append(LoadedFile(
                    path=abs_path,
                    filename=Path(abs_path).stem,
                    file_id=meta.get("id", Path(abs_path).stem),
                    layer=meta.get("layer", "cross"),
                    file_type=meta.get("type", "context"),
                    content=body.strip(),
                    metadata=meta,
                    token_estimate=tokens,
                    relevance_score=1.0,
                    load_reason="always"
                ))
                total_tokens += tokens

        # ─── Project overview (if in project) ─────────────────────
        if project:
            overview_path = os.path.join(
                self.vault_path, "projects", project, "_overview.md"
            )
            if os.path.exists(overview_path):
                meta, body = read_vault_file(overview_path)
                tokens = self._estimate_tokens(body)
                loaded_files.append(LoadedFile(
                    path=overview_path,
                    filename="_overview",
                    file_id=meta.get("id", "_overview"),
                    layer="L1",
                    file_type="overview",
                    content=body.strip(),
                    metadata=meta,
                    token_estimate=tokens,
                    relevance_score=1.0,
                    load_reason="project"
                ))
                total_tokens += tokens

        # ─── Stage 2: Score and load relevant files ───────────────
        remaining_budget = budget_tokens - total_tokens
        remaining_slots = max_files - len(loaded_files)

        if remaining_budget > 0 and remaining_slots > 0:
            # Score all files not already loaded
            loaded_paths = {f.path for f in loaded_files}
            candidates = []

            for meta in all_metadata:
                path = meta.get("_path", "")
                if path in loaded_paths:
                    continue
                if ".private" in path:
                    continue

                # Score this file
                score = self.scorer.score(
                    metadata=meta,
                    topic=topic,
                    project=project,
                    vault_path=self.vault_path,
                )
                candidates.append((meta, score))

            # Sort by score descending
            candidates.sort(key=lambda x: x[1].total_score, reverse=True)

            # Load top files within budget
            for meta, score in candidates[:remaining_slots * 2]:  # Check 2x for budget
                if total_tokens >= budget_tokens:
                    truncated = True
                    break

                path = meta.get("_path", "")
                if not os.path.exists(path):
                    continue

                file_meta, body = read_vault_file(path)
                tokens = self._estimate_tokens(body)

                if total_tokens + tokens > budget_tokens:
                    # Try loading just the summary section
                    summary = self._extract_summary(body)
                    if summary:
                        tokens = self._estimate_tokens(summary)
                        if total_tokens + tokens <= budget_tokens:
                            body = summary + "\n\n[... truncated for budget ...]"
                        else:
                            truncated = True
                            break
                    else:
                        truncated = True
                        break

                loaded_files.append(LoadedFile(
                    path=path,
                    filename=meta.get("_filename", Path(path).stem),
                    file_id=file_meta.get("id", meta.get("_filename", "")),
                    layer=file_meta.get("layer", "cross"),
                    file_type=file_meta.get("type", "unknown"),
                    content=body.strip(),
                    metadata=file_meta,
                    token_estimate=tokens,
                    relevance_score=score.total_score,
                    load_reason="relevant"
                ))
                total_tokens += tokens

        # ─── Load explicitly requested files ──────────────────────
        for file_id in extra_files:
            if total_tokens >= budget_tokens:
                break
            # Skip if already loaded
            if any(f.file_id == file_id for f in loaded_files):
                continue

            resolved = self._resolve_file_id(file_id, project)
            if resolved and os.path.exists(resolved):
                meta, body = read_vault_file(resolved)
                tokens = self._estimate_tokens(body)
                if total_tokens + tokens <= budget_tokens:
                    loaded_files.append(LoadedFile(
                        path=resolved,
                        filename=Path(resolved).stem,
                        file_id=meta.get("id", file_id),
                        layer=meta.get("layer", "cross"),
                        file_type=meta.get("type", "unknown"),
                        content=body.strip(),
                        metadata=meta,
                        token_estimate=tokens,
                        relevance_score=1.0,
                        load_reason="linked"
                    ))
                    total_tokens += tokens

        elapsed_ms = (time.time() - start_time) * 1000

        return VaultContext(
            project=project,
            topic=topic,
            total_tokens=total_tokens,
            budget_tokens=budget_tokens,
            files=loaded_files,
            truncated=truncated,
            stage1_scanned=stage1_count,
            stage2_loaded=len(loaded_files),
            load_time_ms=elapsed_ms,
        )

    def load_by_layer(
        self,
        layer: str,
        project: Optional[str] = None,
        budget_tokens: int = 4000,
    ) -> VaultContext:
        """Load all files at a specific layer."""
        files = find_by_layer(layer, self.vault_path, project)
        loaded = []
        total_tokens = 0

        for meta in files:
            path = meta.get("_path", "")
            if not os.path.exists(path):
                continue

            fm, body = read_vault_file(path)
            tokens = self._estimate_tokens(body)

            if total_tokens + tokens > budget_tokens:
                break

            loaded.append(LoadedFile(
                path=path,
                filename=meta.get("_filename", ""),
                file_id=fm.get("id", ""),
                layer=fm.get("layer", layer),
                file_type=fm.get("type", "unknown"),
                content=body.strip(),
                metadata=fm,
                token_estimate=tokens,
                relevance_score=1.0,
                load_reason="layer"
            ))
            total_tokens += tokens

        return VaultContext(
            project=project,
            topic=f"layer:{layer}",
            total_tokens=total_tokens,
            budget_tokens=budget_tokens,
            files=loaded,
            truncated=False,
            stage1_scanned=len(files),
            stage2_loaded=len(loaded),
            load_time_ms=0,
        )

    def refresh_context(
        self,
        context: VaultContext,
        new_topic: Optional[str] = None,
    ) -> VaultContext:
        """Re-load context with updated topic (e.g., after topic shift)."""
        return self.load_context(
            project=context.project,
            topic=new_topic or context.topic,
            budget_tokens=context.budget_tokens,
        )

    # ─── Helpers ──────────────────────────────────────────────────

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text."""
        return len(text) // CHARS_PER_TOKEN

    def _extract_summary(self, body: str) -> Optional[str]:
        """Extract just the Summary section from a vault file."""
        match = re.search(
            r'## Summary\s*\n(.*?)(?=\n## |\Z)',
            body,
            re.DOTALL
        )
        if match:
            return f"## Summary\n{match.group(1).strip()}"
        return None

    def _resolve_file_id(self, file_id: str, project: Optional[str]) -> Optional[str]:
        """Resolve a file ID to its path in the vault."""
        # Try exact filename match
        for md_file in Path(self.vault_path).rglob("*.md"):
            if md_file.stem == file_id:
                return str(md_file)

        # Try frontmatter id match
        for md_file in Path(self.vault_path).rglob("*.md"):
            try:
                meta, _ = read_vault_file(str(md_file))
                if meta.get("id") == file_id:
                    return str(md_file)
            except Exception:
                continue

        return None


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    loader = ContextLoader(vault)

    if cmd == "load":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        topic = sys.argv[3] if len(sys.argv) > 3 else None
        budget = int(sys.argv[4]) if len(sys.argv) > 4 else 4000

        ctx = loader.load_context(project=project, topic=topic, budget_tokens=budget)
        print(ctx.to_prompt_section())

    elif cmd == "layer":
        layer = sys.argv[2] if len(sys.argv) > 2 else "L1"
        project = sys.argv[3] if len(sys.argv) > 3 else None

        ctx = loader.load_by_layer(layer=layer, project=project)
        print(f"Layer {layer}: {ctx.stage2_loaded} files, ~{ctx.total_tokens} tokens")
        for f in ctx.files:
            print(f"  [{f.layer}] {f.filename} ({f.token_estimate} tokens)")

    elif cmd == "compact":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        topic = sys.argv[3] if len(sys.argv) > 3 else None

        ctx = loader.load_context(project=project, topic=topic)
        print(ctx.to_compact())

    else:
        print("Commands: load [project] [topic] [budget], layer <L1-L4> [project], compact [project] [topic]")

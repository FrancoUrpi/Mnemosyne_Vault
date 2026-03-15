#!/usr/bin/env python3
"""
Layer Traversal Integrator for Mnemosyne Knowledge Vault.

Wires together layer_state, vault_search, link_navigator, and on_demand
into a unified navigation interface for the agent.

Provides:
  - Context-aware layer navigation
  - Search + layer filtering
  - Drill-down with automatic context loading
  - Reasoning chain reconstruction
  - Navigation state tracking across a session

Usage:
    from traversal import VaultNavigator

    nav = VaultNavigator(vault_path="~/.hermes/memory")
    
    # Start at project overview
    nav.enter_project("eeg")
    
    # Drill down to understand a component
    result = nav.drill_to("gold_electrodes")
    
    # Search within current context
    results = nav.search_in_context("oxidation")
    
    # Get full navigation state
    state = nav.get_state()
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from layer_state import LayerState, TraversalMode, LAYER_ORDER
from vault_search import VaultSearch, SearchResult
from link_navigator import LinkNavigator, LinkNode, TraversalResult
from on_demand import OnDemandRetriever, RetrievedFile
from context_loader import ContextLoader, VaultContext
from vault_utils import read_vault_file, extract_links


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class NavigationStep:
    """A single navigation step."""
    action: str  # "enter_project", "drill_down", "synthesize_up", "search", "follow_link"
    from_layer: Optional[str]
    to_layer: Optional[str]
    file_id: Optional[str]
    reason: str
    timestamp: datetime


@dataclass
class DrillResult:
    """Result of a drill-down operation."""
    target_file: RetrievedFile
    context_above: List[RetrievedFile]  # Higher layer context
    context_below: List[RetrievedFile]  # Deeper layer context
    related: List[RetrievedFile]  # Same layer
    reasoning_chain: List[LinkNode]
    total_tokens: int


@dataclass
class NavigationState:
    """Complete navigation state."""
    project: Optional[str]
    current_layer: str
    current_file: Optional[str]
    history: List[NavigationStep]
    files_loaded: int
    tokens_used: int
    can_go_deeper: bool
    can_go_higher: bool


# ─── Vault Navigator ──────────────────────────────────────────────

class VaultNavigator:
    """
    Unified navigation interface for the Mnemosyne vault.

    Integrates all Week 1-3 components into a single navigation API.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)

        # Initialize components
        self.layer_state = LayerState(vault_path)
        self.search = VaultSearch(vault_path)
        self.link_nav = LinkNavigator(vault_path)
        self.retriever = OnDemandRetriever(vault_path)
        self.context_loader = ContextLoader(vault_path)

        # Navigation state
        self._project: Optional[str] = None
        self._current_layer: str = "L1"
        self._current_file: Optional[str] = None
        self._history: List[NavigationStep] = []
        self._files_loaded: int = 0
        self._tokens_used: int = 0

    # ─── Project Navigation ───────────────────────────────────────

    def enter_project(self, project: str) -> Dict:
        """
        Enter a project. Loads the L1 overview.

        Returns project summary with available layers.
        """
        self._project = project
        self._current_layer = "L1"
        self.layer_state.set_project(project)

        # Load overview
        overview = self.retriever.get("_overview", reason="project_entry")
        if overview:
            self._current_file = overview.file_id
            self._files_loaded += 1
            self._tokens_used += overview.token_estimate

        # Get layer info
        layers = self.layer_state.available_layers()

        self._add_step("enter_project", None, "L1", "_overview", f"Entered {project}")

        return {
            "project": project,
            "current_layer": "L1",
            "overview": overview,
            "layers": layers,
            "total_files": sum(l["file_count"] for l in layers),
        }

    def exit_project(self) -> None:
        """Exit current project."""
        self._add_step("exit_project", self._current_layer, None, None, f"Exited {self._project}")
        self._project = None
        self._current_layer = "L1"
        self._current_file = None

    # ─── Layer Navigation ─────────────────────────────────────────

    def drill_down(self, reason: str = "") -> Optional[Dict]:
        """Move to next deeper layer (L1->L2->L3->L4)."""
        old_layer = self._current_layer
        result = self.layer_state.drill_down(reason)

        if "error" in result:
            return None

        self._current_layer = result["layer"]
        self._add_step("drill_down", old_layer, self._current_layer, None, reason)

        # Load files at this layer
        files = self.retriever.get_by_layer(
            self._current_layer,
            project=self._project,
            reason="layer_drill"
        )
        self._files_loaded += len(files)

        return {
            "layer": self._current_layer,
            "layer_name": result.get("layer_name", ""),
            "files": files,
            "file_count": len(files),
        }

    def synthesize_up(self, reason: str = "") -> Optional[Dict]:
        """Move to next higher layer (L4->L3->L2->L1)."""
        old_layer = self._current_layer
        result = self.layer_state.synthesize_up(reason)

        if "error" in result:
            return None

        self._current_layer = result["layer"]
        self._add_step("synthesize_up", old_layer, self._current_layer, None, reason)

        files = self.retriever.get_by_layer(
            self._current_layer,
            project=self._project,
            reason="layer_synth"
        )
        self._files_loaded += len(files)

        return {
            "layer": self._current_layer,
            "layer_name": result.get("layer_name", ""),
            "files": files,
            "file_count": len(files),
        }

    def go_to_layer(self, layer: str, reason: str = "") -> Dict:
        """Jump directly to a layer."""
        old_layer = self._current_layer
        self.layer_state.set_layer(layer)
        self._current_layer = layer
        self._add_step("go_to_layer", old_layer, layer, None, reason or f"Jump to {layer}")

        files = self.retriever.get_by_layer(layer, project=self._project, reason="direct")
        self._files_loaded += len(files)

        return {
            "layer": layer,
            "files": files,
            "file_count": len(files),
        }

    # ─── File Navigation ──────────────────────────────────────────

    def drill_to(self, file_id: str) -> Optional[DrillResult]:
        """
        Drill into a specific file with full context.

        Loads the file, its layer context, reasoning chain, and related files.
        """
        # Load target file
        target = self.retriever.get(file_id, reason="drill_target")
        if not target:
            return None

        self._current_file = file_id
        self._current_layer = target.layer
        self._files_loaded += 1
        self._tokens_used += target.token_estimate

        # Get layer context
        layer_ctx = self.retriever.get_layer_context(file_id, reason="context")
        self._files_loaded += len(layer_ctx["above"]) + len(layer_ctx["same"]) + len(layer_ctx["below"])

        # Get reasoning chain
        chain = self.link_nav.get_reasoning_chain(file_id, direction="up")

        # Find similar files
        similar = self.search.search_similar(file_id, limit=3)
        related = []
        for sr in similar:
            f = self.retriever.get(sr.file_id, reason="related")
            if f:
                related.append(f)

        total_tokens = (
            target.token_estimate +
            sum(f.token_estimate for f in layer_ctx["above"]) +
            sum(f.token_estimate for f in layer_ctx["below"]) +
            sum(f.token_estimate for f in related)
        )
        self._tokens_used += total_tokens

        self._add_step("drill_to", None, target.layer, file_id, f"Drilled to {file_id}")

        return DrillResult(
            target_file=target,
            context_above=layer_ctx["above"],
            context_below=layer_ctx["below"],
            related=related,
            reasoning_chain=chain,
            total_tokens=total_tokens,
        )

    def follow_link(self, link_target: str) -> Optional[RetrievedFile]:
        """Navigate to a file via [[link]]."""
        retrieved = self.retriever.get(link_target, reason="link_follow")
        if retrieved:
            self._current_file = retrieved.file_id
            self._current_layer = retrieved.layer
            self._files_loaded += 1
            self._tokens_used += retrieved.token_estimate
            self._add_step("follow_link", None, retrieved.layer, retrieved.file_id, f"Followed [[{link_target}]]")
        return retrieved

    def go_back(self) -> Optional[NavigationStep]:
        """Go back to previous navigation step."""
        if len(self._history) < 2:
            return None

        # Remove current step
        self._history.pop()
        # Get previous step
        prev = self._history[-1]

        # Restore state
        if prev.to_layer:
            self._current_layer = prev.to_layer
        if prev.file_id:
            self._current_file = prev.file_id

        return prev

    # ─── Search ───────────────────────────────────────────────────

    def search_in_context(
        self,
        query: str,
        limit: int = 10,
    ) -> List[SearchResult]:
        """
        Search within current project/layer context.
        """
        results = self.search.search(
            query,
            project=self._project,
            limit=limit,
        )
        self._add_step("search", self._current_layer, self._current_layer, None, f"Searched: {query}")
        return results

    def search_global(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search across entire vault (no project filter)."""
        return self.search.search(query, limit=limit)

    def find_links_to(self, file_id: str) -> List[SearchResult]:
        """Find all files that link to a specific file."""
        return self.search.search_by_link(file_id)

    # ─── Graph Exploration ────────────────────────────────────────

    def explore_neighborhood(
        self,
        file_id: Optional[str] = None,
        depth: int = 2,
    ) -> TraversalResult:
        """Explore the link neighborhood of a file."""
        fid = file_id or self._current_file
        if not fid:
            return TraversalResult("", [], [], 0, 0)
        return self.link_nav.get_neighborhood(fid, depth=depth)

    def find_path_to(self, target_id: str, start_id: Optional[str] = None):
        """Find link path from current/specified file to target."""
        start = start_id or self._current_file
        if not start:
            return None
        return self.link_nav.find_path(start, target_id)

    def get_reasoning_chain(
        self,
        file_id: Optional[str] = None,
        direction: str = "up",
    ) -> List[LinkNode]:
        """Get reasoning chain from a file."""
        fid = file_id or self._current_file
        if not fid:
            return []
        return self.link_nav.get_reasoning_chain(fid, direction=direction)

    # ─── State ────────────────────────────────────────────────────

    def get_state(self) -> NavigationState:
        """Get current navigation state."""
        layer_idx = LAYER_ORDER.index(self._current_layer) if self._current_layer in LAYER_ORDER else -1

        return NavigationState(
            project=self._project,
            current_layer=self._current_layer,
            current_file=self._current_file,
            history=list(self._history),
            files_loaded=self._files_loaded,
            tokens_used=self._tokens_used,
            can_go_deeper=layer_idx < 3,
            can_go_higher=layer_idx > 0,
        )

    def get_history(self) -> List[Dict]:
        """Get navigation history."""
        return [
            {
                "action": s.action,
                "from": s.from_layer,
                "to": s.to_layer,
                "file": s.file_id,
                "reason": s.reason,
                "time": s.timestamp.isoformat(),
            }
            for s in self._history
        ]

    def reset(self) -> None:
        """Reset navigation state."""
        self._project = None
        self._current_layer = "L1"
        self._current_file = None
        self._history.clear()
        self._files_loaded = 0
        self._tokens_used = 0
        self.retriever.clear_cache()

    def _add_step(
        self,
        action: str,
        from_layer: Optional[str],
        to_layer: Optional[str],
        file_id: Optional[str],
        reason: str,
    ) -> None:
        """Record a navigation step."""
        self._history.append(NavigationStep(
            action=action,
            from_layer=from_layer,
            to_layer=to_layer,
            file_id=file_id,
            reason=reason,
            timestamp=datetime.now(),
        ))


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    nav = VaultNavigator(vault)

    if cmd == "enter":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: traversal.py enter <project>")
            sys.exit(1)
        result = nav.enter_project(project)
        print(f"Entered project: {result['project']}")
        print(f"Total files: {result['total_files']}")
        for layer in result["layers"]:
            marker = " <-- current" if layer["current"] else ""
            print(f"  {layer['layer']} | {layer['name']:12} | {layer['file_count']} files{marker}")

    elif cmd == "drill":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if target:
            result = nav.drill_to(target)
            if result:
                print(f"Drilled to: {result.target_file.file_id} [{result.target_file.layer}]")
                print(f"Above: {len(result.context_above)} files")
                print(f"Below: {len(result.context_below)} files")
                print(f"Related: {len(result.related)} files")
                print(f"Reasoning chain: {' -> '.join(n.file_id for n in result.reasoning_chain)}")
                print(f"Tokens: ~{result.total_tokens}")
            else:
                print(f"File '{target}' not found")
        else:
            result = nav.drill_down("CLI drill down")
            if result:
                print(f"Now at {result['layer']} ({result['layer_name']}): {result['file_count']} files")
                for f in result["files"]:
                    print(f"  [{f.layer}] {f.file_id}")
            else:
                print("Cannot drill deeper")

    elif cmd == "up":
        result = nav.synthesize_up("CLI synthesize up")
        if result:
            print(f"Now at {result['layer']} ({result['layer_name']}): {result['file_count']} files")
        else:
            print("Cannot go higher")

    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Usage: traversal.py search <query>")
            sys.exit(1)
        results = nav.search_in_context(query)
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  {r.score:.2f} [{r.layer}] {r.file_id}: {r.snippet[:60]}")

    elif cmd == "state":
        state = nav.get_state()
        print(f"Project: {state.project or '(none)'}")
        print(f"Layer: {state.current_layer}")
        print(f"Current file: {state.current_file or '(none)'}")
        print(f"Files loaded: {state.files_loaded}")
        print(f"Tokens used: ~{state.tokens_used}")
        print(f"Can go deeper: {state.can_go_deeper}")
        print(f"Can go higher: {state.can_go_higher}")
        print(f"History: {len(state.history)} steps")

    elif cmd == "history":
        history = nav.get_history()
        for step in history[-10:]:
            print(f"  {step['action']:15} {step.get('from', '-'):3} -> {step.get('to', '-'):3}  {step['reason']}")

    else:
        print("Commands: enter <project>, drill [target], up, search <query>, state, history")

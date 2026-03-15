#!/usr/bin/env python3
"""
Layer State Machine for Mnemosyne Knowledge Vault.

Manages traversal between abstraction layers (L1-L4) and tracks context.
Supports three traversal modes: drill_down, synthesize_up, lateral.

Layers:
  L1: SURFACE      — Decisions, goals, status
  L2: COMPONENTS   — Parts, interfaces
  L3: RULES        — Constraints, specs
  L4: DETERMINANTS — Physics, research, principles

Usage:
    from layer_state import LayerState, TraversalMode

    state = LayerState(vault_path="~/.hermes/memory")
    state.set_project("eeg")
    state.set_layer("L1")

    # Drill down: L1 -> L2
    result = state.traverse(TraversalMode.DRILL_DOWN)
    print(f"Now at {result['layer']}, loaded {len(result['files'])} files")

    # Get current context summary
    context = state.get_context()
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from vault_utils import (
    scan_vault, find_by_layer, find_by_project,
    read_vault_file, extract_links, resolve_link
)


class TraversalMode(Enum):
    DRILL_DOWN = "drill_down"       # L1 -> L2 -> L3 -> L4
    SYNTHESIZE_UP = "synthesize_up" # L4 -> L3 -> L2 -> L1
    LATERAL = "lateral"             # Same layer, different files
    DIRECT = "direct"               # Jump to specific layer


LAYER_ORDER = ["L1", "L2", "L3", "L4"]
LAYER_INFO = {
    "L1": {
        "name": "SURFACE",
        "description": "Decisions, goals, status",
        "folder": None,  # _overview.md at project root
        "file_types": ["overview"],
    },
    "L2": {
        "name": "COMPONENTS",
        "description": "Parts, interfaces",
        "folder": "components",
        "file_types": ["component"],
    },
    "L3": {
        "name": "RULES",
        "description": "Constraints, specs",
        "folder": "rules",
        "file_types": ["rule"],
    },
    "L4": {
        "name": "DETERMINANTS",
        "description": "Physics, research, principles",
        "folder": "research",
        "file_types": ["research"],
    },
}


@dataclass
class LayerTransition:
    """Record of a layer transition."""
    from_layer: str
    to_layer: str
    mode: TraversalMode
    reason: str
    files_loaded: List[str] = field(default_factory=list)


@dataclass
class LayerState:
    """
    Manages the current layer context and traversal state.
    """
    vault_path: str
    current_layer: str = "L1"
    current_project: Optional[str] = None
    current_files: List[Dict] = field(default_factory=list)
    history: List[LayerTransition] = field(default_factory=list)
    _loaded_file_paths: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.vault_path = os.path.expanduser(self.vault_path)

    # ─── Layer Management ─────────────────────────────────────────

    def set_layer(self, layer: str) -> Dict:
        """Set current layer directly. Returns loaded files."""
        if layer not in LAYER_ORDER and layer != "cross":
            raise ValueError(f"Invalid layer: {layer}. Must be one of {LAYER_ORDER + ['cross']}")

        old_layer = self.current_layer
        self.current_layer = layer
        self._load_layer_files()

        self.history.append(LayerTransition(
            from_layer=old_layer,
            to_layer=layer,
            mode=TraversalMode.DIRECT,
            reason="Direct layer set"
        ))

        return self.get_context()

    def set_project(self, project: str) -> None:
        """Set current project context."""
        project_path = Path(self.vault_path) / "projects" / project
        if not project_path.exists():
            raise ValueError(f"Project '{project}' not found at {project_path}")
        self.current_project = project
        self._load_layer_files()

    # ─── Traversal ────────────────────────────────────────────────

    def traverse(self, mode: TraversalMode, reason: str = "") -> Dict:
        """
        Traverse to another layer based on mode.

        Returns context dict with:
          - layer: new layer name
          - layer_info: metadata about the layer
          - files: list of loaded file metadata
          - navigation: where you can go from here
        """
        old_layer = self.current_layer

        if mode == TraversalMode.DRILL_DOWN:
            new_layer = self._next_layer_down()
        elif mode == TraversalMode.SYNTHESIZE_UP:
            new_layer = self._next_layer_up()
        elif mode == TraversalMode.LATERAL:
            new_layer = self.current_layer  # Stay, reload with different view
        else:
            raise ValueError(f"Use set_layer() for DIRECT mode")

        if new_layer is None:
            return {
                "layer": self.current_layer,
                "error": f"Cannot {mode.value} from {self.current_layer}",
                "files": self.current_files,
            }

        self.current_layer = new_layer
        self._load_layer_files()

        self.history.append(LayerTransition(
            from_layer=old_layer,
            to_layer=new_layer,
            mode=mode,
            reason=reason or mode.value,
            files_loaded=self._loaded_file_paths
        ))

        return self.get_context()

    def drill_down(self, reason: str = "") -> Dict:
        """Convenience: drill down one layer."""
        return self.traverse(TraversalMode.DRILL_DOWN, reason)

    def synthesize_up(self, reason: str = "") -> Dict:
        """Convenience: synthesize up one layer."""
        return self.traverse(TraversalMode.SYNTHESIZE_UP, reason)

    def lateral(self, reason: str = "") -> Dict:
        """Convenience: explore laterally (same layer)."""
        return self.traverse(TraversalMode.LATERAL, reason)

    # ─── Context ──────────────────────────────────────────────────

    def get_context(self) -> Dict:
        """Get current context summary."""
        layer_idx = LAYER_ORDER.index(self.current_layer) if self.current_layer in LAYER_ORDER else -1

        navigation = {}
        if layer_idx > 0:
            navigation["drill_down"] = LAYER_ORDER[layer_idx + 1] if layer_idx < 3 else None
            navigation["synthesize_up"] = LAYER_ORDER[layer_idx - 1] if layer_idx > 0 else None
        else:
            navigation["drill_down"] = "L2" if self.current_layer == "L1" else None
            navigation["synthesize_up"] = None

        if self.current_layer == "L1":
            navigation["drill_down"] = "L2"
            navigation["synthesize_up"] = None
        elif self.current_layer == "L4":
            navigation["drill_down"] = None
            navigation["synthesize_up"] = "L3"

        return {
            "layer": self.current_layer,
            "layer_name": LAYER_INFO.get(self.current_layer, {}).get("name", "CROSS"),
            "layer_description": LAYER_INFO.get(self.current_layer, {}).get("description", ""),
            "project": self.current_project,
            "files": self.current_files,
            "file_count": len(self.current_files),
            "navigation": navigation,
            "history_length": len(self.history),
        }

    def get_history(self) -> List[Dict]:
        """Get traversal history."""
        return [
            {
                "from": t.from_layer,
                "to": t.to_layer,
                "mode": t.mode.value,
                "reason": t.reason,
            }
            for t in self.history
        ]

    def get_reasoning_chain(self) -> List[Dict]:
        """
        Get the current reasoning chain (L4 -> L3 -> L2 -> L1).
        Reconstructs from history.
        """
        chain = []
        for t in self.history:
            if t.mode in (TraversalMode.DRILL_DOWN, TraversalMode.SYNTHESIZE_UP):
                chain.append({
                    "layer": t.to_layer,
                    "action": t.mode.value,
                    "reason": t.reason,
                    "files": t.files_loaded,
                })
        return chain

    # ─── File Loading ─────────────────────────────────────────────

    def _load_layer_files(self) -> None:
        """Load files for current layer and project."""
        if not self.current_project:
            self.current_files = []
            self._loaded_file_paths = []
            return

        files = find_by_layer(self.current_layer, self.vault_path, self.current_project)

        # Also load files with layer=cross that mention this project
        if self.current_layer != "cross":
            cross_files = find_by_layer("cross", self.vault_path, self.current_project)
            files.extend(cross_files)

        # Enrich with file content preview
        enriched = []
        for f in files:
            path = f.get("_path", "")
            if path and os.path.exists(path):
                metadata, body = read_vault_file(path)
                # Get first 200 chars of body as preview
                preview = body.strip()[:200] + "..." if len(body.strip()) > 200 else body.strip()
                enriched.append({
                    "id": metadata.get("id", f.get("_filename", "")),
                    "path": path,
                    "filename": f.get("_filename", ""),
                    "type": metadata.get("type", "unknown"),
                    "layer": metadata.get("layer", self.current_layer),
                    "confidence": metadata.get("confidence", "moderate"),
                    "status": metadata.get("status", "active"),
                    "tags": metadata.get("tags", []),
                    "preview": preview,
                })

        self.current_files = enriched
        self._loaded_file_paths = [f["path"] for f in enriched]

    def load_file_content(self, file_id: str) -> Optional[Dict]:
        """Load full content of a specific file by ID."""
        for f in self.current_files:
            if f["id"] == file_id or f["filename"] == file_id:
                path = f["path"]
                if os.path.exists(path):
                    metadata, body = read_vault_file(path)
                    links = extract_links(body)
                    return {
                        "metadata": metadata,
                        "body": body,
                        "links": links,
                        "path": path,
                    }
        return None

    def follow_link(self, link_target: str) -> Optional[Dict]:
        """Follow a [[link]] to its target file."""
        resolved = resolve_link(link_target, self.vault_path)
        if resolved:
            metadata, body = read_vault_file(resolved)
            # Update layer based on file's layer
            file_layer = metadata.get("layer", "cross")
            if file_layer in LAYER_ORDER:
                self.current_layer = file_layer
                self._load_layer_files()
            return {
                "metadata": metadata,
                "body": body,
                "path": resolved,
                "layer_changed": file_layer != self.current_layer,
            }
        return None

    # ─── Navigation Helpers ───────────────────────────────────────

    def _next_layer_down(self) -> Optional[str]:
        """Get next layer down (L1->L2->L3->L4)."""
        if self.current_layer == "cross":
            return "L2"
        try:
            idx = LAYER_ORDER.index(self.current_layer)
            if idx < len(LAYER_ORDER) - 1:
                return LAYER_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def _next_layer_up(self) -> Optional[str]:
        """Get next layer up (L4->L3->L2->L1)."""
        if self.current_layer == "cross":
            return "L2"
        try:
            idx = LAYER_ORDER.index(self.current_layer)
            if idx > 0:
                return LAYER_ORDER[idx - 1]
        except ValueError:
            pass
        return None

    def available_layers(self) -> List[Dict]:
        """List all layers with file counts."""
        result = []
        for layer in LAYER_ORDER:
            files = find_by_layer(layer, self.vault_path, self.current_project)
            result.append({
                "layer": layer,
                "name": LAYER_INFO[layer]["name"],
                "description": LAYER_INFO[layer]["description"],
                "file_count": len(files),
                "current": layer == self.current_layer,
            })
        return result

    # ─── Vault Init Helper ────────────────────────────────────────

    @staticmethod
    def init_project(vault_path: str, project_name: str) -> str:
        """
        Initialize a new project in the vault.
        Creates directory structure and _overview.md from template.
        Returns path to project root.
        """
        vault_path = os.path.expanduser(vault_path)
        project_root = Path(vault_path) / "projects" / project_name

        if project_root.exists():
            raise ValueError(f"Project '{project_name}' already exists")

        # Create directories
        for subdir in ["components", "rules", "research"]:
            (project_root / subdir).mkdir(parents=True, exist_ok=True)

        # Create _overview.md
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        overview_content = f"""---
id: _overview
type: overview
layer: L1
project: {project_name}
created: {today}
updated: {today}
confidence: moderate
status: active
tags: []
---

# {project_name.title()} — Project Overview

## Summary
Project overview for {project_name}.

## Intent

### Objective
Define the project objective here.

### Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Constraints
- Budget:
- Timeline:
- Scope:

### Decision Autonomy
| Area | Level | Notes |
|------|-------|-------|
| Research | autonomous | |
| Implementation | notify | |
| Spending | approve | |

### Stop Rules
- If unclear → ask user

## Status
**Current Phase:** Planning
**Health:** Green
**Last Activity:** {today}

## Key Decisions
_(none yet)_

## Active Threads
_(none yet)_

## Links

### Derived From
_(none)_

### Supports
_(none)_

### Related
_(none)_
"""
        (project_root / "_overview.md").write_text(overview_content, encoding="utf-8")

        # Create _synthesis.md
        synthesis_content = f"""---
id: _synthesis
type: overview
layer: cross
project: {project_name}
created: {today}
updated: {today}
confidence: low
status: active
tags: [synthesis]
---

# Synthesis: {project_name.title()}

## Summary
_(Synthesis will be built as research accumulates)_

## Key Decisions
_(none yet)_

## Active Rules
_(none yet)_

## Component Map
_(none yet)_

## Current Status
- 🔄 Project initialized

## Open Questions
_(none yet)_

## Links

### Derived From
_(none)_

### Supports
- [[_overview]]

### Related
_(none)_
"""
        (project_root / "_synthesis.md").write_text(synthesis_content, encoding="utf-8")

        return str(project_root)


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "status":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        state = LayerState(vault_path=vault)
        if project:
            state.set_project(project)
        ctx = state.get_context()
        print(f"Layer: {ctx['layer']} ({ctx['layer_name']})")
        print(f"Project: {ctx['project'] or '(none)'}")
        print(f"Files: {ctx['file_count']}")
        print(f"Navigation: {json.dumps(ctx['navigation'])}")

    elif cmd == "layers":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        state = LayerState(vault_path=vault)
        if project:
            state.set_project(project)
        for layer in state.available_layers():
            marker = " <-- current" if layer["current"] else ""
            print(f"  {layer['layer']} | {layer['name']:12} | {layer['file_count']} files | {layer['description']}{marker}")

    elif cmd == "goto":
        layer = sys.argv[2] if len(sys.argv) > 2 else None
        project = sys.argv[3] if len(sys.argv) > 3 else None
        if not layer:
            print("Usage: layer_state.py goto <L1|L2|L3|L4> [project]")
            sys.exit(1)
        state = LayerState(vault_path=vault)
        if project:
            state.set_project(project)
        ctx = state.set_layer(layer)
        print(f"Now at {ctx['layer']} ({ctx['layer_name']})")
        print(f"Files: {ctx['file_count']}")
        for f in ctx["files"]:
            print(f"  - {f['id']} ({f['type']}, {f['confidence']})")

    elif cmd == "init":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: layer_state.py init <project_name>")
            sys.exit(1)
        try:
            path = LayerState.init_project(vault, project)
            print(f"Project '{project}' initialized at {path}")
        except ValueError as e:
            print(f"Error: {e}")

    else:
        print("Commands: status [project], layers [project], goto <layer> [project], init <project>")

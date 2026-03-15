#!/usr/bin/env python3
"""
Link Navigator for Mnemosyne Knowledge Vault.

Provides graph navigation through [[wiki-links]]:
  - Follow links forward (what does this link to?)
  - Follow backlinks backward (what links to this?)
  - Multi-hop traversal (follow chain of links)
  - Graph neighborhood (files within N hops)
  - Path finding (shortest path between two files)

Usage:
    from link_navigator import LinkNavigator

    nav = LinkNavigator(vault_path="~/.hermes/memory")
    
    # Follow links from a file
    links = nav.get_outgoing("gold_electrodes")
    
    # Find what links to a file
    backs = nav.get_backlinks("gold_electrodes")
    
    # Traverse the graph
    neighborhood = nav.get_neighborhood("gold_electrodes", depth=2)
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque

from vault_utils import (
    scan_vault, read_vault_file, extract_links,
    find_by_layer, find_by_project
)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class LinkNode:
    """A node in the link graph."""
    file_id: str
    path: str
    layer: str
    file_type: str
    project: Optional[str]
    depth: int  # Distance from traversal start
    via: Optional[str]  # Which link led here


@dataclass
class LinkEdge:
    """An edge in the link graph (a [[link]] from one file to another)."""
    source_id: str
    target_id: str
    source_path: str
    resolved: bool  # Whether target exists
    context: str  # Surrounding text of the link


@dataclass
class TraversalResult:
    """Result of a graph traversal."""
    start_node: str
    nodes: List[LinkNode]
    edges: List[LinkEdge]
    depth_reached: int
    total_files_visited: int


@dataclass
class PathResult:
    """A path between two files."""
    start: str
    end: str
    path: List[str]  # List of file_ids forming the path
    length: int
    found: bool


# ─── Link Graph Builder ───────────────────────────────────────────

class LinkGraph:
    """
    In-memory representation of the vault's link graph.
    Built once, queried many times.
    """

    def __init__(self):
        self.nodes: Dict[str, Dict] = {}  # file_id -> metadata
        self.outgoing: Dict[str, List[str]] = {}  # file_id -> [linked_ids]
        self.incoming: Dict[str, List[str]] = {}  # file_id -> [backlink_ids]
        self.edges: List[LinkEdge] = []
        self._built = False

    def build(self, vault_path: str) -> None:
        """Build the link graph from vault files."""
        self.nodes.clear()
        self.outgoing.clear()
        self.incoming.clear()
        self.edges.clear()

        vault_path = os.path.expanduser(vault_path)

        # First pass: collect all nodes
        for md_file in Path(vault_path).rglob("*.md"):
            if ".private" in str(md_file):
                continue
            try:
                meta, body = read_vault_file(str(md_file))
                file_id = meta.get("id", md_file.stem)
                self.nodes[file_id] = {
                    "path": str(md_file),
                    "filename": md_file.stem,
                    "layer": meta.get("layer", "cross"),
                    "type": meta.get("type", "unknown"),
                    "project": meta.get("project"),
                    "tags": meta.get("tags", []),
                }
                self.outgoing[file_id] = []
                self.incoming[file_id] = []
            except Exception:
                continue

        # Second pass: collect edges
        for file_id, node_data in self.nodes.items():
            path = node_data["path"]
            try:
                _, body = read_vault_file(path)
                links = extract_links(body)

                for link_target in links:
                    # Resolve link to file_id
                    resolved_id = self._resolve_link(link_target)

                    edge = LinkEdge(
                        source_id=file_id,
                        target_id=link_target,
                        source_path=path,
                        resolved=resolved_id is not None,
                        context=self._get_link_context(body, link_target),
                    )
                    self.edges.append(edge)

                    self.outgoing[file_id].append(link_target)

                    if resolved_id:
                        if file_id not in self.incoming.get(resolved_id, []):
                            self.incoming.setdefault(resolved_id, []).append(file_id)

            except Exception:
                continue

        self._built = True

    def _resolve_link(self, link_target: str) -> Optional[str]:
        """Resolve a link target to a file_id in the graph."""
        # Direct match
        if link_target in self.nodes:
            return link_target

        # Case-insensitive match
        link_lower = link_target.lower()
        for file_id in self.nodes:
            if file_id.lower() == link_lower:
                return file_id

        return None

    def _get_link_context(self, body: str, link_target: str, chars: int = 60) -> str:
        """Get text context around a link."""
        pattern = rf'\[\[{re.escape(link_target)}(?:\|[^\]]+)?\]\]'
        match = re.search(pattern, body)
        if match:
            start = max(0, match.start() - chars)
            end = min(len(body), match.end() + chars)
            context = body[start:end].replace("\n", " ").strip()
            return context
        return ""

    @property
    def is_built(self) -> bool:
        return self._built

    def get_stats(self) -> Dict:
        """Get graph statistics."""
        if not self._built:
            return {}
        resolved_edges = sum(1 for e in self.edges if e.resolved)
        broken_edges = sum(1 for e in self.edges if not e.resolved)
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "resolved_edges": resolved_edges,
            "broken_edges": broken_edges,
            "avg_outgoing": len(self.edges) / max(1, len(self.nodes)),
        }


# ─── Link Navigator ───────────────────────────────────────────────

class LinkNavigator:
    """
    Navigate the vault's link graph.

    Provides forward links, backlinks, multi-hop traversal,
    neighborhood exploration, and path finding.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.graph = LinkGraph()

    def ensure_graph(self) -> None:
        """Build graph if not already built."""
        if not self.graph.is_built:
            self.graph.build(self.vault_path)

    def get_outgoing(self, file_id: str) -> List[LinkEdge]:
        """Get all outgoing links from a file."""
        self.ensure_graph()
        return [e for e in self.graph.edges if e.source_id == file_id]

    def get_backlinks(self, file_id: str) -> List[LinkNode]:
        """Get all files that link to this file."""
        self.ensure_graph()
        backlink_ids = self.graph.incoming.get(file_id, [])
        nodes = []
        for bid in backlink_ids:
            if bid in self.graph.nodes:
                nd = self.graph.nodes[bid]
                nodes.append(LinkNode(
                    file_id=bid,
                    path=nd["path"],
                    layer=nd["layer"],
                    file_type=nd["type"],
                    project=nd.get("project"),
                    depth=1,
                    via=file_id,
                ))
        return nodes

    def get_neighborhood(
        self,
        file_id: str,
        depth: int = 2,
        direction: str = "both",  # "outgoing", "incoming", "both"
    ) -> TraversalResult:
        """
        Get the neighborhood of a file (all files within N hops).

        Args:
            file_id: Starting file
            depth: How many hops to traverse
            direction: Which direction to follow links

        Returns:
            TraversalResult with all nodes and edges in the neighborhood
        """
        self.ensure_graph()

        visited: Set[str] = set()
        nodes: List[LinkNode] = []
        edges: List[LinkEdge] = []
        queue: deque = deque([(file_id, 0, None)])  # (id, depth, via)

        while queue:
            current_id, current_depth, via = queue.popleft()

            if current_id in visited:
                continue
            if current_depth > depth:
                continue

            visited.add(current_id)

            # Add node
            if current_id in self.graph.nodes:
                nd = self.graph.nodes[current_id]
                nodes.append(LinkNode(
                    file_id=current_id,
                    path=nd["path"],
                    layer=nd["layer"],
                    file_type=nd["type"],
                    project=nd.get("project"),
                    depth=current_depth,
                    via=via,
                ))

            if current_depth < depth:
                # Follow outgoing links
                if direction in ("outgoing", "both"):
                    for edge in self.graph.edges:
                        if edge.source_id == current_id:
                            edges.append(edge)
                            target_id = self.graph._resolve_link(edge.target_id)
                            if target_id and target_id not in visited:
                                queue.append((target_id, current_depth + 1, current_id))

                # Follow incoming links (backlinks)
                if direction in ("incoming", "both"):
                    for backlink_id in self.graph.incoming.get(current_id, []):
                        if backlink_id not in visited:
                            # Find the edge
                            for edge in self.graph.edges:
                                if edge.source_id == backlink_id and self.graph._resolve_link(edge.target_id) == current_id:
                                    edges.append(edge)
                                    break
                            queue.append((backlink_id, current_depth + 1, current_id))

        return TraversalResult(
            start_node=file_id,
            nodes=nodes,
            edges=edges,
            depth_reached=depth,
            total_files_visited=len(visited),
        )

    def find_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> PathResult:
        """
        Find shortest path between two files via links.

        Uses BFS to find the shortest link path.
        """
        self.ensure_graph()

        if start_id == end_id:
            return PathResult(start_id, end_id, [start_id], 0, True)

        # BFS
        visited: Set[str] = set()
        queue: deque = deque([(start_id, [start_id])])

        while queue:
            current_id, path = queue.popleft()

            if current_id in visited:
                continue
            if len(path) > max_depth + 1:
                continue

            visited.add(current_id)

            # Check outgoing links
            for edge in self.graph.edges:
                if edge.source_id == current_id and edge.resolved:
                    target_id = self.graph._resolve_link(edge.target_id)
                    if target_id == end_id:
                        return PathResult(start_id, end_id, path + [end_id], len(path), True)
                    if target_id and target_id not in visited:
                        queue.append((target_id, path + [target_id]))

        return PathResult(start_id, end_id, [], 0, False)

    def get_reasoning_chain(
        self,
        file_id: str,
        direction: str = "up",  # "up" = L4->L1, "down" = L1->L4
    ) -> List[LinkNode]:
        """
        Get a reasoning chain following links across layers.

        direction="up": Follow Derived From links (L4->L3->L2->L1)
        direction="down": Follow Supports links (L1->L2->L3->L4)
        """
        self.ensure_graph()

        if file_id not in self.graph.nodes:
            return []

        start_layer = self.graph.nodes[file_id]["layer"]
        chain = [LinkNode(
            file_id=file_id,
            path=self.graph.nodes[file_id]["path"],
            layer=start_layer,
            file_type=self.graph.nodes[file_id]["type"],
            project=self.graph.nodes[file_id].get("project"),
            depth=0,
            via=None,
        )]

        visited = {file_id}
        current = file_id

        for _ in range(10):  # Max 10 hops
            if direction == "up":
                # Follow backlinks (what references this)
                next_ids = self.graph.incoming.get(current, [])
            else:
                # Follow outgoing links (what this references)
                next_ids = [
                    self.graph._resolve_link(e.target_id)
                    for e in self.graph.edges
                    if e.source_id == current and e.resolved
                ]
                next_ids = [n for n in next_ids if n]

            # Find next file in chain
            found = False
            for next_id in next_ids:
                if next_id in visited:
                    continue
                if next_id in self.graph.nodes:
                    next_layer = self.graph.nodes[next_id]["layer"]
                    # Only follow if it's a different layer
                    if next_layer != self.graph.nodes[current]["layer"]:
                        visited.add(next_id)
                        chain.append(LinkNode(
                            file_id=next_id,
                            path=self.graph.nodes[next_id]["path"],
                            layer=next_layer,
                            file_type=self.graph.nodes[next_id]["type"],
                            project=self.graph.nodes[next_id].get("project"),
                            depth=len(chain),
                            via=current,
                        ))
                        current = next_id
                        found = True
                        break

            if not found:
                break

        return chain

    def get_layer_connections(self, project: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Get all cross-layer connections.

        Returns dict mapping "L1->L2", "L2->L3", etc. to list of file pairs.
        """
        self.ensure_graph()

        connections = {}
        layer_order = ["L1", "L2", "L3", "L4"]

        for edge in self.graph.edges:
            if not edge.resolved:
                continue

            source_layer = self.graph.nodes.get(edge.source_id, {}).get("layer")
            target_id = self.graph._resolve_link(edge.target_id)
            target_layer = self.graph.nodes.get(target_id, {}).get("layer") if target_id else None

            if not source_layer or not target_layer:
                continue
            if source_layer == target_layer:
                continue

            # Check project filter
            if project:
                source_proj = self.graph.nodes.get(edge.source_id, {}).get("project")
                target_proj = self.graph.nodes.get(target_id, {}).get("project") if target_id else None
                if source_proj != project and target_proj != project:
                    continue

            key = f"{source_layer}->{target_layer}"
            connections.setdefault(key, []).append(
                f"{edge.source_id} -> {edge.target_id}"
            )

        return connections

    def get_stats(self) -> Dict:
        """Get navigation statistics."""
        self.ensure_graph()
        return self.graph.get_stats()


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    nav = LinkNavigator(vault)

    if cmd == "links":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: link_navigator.py links <file_id>")
            sys.exit(1)
        outgoing = nav.get_outgoing(file_id)
        print(f"Outgoing links from [[{file_id}]]: {len(outgoing)}")
        for e in outgoing:
            status = "OK" if e.resolved else "BROKEN"
            print(f"  [{status}] [[{e.target_id}]]")

    elif cmd == "backlinks":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: link_navigator.py backlinks <file_id>")
            sys.exit(1)
        backs = nav.get_backlinks(file_id)
        print(f"Backlinks to [[{file_id}]]: {len(backs)}")
        for b in backs:
            print(f"  [{b.layer}] {b.file_id}")

    elif cmd == "neighborhood":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        if not file_id:
            print("Usage: link_navigator.py neighborhood <file_id> [depth]")
            sys.exit(1)
        result = nav.get_neighborhood(file_id, depth=depth)
        print(f"Neighborhood of [[{file_id}]] (depth {depth}):")
        print(f"  Nodes: {len(result.nodes)}, Edges: {len(result.edges)}")
        for n in result.nodes:
            indent = "  " * n.depth
            print(f"  {indent}[{n.layer}] {n.file_id} (depth {n.depth})")

    elif cmd == "path":
        start = sys.argv[2] if len(sys.argv) > 2 else None
        end = sys.argv[3] if len(sys.argv) > 3 else None
        if not start or not end:
            print("Usage: link_navigator.py path <start_id> <end_id>")
            sys.exit(1)
        result = nav.find_path(start, end)
        if result.found:
            print(f"Path found ({result.length} hops):")
            print("  " + " -> ".join(result.path))
        else:
            print(f"No path found from [[{start}]] to [[{end}]]")

    elif cmd == "chain":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        direction = sys.argv[3] if len(sys.argv) > 3 else "up"
        if not file_id:
            print("Usage: link_navigator.py chain <file_id> [up|down]")
            sys.exit(1)
        chain = nav.get_reasoning_chain(file_id, direction=direction)
        print(f"Reasoning chain from [[{file_id}]] ({direction}):")
        for node in chain:
            print(f"  [{node.layer}] {node.file_id}")

    elif cmd == "connections":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        conns = nav.get_layer_connections(project=project)
        print(f"Cross-layer connections{f' for {project}' if project else ''}:")
        for layer_pair, links in sorted(conns.items()):
            print(f"  {layer_pair}: {len(links)} connections")
            for link in links[:3]:
                print(f"    {link}")

    elif cmd == "stats":
        stats = nav.get_stats()
        print(f"Link Graph Statistics:")
        print(f"  Nodes: {stats.get('nodes', 0)}")
        print(f"  Edges: {stats.get('edges', 0)}")
        print(f"  Resolved: {stats.get('resolved_edges', 0)}")
        print(f"  Broken: {stats.get('broken_edges', 0)}")
        print(f"  Avg outgoing: {stats.get('avg_outgoing', 0):.1f}")

    else:
        print("Commands: links <id>, backlinks <id>, neighborhood <id> [depth],")
        print("          path <start> <end>, chain <id> [up|down],")
        print("          connections [project], stats")

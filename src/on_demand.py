#!/usr/bin/env python3
"""
On-Demand Retriever for Mnemosyne Knowledge Vault.

Provides lazy loading of vault files during agent operation:
  - Load specific files by ID on demand
  - Load files by link reference
  - Load deeper context when needed (e.g., drill into L4)
  - Manage a retrieval cache to avoid re-loading
  - Track retrieval patterns for optimization

Usage:
    from on_demand import OnDemandRetriever

    retriever = OnDemandRetriever(vault_path="~/.hermes/memory")
    
    # Load a specific file
    file = retriever.get("gold_oxidation")
    
    # Load all files linked from current context
    deeper = retriever.follow_links_from("gold_electrodes")
    
    # Get summary without loading full content
    summary = retriever.peek("gold_oxidation")
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from vault_utils import (
    read_vault_file, extract_links, resolve_link,
    scan_vault, find_by_layer, find_by_project
)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class RetrievedFile:
    """A file retrieved on demand."""
    file_id: str
    path: str
    filename: str
    layer: str
    file_type: str
    project: Optional[str]
    frontmatter: Dict
    body: str
    links: List[str]  # Outgoing [[links]]
    token_estimate: int
    retrieved_at: datetime
    retrieval_reason: str  # "direct", "linked", "layer_drill", "search"


@dataclass
class FileSummary:
    """Lightweight file summary (no full content)."""
    file_id: str
    path: str
    layer: str
    file_type: str
    project: Optional[str]
    title: str
    summary_text: str
    link_count: int
    backlink_count: int
    confidence: str
    status: str
    updated: str


@dataclass
class RetrievalStats:
    """Statistics about retrieval patterns."""
    total_retrievals: int
    unique_files: int
    cache_hits: int
    cache_misses: int
    most_retrieved: List[Tuple[str, int]]
    retrieval_reasons: Dict[str, int]


# ─── On-Demand Retriever ──────────────────────────────────────────

class OnDemandRetriever:
    """
    Lazy-loading retriever for vault files.

    Features:
    - Cache to avoid re-reading files
    - Peek (summary only) vs full load
    - Follow links on demand
    - Layer-aware drill-down
    - Retrieval tracking
    """

    def __init__(self, vault_path: str = "~/.hermes/memory", cache_size: int = 50):
        self.vault_path = os.path.expanduser(vault_path)
        self.cache_size = cache_size
        self._cache: Dict[str, RetrievedFile] = {}
        self._summary_cache: Dict[str, FileSummary] = {}
        self._retrieval_count: Dict[str, int] = {}
        self._retrieval_reasons: Dict[str, int] = {}
        self._total_retrievals = 0

    # ─── Core Retrieval ───────────────────────────────────────────

    def get(
        self,
        file_id: str,
        reason: str = "direct",
    ) -> Optional[RetrievedFile]:
        """
        Retrieve a file by ID. Uses cache if available.

        Args:
            file_id: File ID or filename (without .md)
            reason: Why this file is being retrieved

        Returns:
            RetrievedFile or None if not found
        """
        self._total_retrievals += 1
        self._retrieval_reasons[reason] = self._retrieval_reasons.get(reason, 0) + 1

        # Check cache
        if file_id in self._cache:
            self._retrieval_count[file_id] = self._retrieval_count.get(file_id, 0) + 1
            return self._cache[file_id]

        # Resolve and load
        path = self._resolve(file_id)
        if not path:
            return None

        try:
            meta, body = read_vault_file(path)
        except Exception:
            return None

        links = extract_links(body)
        token_est = len(body) // 4

        retrieved = RetrievedFile(
            file_id=meta.get("id", Path(path).stem),
            path=path,
            filename=Path(path).stem,
            layer=meta.get("layer", "cross"),
            file_type=meta.get("type", "unknown"),
            project=meta.get("project"),
            frontmatter=meta,
            body=body,
            links=links,
            token_estimate=token_est,
            retrieved_at=datetime.now(),
            retrieval_reason=reason,
        )

        # Cache it
        self._add_to_cache(file_id, retrieved)
        self._retrieval_count[file_id] = self._retrieval_count.get(file_id, 0) + 1

        return retrieved

    def peek(self, file_id: str) -> Optional[FileSummary]:
        """
        Get a lightweight summary without loading full content.
        Much cheaper than get() for browsing.
        """
        if file_id in self._summary_cache:
            return self._summary_cache[file_id]

        path = self._resolve(file_id)
        if not path:
            return None

        try:
            meta, body = read_vault_file(path)
        except Exception:
            return None

        # Extract summary section
        summary_text = ""
        match = re.search(r'## Summary\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if match:
            summary_text = match.group(1).strip()[:300]

        # Count links
        links = extract_links(body)

        summary = FileSummary(
            file_id=meta.get("id", Path(path).stem),
            path=path,
            layer=meta.get("layer", "cross"),
            file_type=meta.get("type", "unknown"),
            project=meta.get("project"),
            title=meta.get("id", Path(path).stem),
            summary_text=summary_text,
            link_count=len(links),
            backlink_count=0,  # Computed lazily
            confidence=meta.get("confidence", "moderate"),
            status=meta.get("status", "active"),
            updated=meta.get("updated", ""),
        )

        self._summary_cache[file_id] = summary
        return summary

    # ─── Batch Retrieval ──────────────────────────────────────────

    def get_batch(
        self,
        file_ids: List[str],
        reason: str = "batch",
    ) -> List[RetrievedFile]:
        """Retrieve multiple files at once."""
        results = []
        for fid in file_ids:
            f = self.get(fid, reason=reason)
            if f:
                results.append(f)
        return results

    def get_by_layer(
        self,
        layer: str,
        project: Optional[str] = None,
        reason: str = "layer",
    ) -> List[RetrievedFile]:
        """Retrieve all files at a specific layer."""
        files = find_by_layer(layer, self.vault_path, project)
        results = []
        for meta in files:
            fid = meta.get("id", meta.get("_filename", ""))
            if fid:
                f = self.get(fid, reason=reason)
                if f:
                    results.append(f)
        return results

    def peek_batch(self, file_ids: List[str]) -> List[FileSummary]:
        """Get summaries for multiple files."""
        return [s for fid in file_ids if (s := self.peek(fid)) is not None]

    # ─── Link Following ───────────────────────────────────────────

    def follow_links_from(
        self,
        file_id: str,
        depth: int = 1,
        reason: str = "linked",
    ) -> List[RetrievedFile]:
        """
        Load all files linked from a given file.

        Args:
            file_id: Source file
            depth: How many levels of links to follow (1 = direct links only)
            reason: Retrieval reason tag

        Returns:
            List of retrieved files
        """
        source = self.get(file_id, reason="source")
        if not source:
            return []

        results = []
        visited = {file_id}

        current_level = [file_id]
        for level in range(depth):
            next_level = []
            for fid in current_level:
                file = self._cache.get(fid)
                if not file:
                    continue

                for link_target in file.links:
                    # Resolve to actual file_id
                    resolved = self._resolve_id(link_target)
                    if resolved and resolved not in visited:
                        visited.add(resolved)
                        retrieved = self.get(resolved, reason=reason)
                        if retrieved:
                            results.append(retrieved)
                            next_level.append(resolved)

            current_level = next_level
            if not current_level:
                break

        return results

    def follow_backlinks(
        self,
        file_id: str,
        reason: str = "backlink",
    ) -> List[RetrievedFile]:
        """
        Load all files that link to this file.

        Note: Requires scanning all files. Use sparingly.
        """
        pattern = re.compile(
            rf'\[\[{re.escape(file_id)}(?:\|[^\]]+)?\]\]'
        )
        results = []

        for md_file in Path(self.vault_path).rglob("*.md"):
            if ".private" in str(md_file):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                if pattern.search(content):
                    meta, _ = read_vault_file(str(md_file))
                    fid = meta.get("id", md_file.stem)
                    if fid != file_id:
                        retrieved = self.get(fid, reason=reason)
                        if retrieved:
                            results.append(retrieved)
            except Exception:
                continue

        return results

    # ─── Layer Drill-Down ─────────────────────────────────────────

    def drill_deeper(
        self,
        file_id: str,
        reason: str = "drill_down",
    ) -> List[RetrievedFile]:
        """
        From a file, find and load files in deeper layers it links to.

        E.g., from L2 component, find L3 rules and L4 research it references.
        """
        source = self.get(file_id, reason="source")
        if not source:
            return []

        layer_order = ["L1", "L2", "L3", "L4"]
        current_idx = layer_order.index(source.layer) if source.layer in layer_order else -1

        if current_idx < 0 or current_idx >= 3:
            return []  # Already at deepest layer

        # Find linked files in deeper layers
        deeper = []
        for link_target in source.links:
            resolved_id = self._resolve_id(link_target)
            if not resolved_id:
                continue

            # Peek to check layer without full load
            summary = self.peek(resolved_id)
            if not summary:
                continue

            target_idx = layer_order.index(summary.layer) if summary.layer in layer_order else -1
            if target_idx > current_idx:
                retrieved = self.get(resolved_id, reason=reason)
                if retrieved:
                    deeper.append(retrieved)

        return deeper

    def get_layer_context(
        self,
        file_id: str,
        reason: str = "layer_context",
    ) -> Dict[str, List[RetrievedFile]]:
        """
        Get a file plus its context in adjacent layers.

        Returns dict with keys: "above", "same", "below"
        """
        source = self.get(file_id, reason="source")
        if not source:
            return {"above": [], "same": [], "below": []}

        layer_order = ["L1", "L2", "L3", "L4"]
        current_idx = layer_order.index(source.layer) if source.layer in layer_order else -1

        above = []
        same = []
        below = []

        for link_target in source.links:
            resolved_id = self._resolve_id(link_target)
            if not resolved_id:
                continue

            summary = self.peek(resolved_id)
            if not summary:
                continue

            target_idx = layer_order.index(summary.layer) if summary.layer in layer_order else -1

            retrieved = self.get(resolved_id, reason=reason)
            if not retrieved:
                continue

            if target_idx < current_idx:
                above.append(retrieved)
            elif target_idx == current_idx:
                same.append(retrieved)
            elif target_idx > current_idx:
                below.append(retrieved)

        return {"above": above, "same": same, "below": below}

    # ─── Cache Management ─────────────────────────────────────────

    def _add_to_cache(self, file_id: str, file: RetrievedFile) -> None:
        """Add file to cache, evicting oldest if needed."""
        if len(self._cache) >= self.cache_size:
            # Evict least recently retrieved
            oldest = min(self._cache.keys(), key=lambda k: self._retrieval_count.get(k, 0))
            del self._cache[oldest]

        self._cache[file_id] = file

    def clear_cache(self) -> None:
        """Clear the retrieval cache."""
        self._cache.clear()
        self._summary_cache.clear()

    def get_cached_ids(self) -> List[str]:
        """Get list of currently cached file IDs."""
        return list(self._cache.keys())

    # ─── Resolution ───────────────────────────────────────────────

    def _resolve(self, file_id: str) -> Optional[str]:
        """Resolve a file ID to its path."""
        # Direct path
        if os.path.exists(file_id):
            return file_id

        # Search by filename
        for md_file in Path(self.vault_path).rglob("*.md"):
            if md_file.stem == file_id:
                return str(md_file)

        # Search by frontmatter id
        for md_file in Path(self.vault_path).rglob("*.md"):
            if ".private" in str(md_file):
                continue
            try:
                meta, _ = read_vault_file(str(md_file))
                if meta.get("id") == file_id:
                    return str(md_file)
            except Exception:
                continue

        return None

    def _resolve_id(self, link_target: str) -> Optional[str]:
        """Resolve a [[link]] target to a file ID."""
        path = self._resolve(link_target)
        if path:
            try:
                meta, _ = read_vault_file(path)
                return meta.get("id", Path(path).stem)
            except Exception:
                return Path(path).stem
        return None

    # ─── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> RetrievalStats:
        """Get retrieval statistics."""
        reason_counts = dict(self._retrieval_reasons)

        # Most retrieved
        sorted_counts = sorted(
            self._retrieval_count.items(),
            key=lambda x: x[1],
            reverse=True
        )

        cache_hits = sum(
            1 for fid, count in self._retrieval_count.items()
            if count > 1
        )

        return RetrievalStats(
            total_retrievals=self._total_retrievals,
            unique_files=len(self._retrieval_count),
            cache_hits=cache_hits,
            cache_misses=self._total_retrievals - cache_hits,
            most_retrieved=sorted_counts[:10],
            retrieval_reasons=reason_counts,
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    retriever = OnDemandRetriever(vault)

    if cmd == "get":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: on_demand.py get <file_id>")
            sys.exit(1)
        f = retriever.get(file_id)
        if f:
            print(f"[{f.layer}/{f.file_type}] {f.file_id}")
            print(f"Path: {f.path}")
            print(f"Links: {', '.join(f.links[:10])}")
            print(f"Tokens: ~{f.token_estimate}")
            print()
            print(f.body[:500])
        else:
            print(f"File '{file_id}' not found")

    elif cmd == "peek":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: on_demand.py peek <file_id>")
            sys.exit(1)
        s = retriever.peek(file_id)
        if s:
            print(f"[{s.layer}/{s.file_type}] {s.file_id}")
            print(f"Status: {s.status}, Confidence: {s.confidence}")
            print(f"Links: {s.link_count}, Updated: {s.updated}")
            print(f"Summary: {s.summary_text[:200]}")
        else:
            print(f"File '{file_id}' not found")

    elif cmd == "follow":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        if not file_id:
            print("Usage: on_demand.py follow <file_id> [depth]")
            sys.exit(1)
        results = retriever.follow_links_from(file_id, depth=depth)
        print(f"Followed links from [[{file_id}]] (depth {depth}): {len(results)} files")
        for f in results:
            print(f"  [{f.layer}] {f.file_id} (via {f.retrieval_reason})")

    elif cmd == "drill":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: on_demand.py drill <file_id>")
            sys.exit(1)
        results = retriever.drill_deeper(file_id)
        print(f"Deeper files from [[{file_id}]]: {len(results)}")
        for f in results:
            print(f"  [{f.layer}] {f.file_id}")

    elif cmd == "stats":
        stats = retriever.get_stats()
        print(f"Retrieval Statistics:")
        print(f"  Total retrievals: {stats.total_retrievals}")
        print(f"  Unique files: {stats.unique_files}")
        print(f"  Cache hits: {stats.cache_hits}")
        print(f"  Reasons: {stats.retrieval_reasons}")
        if stats.most_retrieved:
            print(f"  Most retrieved:")
            for fid, count in stats.most_retrieved[:5]:
                print(f"    {fid}: {count}x")

    else:
        print("Commands: get <id>, peek <id>, follow <id> [depth], drill <id>, stats")

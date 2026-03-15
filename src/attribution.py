#!/usr/bin/env python3
"""
Chunk Attribution Tracker for Mnemosyne Knowledge Vault.

Tracks which vault files/chunks contributed to each agent response:
  - Records file IDs loaded into context for a response
  - Tracks which files were actually cited/referenced in the response
  - Builds attribution chains (response -> source files)
  - Enables "show your sources" transparency

Usage:
    from attribution import AttributionTracker

    tracker = AttributionTracker(vault_path="~/.hermes/memory")
    
    # Start tracking for a response
    session = tracker.begin_response(context_files=["gold_oxidation", "impedance_spec"])
    
    # Record a citation during response generation
    tracker.cite("gold_oxidation", "Gold resists oxidation at skin pH levels")
    
    # Finalize the response
    entry = tracker.end_response(response_text="Based on research, gold electrodes...")
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class Citation:
    """A single citation from a vault file."""
    file_id: str
    excerpt: str  # The text/finding cited
    timestamp: str = ""


@dataclass
class AttributionEntry:
    """Complete attribution record for a response."""
    id: str
    response_hash: str
    timestamp: str
    project: Optional[str]
    context_files: List[str]  # All files loaded into context
    cited_files: List[str]    # Files actually cited in response
    citations: List[Citation]
    response_preview: str     # First 200 chars of response
    token_count: int = 0

    def citation_rate(self) -> float:
        """Percentage of context files that were actually cited."""
        if not self.context_files:
            return 0.0
        return len(self.cited_files) / len(self.context_files)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "response_hash": self.response_hash,
            "timestamp": self.timestamp,
            "project": self.project,
            "context_files": self.context_files,
            "cited_files": self.cited_files,
            "citations": [{"file_id": c.file_id, "excerpt": c.excerpt} for c in self.citations],
            "response_preview": self.response_preview,
            "token_count": self.token_count,
            "citation_rate": self.citation_rate(),
        }


@dataclass
class AttributionStats:
    """Aggregated attribution statistics."""
    total_responses: int
    total_citations: int
    avg_citations_per_response: float
    avg_context_files: float
    avg_citation_rate: float
    most_cited_files: List[Dict]  # [{file_id, count}]
    citation_frequency: Dict[str, int]  # file_id -> citation count


@dataclass
class _TrackingSession:
    """Internal tracking session."""
    session_id: str
    context_files: List[str]
    citations: List[Citation]
    start_time: datetime
    project: Optional[str] = None


# ─── Attribution Tracker ──────────────────────────────────────────

class AttributionTracker:
    """
    Tracks which vault files contributed to agent responses.

    Enables:
    - Source transparency ("show your sources")
    - Citation quality analysis
    - File usage patterns
    - Response provenance
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.attribution_dir = Path(self.vault_path) / "attribution"
        self._session: Optional[_TrackingSession] = None
        self._counter = 0

    def begin_response(
        self,
        context_files: List[str],
        project: Optional[str] = None,
    ) -> str:
        """
        Start tracking a new response.

        Args:
            context_files: List of file IDs loaded into context
            project: Current project

        Returns:
            Session ID for this tracking session
        """
        self._counter += 1
        session_id = f"attr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._counter}"

        self._session = _TrackingSession(
            session_id=session_id,
            context_files=context_files,
            citations=[],
            start_time=datetime.now(),
            project=project,
        )

        return session_id

    def cite(
        self,
        file_id: str,
        excerpt: str = "",
    ) -> None:
        """
        Record a citation from a vault file.

        Call this when the agent references specific content from a vault file.

        Args:
            file_id: ID of the file being cited
            excerpt: The specific text/finding being referenced
        """
        if not self._session:
            return

        citation = Citation(
            file_id=file_id,
            excerpt=excerpt[:500],  # Cap excerpt length
            timestamp=datetime.now().isoformat(),
        )
        self._session.citations.append(citation)

    def end_response(
        self,
        response_text: str,
        token_count: int = 0,
    ) -> Optional[AttributionEntry]:
        """
        Finalize tracking for a response.

        Args:
            response_text: The full response text
            token_count: Approximate token count of response

        Returns:
            AttributionEntry that was recorded
        """
        if not self._session:
            return None

        # Determine which files were actually cited
        cited_files = list(set(c.file_id for c in self._session.citations))

        # Auto-detect citations from response text
        auto_cited = self._detect_citations(response_text)
        for file_id in auto_cited:
            if file_id not in cited_files:
                cited_files.append(file_id)
                self._session.citations.append(Citation(
                    file_id=file_id,
                    excerpt="(auto-detected)",
                    timestamp=datetime.now().isoformat(),
                ))

        # Build entry
        entry = AttributionEntry(
            id=self._session.session_id,
            response_hash=hashlib.md5(response_text.encode()).hexdigest()[:12],
            timestamp=self._session.start_time.isoformat(),
            project=self._session.project,
            context_files=self._session.context_files,
            cited_files=cited_files,
            citations=self._session.citations,
            response_preview=response_text[:200],
            token_count=token_count,
        )

        # Persist
        self._write_attribution(entry)

        # Clear session
        self._session = None

        return entry

    def get_attribution(self, attribution_id: str) -> Optional[AttributionEntry]:
        """Retrieve a specific attribution entry."""
        attr_file = self.attribution_dir / f"{attribution_id}.json"
        if not attr_file.exists():
            return None

        try:
            data = json.loads(attr_file.read_text(encoding="utf-8"))
            return self._dict_to_entry(data)
        except Exception:
            return None

    def get_recent(
        self,
        project: Optional[str] = None,
        limit: int = 20,
    ) -> List[AttributionEntry]:
        """Get recent attribution entries."""
        entries = []

        if not self.attribution_dir.exists():
            return entries

        for json_file in sorted(self.attribution_dir.glob("*.json"), reverse=True):
            if len(entries) >= limit:
                break
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if project and data.get("project") != project:
                    continue
                entries.append(self._dict_to_entry(data))
            except Exception:
                continue

        return entries

    def get_file_usage(
        self,
        file_id: str,
        project: Optional[str] = None,
    ) -> Dict:
        """
        Get usage statistics for a specific file.

        Returns how many times it was loaded into context vs. actually cited.
        """
        all_entries = self.get_recent(project=project, limit=1000)

        context_count = 0
        cited_count = 0
        citations = []

        for entry in all_entries:
            if file_id in entry.context_files:
                context_count += 1
            if file_id in entry.cited_files:
                cited_count += 1
                for c in entry.citations:
                    if c.file_id == file_id:
                        citations.append(c.excerpt)

        return {
            "file_id": file_id,
            "context_count": context_count,
            "cited_count": cited_count,
            "citation_rate": cited_count / max(1, context_count),
            "sample_citations": citations[:5],
        }

    def get_stats(
        self,
        project: Optional[str] = None,
    ) -> AttributionStats:
        """Get aggregated attribution statistics."""
        entries = self.get_recent(project=project, limit=1000)

        if not entries:
            return AttributionStats(
                total_responses=0,
                total_citations=0,
                avg_citations_per_response=0,
                avg_context_files=0,
                avg_citation_rate=0,
                most_cited_files=[],
                citation_frequency={},
            )

        total_citations = sum(len(e.citations) for e in entries)
        total_context = sum(len(e.context_files) for e in entries)

        # Count citation frequency
        freq: Dict[str, int] = {}
        for entry in entries:
            for file_id in entry.cited_files:
                freq[file_id] = freq.get(file_id, 0) + 1

        # Sort by frequency
        most_cited = [
            {"file_id": fid, "count": count}
            for fid, count in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        avg_rate = sum(e.citation_rate() for e in entries) / len(entries)

        return AttributionStats(
            total_responses=len(entries),
            total_citations=total_citations,
            avg_citations_per_response=total_citations / len(entries),
            avg_context_files=total_context / len(entries),
            avg_citation_rate=avg_rate,
            most_cited_files=most_cited,
            citation_frequency=freq,
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _detect_citations(self, response_text: str) -> List[str]:
        """Auto-detect [[file_id]] references in response text."""
        import re
        pattern = r'\[\[(\w+)(?:\|[^\]]+)?\]\]'
        matches = re.findall(pattern, response_text)
        return list(set(matches))

    def _write_attribution(self, entry: AttributionEntry) -> None:
        """Write attribution entry to disk."""
        self.attribution_dir.mkdir(parents=True, exist_ok=True)

        attr_file = self.attribution_dir / f"{entry.id}.json"
        attr_file.write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _dict_to_entry(self, data: Dict) -> AttributionEntry:
        """Convert dict to AttributionEntry."""
        citations = [
            Citation(
                file_id=c.get("file_id", ""),
                excerpt=c.get("excerpt", ""),
            )
            for c in data.get("citations", [])
        ]

        return AttributionEntry(
            id=data.get("id", ""),
            response_hash=data.get("response_hash", ""),
            timestamp=data.get("timestamp", ""),
            project=data.get("project"),
            context_files=data.get("context_files", []),
            cited_files=data.get("cited_files", []),
            citations=citations,
            response_preview=data.get("response_preview", ""),
            token_count=data.get("token_count", 0),
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    tracker = AttributionTracker(vault)

    if cmd == "recent":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        entries = tracker.get_recent(project=project)
        print(f"Recent attributions: {len(entries)}")
        for e in entries[:10]:
            print(f"  {e.id}: {len(e.cited_files)} cited / {len(e.context_files)} context "
                  f"({e.citation_rate():.0%})")

    elif cmd == "file":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: attribution.py file <file_id>")
            sys.exit(1)
        usage = tracker.get_file_usage(file_id)
        print(f"Usage for [[{file_id}]]:")
        print(f"  Loaded into context: {usage['context_count']}x")
        print(f"  Actually cited: {usage['cited_count']}x")
        print(f"  Citation rate: {usage['citation_rate']:.0%}")

    elif cmd == "stats":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        stats = tracker.get_stats(project=project)
        print(f"Attribution Statistics:")
        print(f"  Total responses: {stats.total_responses}")
        print(f"  Total citations: {stats.total_citations}")
        print(f"  Avg citations/response: {stats.avg_citations_per_response:.1f}")
        print(f"  Avg context files: {stats.avg_context_files:.1f}")
        print(f"  Avg citation rate: {stats.avg_citation_rate:.0%}")
        if stats.most_cited_files:
            print(f"  Most cited:")
            for f in stats.most_cited_files[:5]:
                print(f"    {f['file_id']}: {f['count']}x")

    else:
        print("Commands: recent [project], file <file_id>, stats [project]")

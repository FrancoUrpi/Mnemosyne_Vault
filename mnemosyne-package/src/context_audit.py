#!/usr/bin/env python3
"""
Context Auditor for Mnemosyne Knowledge Vault.

Logs and analyzes vault context loading decisions:
  - What files were loaded and why
  - Budget allocation breakdown
  - Relevance scores for loaded files
  - Files that were considered but excluded
  - Degradation events
  - Context quality metrics

Usage:
    from context_audit import ContextAuditor

    auditor = ContextAuditor(vault_path="~/.hermes/memory")
    
    # Log a context load
    auditor.log_load(
        project="eeg",
        topic="gold electrodes",
        loaded_files=[...],
        excluded_files=[...],
        budget_used=3200,
        budget_limit=4000,
    )
    
    # Analyze context quality
    report = auditor.get_quality_report(project="eeg")
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class LoadedFileInfo:
    """Information about a loaded file."""
    file_id: str
    layer: str
    file_type: str
    relevance_score: float
    token_estimate: int
    load_reason: str  # "always", "project", "relevant", "linked"
    included: bool = True


@dataclass
class ExcludedFileInfo:
    """Information about a file that was considered but excluded."""
    file_id: str
    layer: str
    relevance_score: float
    reason: str  # "budget", "low_relevance", "private", "archived"


@dataclass
class ContextAuditEntry:
    """A single context loading audit record."""
    id: str
    timestamp: str
    project: Optional[str]
    topic: Optional[str]
    loaded_files: List[LoadedFileInfo]
    excluded_files: List[ExcludedFileInfo]
    budget_used: int
    budget_limit: int
    budget_utilization: float
    degradation_level: str
    stage1_scanned: int
    stage2_loaded: int
    load_time_ms: float

    @property
    def avg_relevance(self) -> float:
        """Average relevance score of loaded files."""
        if not self.loaded_files:
            return 0.0
        return sum(f.relevance_score for f in self.loaded_files) / len(self.loaded_files)

    @property
    def layer_distribution(self) -> Dict[str, int]:
        """Count of loaded files by layer."""
        dist: Dict[str, int] = {}
        for f in self.loaded_files:
            dist[f.layer] = dist.get(f.layer, 0) + 1
        return dist

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "project": self.project,
            "topic": self.topic,
            "loaded_files": [
                {"file_id": f.file_id, "layer": f.layer, "score": f.relevance_score,
                 "tokens": f.token_estimate, "reason": f.load_reason}
                for f in self.loaded_files
            ],
            "excluded_files": [
                {"file_id": f.file_id, "layer": f.layer, "score": f.relevance_score,
                 "reason": f.reason}
                for f in self.excluded_files
            ],
            "budget_used": self.budget_used,
            "budget_limit": self.budget_limit,
            "budget_utilization": self.budget_utilization,
            "degradation_level": self.degradation_level,
            "stage1_scanned": self.stage1_scanned,
            "stage2_loaded": self.stage2_loaded,
            "load_time_ms": self.load_time_ms,
            "avg_relevance": self.avg_relevance,
            "layer_distribution": self.layer_distribution,
        }


@dataclass
class QualityReport:
    """Context quality analysis report."""
    project: Optional[str]
    period_start: str
    period_end: str
    total_loads: int
    avg_budget_utilization: float
    avg_files_loaded: float
    avg_relevance: float
    avg_load_time_ms: float
    degradation_events: int
    layer_balance: Dict[str, float]  # layer -> % of total
    most_loaded_files: List[Dict]
    most_excluded_files: List[Dict]
    budget_efficiency: float  # relevance per token


# ─── Context Auditor ──────────────────────────────────────────────

class ContextAuditor:
    """
    Audits vault context loading decisions.

    Records what was loaded, why, and analyzes quality metrics
    to optimize context loading over time.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.audit_dir = Path(self.vault_path) / "context_audit"
        self._counter = 0

    def log_load(
        self,
        project: Optional[str],
        topic: Optional[str],
        loaded_files: List[Dict],
        excluded_files: Optional[List[Dict]] = None,
        budget_used: int = 0,
        budget_limit: int = 4000,
        degradation_level: str = "none",
        stage1_scanned: int = 0,
        stage2_loaded: int = 0,
        load_time_ms: float = 0,
    ) -> ContextAuditEntry:
        """
        Log a context loading event.

        Args:
            project: Current project
            topic: Current topic/query
            loaded_files: List of {file_id, layer, file_type, relevance_score, token_estimate, load_reason}
            excluded_files: List of {file_id, layer, relevance_score, reason}
            budget_used: Tokens used
            budget_limit: Token budget limit
            degradation_level: Degradation level applied
            stage1_scanned: Files scanned in stage 1
            stage2_loaded: Files loaded in stage 2
            load_time_ms: Time taken to load

        Returns:
            ContextAuditEntry that was created
        """
        self._counter += 1
        entry_id = f"ctx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._counter}"

        loaded = [
            LoadedFileInfo(
                file_id=f.get("file_id", ""),
                layer=f.get("layer", "cross"),
                file_type=f.get("file_type", "unknown"),
                relevance_score=f.get("relevance_score", 0.5),
                token_estimate=f.get("token_estimate", 0),
                load_reason=f.get("load_reason", "relevant"),
            )
            for f in (loaded_files or [])
        ]

        excluded = [
            ExcludedFileInfo(
                file_id=f.get("file_id", ""),
                layer=f.get("layer", "cross"),
                relevance_score=f.get("relevance_score", 0),
                reason=f.get("reason", "unknown"),
            )
            for f in (excluded_files or [])
        ]

        entry = ContextAuditEntry(
            id=entry_id,
            timestamp=datetime.now().isoformat(),
            project=project,
            topic=topic,
            loaded_files=loaded,
            excluded_files=excluded,
            budget_used=budget_used,
            budget_limit=budget_limit,
            budget_utilization=budget_used / max(1, budget_limit),
            degradation_level=degradation_level,
            stage1_scanned=stage1_scanned,
            stage2_loaded=stage2_loaded,
            load_time_ms=load_time_ms,
        )

        self._write_entry(entry)
        return entry

    def get_entries(
        self,
        project: Optional[str] = None,
        limit: int = 50,
    ) -> List[ContextAuditEntry]:
        """Get recent audit entries."""
        entries = []

        if not self.audit_dir.exists():
            return entries

        for json_file in sorted(self.audit_dir.glob("*.json"), reverse=True):
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

    def get_quality_report(
        self,
        project: Optional[str] = None,
        days: int = 7,
    ) -> QualityReport:
        """Generate a context quality report."""
        cutoff = datetime.now() - timedelta(days=days)
        all_entries = self.get_entries(project=project, limit=1000)

        # Filter by date
        entries = []
        for e in all_entries:
            try:
                if datetime.fromisoformat(e.timestamp) >= cutoff:
                    entries.append(e)
            except Exception:
                continue

        if not entries:
            return QualityReport(
                project=project,
                period_start=cutoff.strftime("%Y-%m-%d"),
                period_end=datetime.now().strftime("%Y-%m-%d"),
                total_loads=0,
                avg_budget_utilization=0,
                avg_files_loaded=0,
                avg_relevance=0,
                avg_load_time_ms=0,
                degradation_events=0,
                layer_balance={},
                most_loaded_files=[],
                most_excluded_files=[],
                budget_efficiency=0,
            )

        # Calculate metrics
        total_budget_util = sum(e.budget_utilization for e in entries)
        total_files = sum(len(e.loaded_files) for e in entries)
        total_relevance = sum(e.avg_relevance for e in entries)
        total_time = sum(e.load_time_ms for e in entries)
        degradation_count = sum(1 for e in entries if e.degradation_level != "none")

        # Layer distribution
        layer_counts: Dict[str, int] = {}
        for e in entries:
            for f in e.loaded_files:
                layer_counts[f.layer] = layer_counts.get(f.layer, 0) + 1

        total_layer_files = sum(layer_counts.values())
        layer_balance = {
            layer: count / max(1, total_layer_files)
            for layer, count in layer_counts.items()
        }

        # File frequency
        file_load_count: Dict[str, int] = {}
        file_exclude_count: Dict[str, int] = {}
        for e in entries:
            for f in e.loaded_files:
                file_load_count[f.file_id] = file_load_count.get(f.file_id, 0) + 1
            for f in e.excluded_files:
                file_exclude_count[f.file_id] = file_exclude_count.get(f.file_id, 0) + 1

        most_loaded = [
            {"file_id": fid, "count": count}
            for fid, count in sorted(file_load_count.items(), key=lambda x: x[1], reverse=True)[:10]
        ]
        most_excluded = [
            {"file_id": fid, "count": count}
            for fid, count in sorted(file_exclude_count.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        # Budget efficiency (relevance per token)
        total_tokens = sum(e.budget_used for e in entries)
        avg_relevance_total = total_relevance / len(entries)
        budget_efficiency = avg_relevance_total / max(1, total_tokens / len(entries) / 1000)

        return QualityReport(
            project=project,
            period_start=cutoff.strftime("%Y-%m-%d"),
            period_end=datetime.now().strftime("%Y-%m-%d"),
            total_loads=len(entries),
            avg_budget_utilization=total_budget_util / len(entries),
            avg_files_loaded=total_files / len(entries),
            avg_relevance=avg_relevance_total,
            avg_load_time_ms=total_time / len(entries),
            degradation_events=degradation_count,
            layer_balance=layer_balance,
            most_loaded_files=most_loaded,
            most_excluded_files=most_excluded,
            budget_efficiency=budget_efficiency,
        )

    def get_budget_trend(
        self,
        project: Optional[str] = None,
        days: int = 7,
    ) -> List[Dict]:
        """Get budget utilization trend over time."""
        entries = self.get_entries(project=project, limit=1000)
        cutoff = datetime.now() - timedelta(days=days)

        trend = []
        for e in entries:
            try:
                if datetime.fromisoformat(e.timestamp) >= cutoff:
                    trend.append({
                        "timestamp": e.timestamp[:16],
                        "budget_used": e.budget_used,
                        "budget_limit": e.budget_limit,
                        "utilization": e.budget_utilization,
                        "files_loaded": len(e.loaded_files),
                    })
            except Exception:
                continue

        return sorted(trend, key=lambda x: x["timestamp"])

    # ─── Internal ─────────────────────────────────────────────────

    def _write_entry(self, entry: ContextAuditEntry) -> None:
        """Write audit entry to disk."""
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = self.audit_dir / f"{entry.id}.json"
        audit_file.write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _dict_to_entry(self, data: Dict) -> ContextAuditEntry:
        """Convert dict to ContextAuditEntry."""
        loaded = [
            LoadedFileInfo(
                file_id=f.get("file_id", ""),
                layer=f.get("layer", "cross"),
                file_type=f.get("file_type", "unknown"),
                relevance_score=f.get("score", 0.5),
                token_estimate=f.get("tokens", 0),
                load_reason=f.get("reason", "relevant"),
            )
            for f in data.get("loaded_files", [])
        ]

        excluded = [
            ExcludedFileInfo(
                file_id=f.get("file_id", ""),
                layer=f.get("layer", "cross"),
                relevance_score=f.get("score", 0),
                reason=f.get("reason", "unknown"),
            )
            for f in data.get("excluded_files", [])
        ]

        return ContextAuditEntry(
            id=data.get("id", ""),
            timestamp=data.get("timestamp", ""),
            project=data.get("project"),
            topic=data.get("topic"),
            loaded_files=loaded,
            excluded_files=excluded,
            budget_used=data.get("budget_used", 0),
            budget_limit=data.get("budget_limit", 4000),
            budget_utilization=data.get("budget_utilization", 0),
            degradation_level=data.get("degradation_level", "none"),
            stage1_scanned=data.get("stage1_scanned", 0),
            stage2_loaded=data.get("stage2_loaded", 0),
            load_time_ms=data.get("load_time_ms", 0),
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    auditor = ContextAuditor(vault)

    if cmd == "recent":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        entries = auditor.get_entries(project=project)
        print(f"Recent context loads: {len(entries)}")
        for e in entries[:10]:
            print(f"  {e.id}: {len(e.loaded_files)} files, "
                  f"{e.budget_used}/{e.budget_limit} tokens ({e.budget_utilization:.0%}), "
                  f"degradation={e.degradation_level}")

    elif cmd == "quality":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        report = auditor.get_quality_report(project=project, days=days)
        print(f"Context Quality Report ({report.period_start} to {report.period_end}):")
        print(f"  Total loads: {report.total_loads}")
        print(f"  Avg budget utilization: {report.avg_budget_utilization:.0%}")
        print(f"  Avg files loaded: {report.avg_files_loaded:.1f}")
        print(f"  Avg relevance: {report.avg_relevance:.2f}")
        print(f"  Avg load time: {report.avg_load_time_ms:.0f}ms")
        print(f"  Degradation events: {report.degradation_events}")
        if report.layer_balance:
            print(f"  Layer balance:")
            for layer, pct in sorted(report.layer_balance.items()):
                print(f"    {layer}: {pct:.0%}")

    elif cmd == "trend":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        trend = auditor.get_budget_trend(project=project, days=days)
        print(f"Budget trend ({len(trend)} data points):")
        for t in trend[-10:]:
            bar = "█" * int(t["utilization"] * 20)
            print(f"  {t['timestamp']} {bar:20} {t['utilization']:.0%} ({t['files_loaded']} files)")

    else:
        print("Commands: recent [project], quality [project] [days], trend [project] [days]")

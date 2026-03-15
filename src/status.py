#!/usr/bin/env python3
"""
Status Tracker for Mnemosyne Knowledge Vault.

Monitors project health metrics and progress:
  - Success criteria completion tracking
  - Health metric monitoring with thresholds
  - Progress indicators per layer
  - Activity tracking (recent changes)
  - Alert generation for threshold violations

Usage:
    from status import StatusTracker

    tracker = StatusTracker(vault_path="~/.hermes/memory")
    
    # Get project status
    status = tracker.get_status("eeg")
    
    # Check for alerts
    alerts = tracker.check_alerts("eeg")
    
    # Get progress report
    progress = tracker.get_progress("eeg")
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from vault_utils import read_vault_file, scan_vault, find_by_layer, find_by_project
from intent import IntentManager, ProjectHealth, ProjectPhase


# ─── Enums ────────────────────────────────────────────────────────

class AlertLevel(Enum):
    """Alert severity."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MetricStatus(Enum):
    """Health metric status."""
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"
    UNKNOWN = "unknown"


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class Alert:
    """A status alert."""
    id: str
    project: str
    level: AlertLevel
    metric: str
    message: str
    timestamp: str
    acknowledged: bool = False


@dataclass
class LayerProgress:
    """Progress for a single layer."""
    layer: str
    file_count: int
    last_updated: Optional[str]
    days_since_update: Optional[int]
    completeness: float  # 0.0 to 1.0 (files with content vs empty)
    activity_score: float  # Recent activity (0.0 to 1.0)


@dataclass
class ProjectStatus:
    """Complete project status."""
    project: str
    phase: str
    health: str
    last_updated: str
    days_since_update: int
    criteria_completion: float
    criteria_total: int
    criteria_completed: int
    layer_progress: Dict[str, LayerProgress]
    total_files: int
    recent_changes: int  # Files changed in last 7 days
    alerts: List[Alert]
    health_score: float  # Composite 0.0 to 1.0

    @property
    def is_healthy(self) -> bool:
        return self.health_score >= 0.6

    @property
    def needs_attention(self) -> bool:
        return len([a for a in self.alerts if a.level in (AlertLevel.WARNING, AlertLevel.CRITICAL)]) > 0


@dataclass
class ProgressReport:
    """Progress over time."""
    project: str
    period_start: str
    period_end: str
    criteria_at_start: int
    criteria_at_end: int
    criteria_added: int
    files_at_start: int
    files_at_end: int
    files_added: int
    layer_changes: Dict[str, int]  # layer -> files added
    activity_by_day: Dict[str, int]  # date -> change count


# ─── Status Tracker ───────────────────────────────────────────────

class StatusTracker:
    """
    Monitors project health and progress.

    Aggregates data from intent schemas, vault files, and activity
    to provide a complete project status picture.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.intent_mgr = IntentManager(vault_path)
        self.alerts_dir = Path(vault_path) / "alerts"

    def get_status(self, project: str) -> ProjectStatus:
        """
        Get complete project status.

        Combines intent schema data with vault analysis.
        """
        # Load intent
        intent = self.intent_mgr.load_intent(project)

        # Get project files
        project_files = find_by_project(project, self.vault_path)

        # Layer progress
        layer_progress = {}
        for layer in ["L1", "L2", "L3", "L4"]:
            layer_files = find_by_layer(layer, self.vault_path, project)
            lp = self._analyze_layer(layer, layer_files)
            layer_progress[layer] = lp

        # Recent changes (last 7 days)
        recent_changes = self._count_recent_changes(project, days=7)

        # Calculate completeness from intent
        criteria_completion = 0.0
        criteria_total = 0
        criteria_completed = 0
        if intent:
            criteria_completion = intent.criteria_completion
            criteria_total = len(intent.success_criteria)
            criteria_completed = sum(1 for c in intent.success_criteria if c.completed)

        # Generate alerts
        alerts = self._generate_alerts(project, intent, layer_progress, project_files)

        # Composite health score
        health_score = self._calculate_health_score(
            intent, layer_progress, recent_changes, criteria_completion
        )

        # Determine last update
        last_updated = ""
        days_since = 999
        for f in project_files:
            updated = str(f.get("updated", ""))[:10]
            if updated > last_updated:
                last_updated = updated

        if last_updated:
            try:
                last_date = datetime.strptime(last_updated, "%Y-%m-%d")
                days_since = (datetime.now() - last_date).days
            except (ValueError, TypeError):
                pass

        return ProjectStatus(
            project=project,
            phase=intent.phase.value if intent else "unknown",
            health=intent.health.value if intent else "unknown",
            last_updated=last_updated,
            days_since_update=days_since,
            criteria_completion=criteria_completion,
            criteria_total=criteria_total,
            criteria_completed=criteria_completed,
            layer_progress=layer_progress,
            total_files=len(project_files),
            recent_changes=recent_changes,
            alerts=alerts,
            health_score=health_score,
        )

    def check_alerts(self, project: str) -> List[Alert]:
        """Check for new alerts on a project."""
        status = self.get_status(project)
        return [a for a in status.alerts if not a.acknowledged]

    def get_progress(
        self,
        project: str,
        days: int = 30,
    ) -> ProgressReport:
        """Get progress report over a period."""
        project_files = find_by_project(project, self.vault_path)

        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        # Count files by layer
        layer_changes: Dict[str, int] = {}
        files_added = 0
        activity_by_day: Dict[str, int] = {}

        for f in project_files:
            created = str(f.get("created", ""))[:10]
            updated = str(f.get("updated", ""))[:10]
            layer = f.get("layer", "cross")

            if created >= cutoff_str:
                files_added += 1
                layer_changes[layer] = layer_changes.get(layer, 0) + 1

            if updated >= cutoff_str:
                day = updated[:10]
                activity_by_day[day] = activity_by_day.get(day, 0) + 1

        # Get criteria (current only — we don't have historical)
        intent = self.intent_mgr.load_intent(project)
        criteria_total = len(intent.success_criteria) if intent else 0
        criteria_completed = sum(1 for c in intent.success_criteria if c.completed) if intent else 0

        return ProgressReport(
            project=project,
            period_start=cutoff_str,
            period_end=datetime.now().strftime("%Y-%m-%d"),
            criteria_at_start=max(0, criteria_completed - files_added),
            criteria_at_end=criteria_completed,
            criteria_added=0,  # Can't determine historical
            files_at_start=max(0, len(project_files) - files_added),
            files_at_end=len(project_files),
            files_added=files_added,
            layer_changes=layer_changes,
            activity_by_day=dict(sorted(activity_by_day.items())),
        )

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        alert_file = self.alerts_dir / f"{alert_id}.json"
        if not alert_file.exists():
            return False

        try:
            data = json.loads(alert_file.read_text(encoding="utf-8"))
            data["acknowledged"] = True
            alert_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def get_health_dashboard(self, project: str) -> Dict:
        """Get a quick health dashboard summary."""
        status = self.get_status(project)

        return {
            "project": project,
            "health": status.health,
            "health_score": f"{status.health_score:.0%}",
            "phase": status.phase,
            "criteria": f"{status.criteria_completed}/{status.criteria_total} ({status.criteria_completion:.0%})",
            "files": status.total_files,
            "recent_activity": status.recent_changes,
            "layers": {
                layer: f"{lp.file_count} files"
                for layer, lp in status.layer_progress.items()
            },
            "alerts": len([a for a in status.alerts if not a.acknowledged]),
            "needs_attention": status.needs_attention,
        }

    # ─── Internal ─────────────────────────────────────────────────

    def _analyze_layer(self, layer: str, files: List[Dict]) -> LayerProgress:
        """Analyze progress for a single layer."""
        if not files:
            return LayerProgress(
                layer=layer,
                file_count=0,
                last_updated=None,
                days_since_update=None,
                completeness=0.0,
                activity_score=0.0,
            )

        # Find most recent update
        last_updated = ""
        for f in files:
            u = f.get("updated", "")
            u_str = str(u) if u else ""
            if u_str > last_updated:
                last_updated = u_str

        days_since = None
        if last_updated:
            try:
                last_date = datetime.strptime(last_updated[:10], "%Y-%m-%d")
                days_since = (datetime.now() - last_date).days
            except (ValueError, TypeError):
                pass

        # Completeness: check if files have body content
        complete_count = 0
        for f in files:
            path = f.get("_path", "")
            if path and os.path.exists(path):
                try:
                    _, body = read_vault_file(path)
                    if len(body.strip()) > 50:  # Has meaningful content
                        complete_count += 1
                except Exception:
                    pass

        completeness = complete_count / len(files) if files else 0

        # Activity score: files updated in last 7 days
        cutoff_7d = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent = sum(1 for f in files if str(f.get("updated", ""))[:10] >= cutoff_7d)
        activity_score = min(1.0, recent / max(1, len(files)) * 3)

        return LayerProgress(
            layer=layer,
            file_count=len(files),
            last_updated=last_updated or None,
            days_since_update=days_since,
            completeness=completeness,
            activity_score=activity_score,
        )

    def _count_recent_changes(self, project: str, days: int = 7) -> int:
        """Count files updated in the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        files = find_by_project(project, self.vault_path)
        return sum(1 for f in files if str(f.get("updated", ""))[:10] >= cutoff)

    def _generate_alerts(
        self,
        project: str,
        intent,
        layer_progress: Dict[str, LayerProgress],
        project_files: List[Dict],
    ) -> List[Alert]:
        """Generate alerts based on status analysis."""
        alerts = []
        now = datetime.now().isoformat()

        # Staleness alert
        for layer, lp in layer_progress.items():
            if lp.days_since_update and lp.days_since_update > 14:
                alerts.append(Alert(
                    id=f"stale_{layer}_{datetime.now().strftime('%Y%m%d')}",
                    project=project,
                    level=AlertLevel.WARNING,
                    metric="staleness",
                    message=f"{layer} hasn't been updated in {lp.days_since_update} days",
                    timestamp=now,
                ))

        # Low completeness
        for layer, lp in layer_progress.items():
            if lp.file_count > 0 and lp.completeness < 0.5:
                alerts.append(Alert(
                    id=f"incomplete_{layer}_{datetime.now().strftime('%Y%m%d')}",
                    project=project,
                    level=AlertLevel.INFO,
                    metric="completeness",
                    message=f"{layer} has {lp.completeness:.0%} complete files",
                    timestamp=now,
                ))

        # No L4 research
        if layer_progress.get("L4", LayerProgress("L4", 0, None, None, 0, 0)).file_count == 0:
            alerts.append(Alert(
                id=f"no_research_{datetime.now().strftime('%Y%m%d')}",
                project=project,
                level=AlertLevel.WARNING,
                metric="research",
                message="No L4 research files — decisions may lack foundation",
                timestamp=now,
            ))

        # Stopped health
        if intent and intent.health == ProjectHealth.RED:
            alerts.append(Alert(
                id=f"health_red_{datetime.now().strftime('%Y%m%d')}",
                project=project,
                level=AlertLevel.CRITICAL,
                metric="health",
                message="Project health is RED — needs immediate attention",
                timestamp=now,
            ))

        return alerts

    def _calculate_health_score(
        self,
        intent,
        layer_progress: Dict[str, LayerProgress],
        recent_changes: int,
        criteria_completion: float,
    ) -> float:
        """Calculate composite health score (0.0 to 1.0)."""
        score = 0.5  # Base

        # Intent health bonus
        if intent:
            if intent.health == ProjectHealth.GREEN:
                score += 0.2
            elif intent.health == ProjectHealth.YELLOW:
                score += 0.1
            elif intent.health == ProjectHealth.RED:
                score -= 0.2

        # Criteria completion
        score += criteria_completion * 0.2

        # Layer completeness
        avg_completeness = sum(lp.completeness for lp in layer_progress.values()) / 4
        score += avg_completeness * 0.2

        # Recent activity bonus
        if recent_changes > 3:
            score += 0.1
        elif recent_changes == 0:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _write_alert(self, alert: Alert) -> None:
        """Persist an alert."""
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        alert_file = self.alerts_dir / f"{alert.id}.json"
        alert_file.write_text(json.dumps({
            "id": alert.id,
            "project": alert.project,
            "level": alert.level.value,
            "metric": alert.metric,
            "message": alert.message,
            "timestamp": alert.timestamp,
            "acknowledged": alert.acknowledged,
        }, indent=2), encoding="utf-8")


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    tracker = StatusTracker(vault)

    if cmd == "status":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: status.py status <project>")
            sys.exit(1)
        s = tracker.get_status(project)
        print(f"Project: {s.project}")
        print(f"Phase: {s.phase}, Health: {s.health} ({s.health_score:.0%})")
        print(f"Criteria: {s.criteria_completed}/{s.criteria_total} ({s.criteria_completion:.0%})")
        print(f"Files: {s.total_files} total, {s.recent_changes} recent")
        print(f"Layers:")
        for layer, lp in s.layer_progress.items():
            print(f"  {layer}: {lp.file_count} files, "
                  f"{lp.completeness:.0%} complete, "
                  f"updated {lp.days_since_update or '?'}d ago")
        if s.alerts:
            print(f"Alerts ({len(s.alerts)}):")
            for a in s.alerts:
                print(f"  [{a.level.value}] {a.message}")

    elif cmd == "dashboard":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: status.py dashboard <project>")
            sys.exit(1)
        dash = tracker.get_health_dashboard(project)
        for k, v in dash.items():
            if isinstance(v, dict):
                print(f"  {k}:")
                for k2, v2 in v.items():
                    print(f"    {k2}: {v2}")
            else:
                print(f"  {k}: {v}")

    elif cmd == "progress":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        if not project:
            print("Usage: status.py progress <project> [days]")
            sys.exit(1)
        p = tracker.get_progress(project, days=days)
        print(f"Progress: {p.project} ({p.period_start} to {p.period_end})")
        print(f"  Files: {p.files_at_start} -> {p.files_at_end} (+{p.files_added})")
        print(f"  Criteria: {p.criteria_at_end} completed")
        if p.layer_changes:
            print(f"  By layer:")
            for layer, count in p.layer_changes.items():
                print(f"    {layer}: +{count}")

    elif cmd == "alerts":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: status.py alerts <project>")
            sys.exit(1)
        alerts = tracker.check_alerts(project)
        print(f"Active alerts for {project}: {len(alerts)}")
        for a in alerts:
            print(f"  [{a.level.value:8}] {a.metric}: {a.message}")

    else:
        print("Commands: status <project>, dashboard <project>, progress <project> [days], alerts <project>")

#!/usr/bin/env python3
"""
Governance Engine for Mnemosyne Knowledge Vault.

Enforces autonomy rules and stop conditions:
  - Pre-action authorization checks
  - Stop rule monitoring
  - Autonomy level enforcement
  - Action logging
  - Escalation handling

Usage:
    from governance import GovernanceEngine

    gov = GovernanceEngine(vault_path="~/.hermes/memory")
    
    # Check if action is allowed
    decision = gov.authorize("eeg", "implement", "wire ADC circuit")
    if decision.allowed:
        # Proceed with action
        gov.log_action("eeg", "implement", "wire ADC circuit", "completed")
    else:
        print(decision.message)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from intent import IntentManager, AutonomyLevel, StopRule


# ─── Enums ────────────────────────────────────────────────────────

class ActionStatus(Enum):
    """Status of an attempted action."""
    ALLOWED = "allowed"           # Can proceed freely
    NOTIFY_REQUIRED = "notify"    # Can proceed, must report
    APPROVAL_REQUIRED = "approve" # Must get user approval first
    BLOCKED = "blocked"           # Not allowed
    STOPPED = "stopped"           # Blocked by stop rule


class EscalationLevel(Enum):
    """Escalation severity."""
    INFO = "info"           # Informational
    WARNING = "warning"     # Should be addressed
    CRITICAL = "critical"   # Requires immediate attention


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class AuthorizationDecision:
    """Result of an authorization check."""
    allowed: bool
    status: ActionStatus
    autonomy_level: AutonomyLevel
    message: str
    requires: str  # "nothing", "notification", "approval", "blocked"
    stop_rule: Optional[str] = None  # If blocked by stop rule
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ActionLog:
    """Log entry for an action taken."""
    id: str
    project: str
    area: str
    action: str
    status: ActionStatus
    timestamp: str
    autonomy_level: str
    outcome: Optional[str] = None
    notified: bool = False
    approved_by: Optional[str] = None


@dataclass
class Escalation:
    """An escalation requiring attention."""
    id: str
    project: str
    level: EscalationLevel
    message: str
    timestamp: str
    resolved: bool = False
    resolved_at: Optional[str] = None


@dataclass
class GovernanceReport:
    """Summary of governance activity."""
    project: str
    period_start: str
    period_end: str
    total_actions: int
    autonomous_actions: int
    notified_actions: int
    approved_actions: int
    blocked_actions: int
    escalations: int
    stop_triggers: int
    action_log: List[ActionLog]


# ─── Governance Engine ────────────────────────────────────────────

class GovernanceEngine:
    """
    Governance engine for enforcing autonomy rules and stop conditions.

    Wraps IntentManager to provide:
    - Pre-action authorization
    - Action logging
    - Stop rule monitoring
    - Escalation management
    - Governance reporting
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.intent_mgr = IntentManager(vault_path)
        self.log_dir = Path(vault_path) / "governance"
        self._action_counter = 0

    def authorize(
        self,
        project: str,
        area: str,
        action: str,
    ) -> AuthorizationDecision:
        """
        Check if an action is authorized under project governance.

        Args:
            project: Project name
            area: Action area (research, implementation, spending, etc.)
            action: Description of the action

        Returns:
            AuthorizationDecision with allowed status and requirements
        """
        # Load intent
        intent = self.intent_mgr.load_intent(project)
        if not intent:
            return AuthorizationDecision(
                allowed=False,
                status=ActionStatus.BLOCKED,
                autonomy_level=AutonomyLevel.FORBIDDEN,
                message=f"No intent schema found for project '{project}'",
                requires="intent_schema",
            )

        # Check stop rules first
        for rule in intent.stop_rules:
            if rule.triggered:
                return AuthorizationDecision(
                    allowed=False,
                    status=ActionStatus.STOPPED,
                    autonomy_level=AutonomyLevel.FORBIDDEN,
                    message=f"Stop rule active: {rule.condition}",
                    requires="stop_rule_resolved",
                    stop_rule=rule.condition,
                )

        # Check autonomy level
        level = intent.get_autonomy(area)

        if level == AutonomyLevel.AUTONOMOUS:
            decision = AuthorizationDecision(
                allowed=True,
                status=ActionStatus.ALLOWED,
                autonomy_level=level,
                message=f"Autonomous: '{action}' allowed in {area}",
                requires="nothing",
            )
        elif level == AutonomyLevel.NOTIFY:
            decision = AuthorizationDecision(
                allowed=True,
                status=ActionStatus.NOTIFY_REQUIRED,
                autonomy_level=level,
                message=f"Notify: '{action}' allowed, will report after",
                requires="notification",
            )
        elif level == AutonomyLevel.APPROVE:
            decision = AuthorizationDecision(
                allowed=False,
                status=ActionStatus.APPROVAL_REQUIRED,
                autonomy_level=level,
                message=f"Approve: '{action}' requires user approval",
                requires="approval",
            )
        else:  # FORBIDDEN
            decision = AuthorizationDecision(
                allowed=False,
                status=ActionStatus.BLOCKED,
                autonomy_level=level,
                message=f"Forbidden: '{action}' not allowed in {area}",
                requires="blocked",
            )

        # Log the authorization check
        self._log_authorization(project, area, action, decision)

        return decision

    def log_action(
        self,
        project: str,
        area: str,
        action: str,
        outcome: str,
        status: ActionStatus = ActionStatus.ALLOWED,
    ) -> ActionLog:
        """
        Log an action that was taken.

        Args:
            project: Project name
            area: Action area
            action: Description of the action
            outcome: What happened
            status: Authorization status at time of action

        Returns:
            ActionLog entry
        """
        self._action_counter += 1
        intent = self.intent_mgr.load_intent(project)
        autonomy = intent.get_autonomy(area) if intent else AutonomyLevel.APPROVE

        log = ActionLog(
            id=f"action_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._action_counter}",
            project=project,
            area=area,
            action=action,
            status=status,
            timestamp=datetime.now().isoformat(),
            autonomy_level=autonomy.value,
            outcome=outcome,
        )

        self._write_action_log(log)
        return log

    def check_stop_rules(self, project: str) -> List[Dict]:
        """
        Check all stop rules for a project.

        Returns list of triggered rules with their actions.
        """
        intent = self.intent_mgr.load_intent(project)
        if not intent:
            return []

        triggered = []
        for rule in intent.stop_rules:
            if rule.triggered:
                triggered.append({
                    "condition": rule.condition,
                    "action": rule.action,
                    "trigger_count": rule.trigger_count,
                })

        return triggered

    def trigger_stop(
        self,
        project: str,
        condition: str,
        context: str = "",
    ) -> Dict:
        """
        Trigger a stop rule.

        Returns escalation info.
        """
        result = self.intent_mgr.trigger_stop_rule(project, condition)

        # Create escalation
        escalation = Escalation(
            id=f"esc_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            project=project,
            level=EscalationLevel.CRITICAL,
            message=f"Stop rule triggered: {condition}. Context: {context}",
            timestamp=datetime.now().isoformat(),
        )

        self._write_escalation(escalation)

        return {
            "action": result.get("action", "stop"),
            "condition": condition,
            "escalation_id": escalation.id,
            "message": result.get("message", ""),
        }

    def escalate(
        self,
        project: str,
        level: EscalationLevel,
        message: str,
    ) -> Escalation:
        """Create an escalation for user attention."""
        escalation = Escalation(
            id=f"esc_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            project=project,
            level=level,
            message=message,
            timestamp=datetime.now().isoformat(),
        )
        self._write_escalation(escalation)
        return escalation

    def get_action_log(
        self,
        project: Optional[str] = None,
        area: Optional[str] = None,
        limit: int = 50,
    ) -> List[ActionLog]:
        """Get recent action logs."""
        logs = []

        if not self.log_dir.exists():
            return logs

        log_file = self.log_dir / "actions.jsonl"
        if not log_file.exists():
            return logs

        try:
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            for line in reversed(lines):
                if len(logs) >= limit:
                    break
                if not line.strip():
                    continue

                data = json.loads(line)

                # Apply filters
                if project and data.get("project") != project:
                    continue
                if area and data.get("area") != area:
                    continue

                logs.append(ActionLog(
                    id=data.get("id", ""),
                    project=data.get("project", ""),
                    area=data.get("area", ""),
                    action=data.get("action", ""),
                    status=ActionStatus(data.get("status", "allowed")),
                    timestamp=data.get("timestamp", ""),
                    autonomy_level=data.get("autonomy_level", ""),
                    outcome=data.get("outcome"),
                    notified=data.get("notified", False),
                ))
        except Exception:
            pass

        return logs

    def get_escalations(
        self,
        project: Optional[str] = None,
        unresolved_only: bool = True,
    ) -> List[Escalation]:
        """Get escalations."""
        escalations = []

        esc_file = self.log_dir / "escalations.jsonl"
        if not esc_file.exists():
            return escalations

        try:
            lines = esc_file.read_text(encoding="utf-8").strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue

                data = json.loads(line)

                if project and data.get("project") != project:
                    continue
                if unresolved_only and data.get("resolved", False):
                    continue

                escalations.append(Escalation(
                    id=data.get("id", ""),
                    project=data.get("project", ""),
                    level=EscalationLevel(data.get("level", "info")),
                    message=data.get("message", ""),
                    timestamp=data.get("timestamp", ""),
                    resolved=data.get("resolved", False),
                ))
        except Exception:
            pass

        return escalations

    def get_report(
        self,
        project: str,
        days: int = 7,
    ) -> GovernanceReport:
        """Generate a governance report for a project."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        logs = self.get_action_log(project=project, limit=1000)

        # Filter by date
        recent_logs = []
        for log in logs:
            try:
                log_time = datetime.fromisoformat(log.timestamp)
                if log_time >= cutoff:
                    recent_logs.append(log)
            except Exception:
                continue

        # Count by status
        autonomous = sum(1 for l in recent_logs if l.autonomy_level == "autonomous")
        notified = sum(1 for l in recent_logs if l.autonomy_level == "notify")
        approved = sum(1 for l in recent_logs if l.autonomy_level == "approve")
        blocked = sum(1 for l in recent_logs if l.status == ActionStatus.BLOCKED)

        escalations = self.get_escalations(project=project, unresolved_only=False)
        recent_esc = [e for e in escalations if e.timestamp >= cutoff.isoformat()]

        return GovernanceReport(
            project=project,
            period_start=cutoff.strftime("%Y-%m-%d"),
            period_end=datetime.now().strftime("%Y-%m-%d"),
            total_actions=len(recent_logs),
            autonomous_actions=autonomous,
            notified_actions=notified,
            approved_actions=approved,
            blocked_actions=blocked,
            escalations=len(recent_esc),
            stop_triggers=sum(1 for e in recent_esc if "stop rule" in e.message.lower()),
            action_log=recent_logs[:20],
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _log_authorization(
        self,
        project: str,
        area: str,
        action: str,
        decision: AuthorizationDecision,
    ) -> None:
        """Log an authorization check."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        log_file = self.log_dir / "auth_checks.jsonl"
        entry = {
            "project": project,
            "area": area,
            "action": action,
            "allowed": decision.allowed,
            "status": decision.status.value,
            "autonomy_level": decision.autonomy_level.value,
            "timestamp": decision.timestamp,
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_action_log(self, log: ActionLog) -> None:
        """Write action log entry."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        log_file = self.log_dir / "actions.jsonl"
        entry = {
            "id": log.id,
            "project": log.project,
            "area": log.area,
            "action": log.action,
            "status": log.status.value,
            "timestamp": log.timestamp,
            "autonomy_level": log.autonomy_level,
            "outcome": log.outcome,
            "notified": log.notified,
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_escalation(self, escalation: Escalation) -> None:
        """Write escalation entry."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        esc_file = self.log_dir / "escalations.jsonl"
        entry = {
            "id": escalation.id,
            "project": escalation.project,
            "level": escalation.level.value,
            "message": escalation.message,
            "timestamp": escalation.timestamp,
            "resolved": escalation.resolved,
        }

        with open(esc_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    gov = GovernanceEngine(vault)

    if cmd == "authorize":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        area = sys.argv[3] if len(sys.argv) > 3 else "research"
        action = sys.argv[4] if len(sys.argv) > 4 else "explore"
        if not project:
            print("Usage: governance.py authorize <project> <area> <action>")
            sys.exit(1)
        decision = gov.authorize(project, area, action)
        print(f"Allowed: {decision.allowed}")
        print(f"Status: {decision.status.value}")
        print(f"Level: {decision.autonomy_level.value}")
        print(f"Requires: {decision.requires}")
        print(f"Message: {decision.message}")

    elif cmd == "log":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: governance.py log [project]")
            sys.exit(1)
        logs = gov.get_action_log(project=project)
        print(f"Recent actions{f' for {project}' if project else ''}: {len(logs)}")
        for log in logs[:10]:
            print(f"  [{log.status.value:10}] [{log.autonomy_level:12}] {log.action[:50]}")

    elif cmd == "escalations":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        escs = gov.get_escalations(project=project)
        print(f"Unresolved escalations: {len(escs)}")
        for e in escs[:10]:
            print(f"  [{e.level.value:8}] {e.message[:60]}")

    elif cmd == "report":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        if not project:
            print("Usage: governance.py report <project> [days]")
            sys.exit(1)
        report = gov.get_report(project, days=days)
        print(f"Governance Report: {report.project}")
        print(f"Period: {report.period_start} to {report.period_end}")
        print(f"Total actions: {report.total_actions}")
        print(f"  Autonomous: {report.autonomous_actions}")
        print(f"  Notified: {report.notified_actions}")
        print(f"  Approved: {report.approved_actions}")
        print(f"  Blocked: {report.blocked_actions}")
        print(f"Escalations: {report.escalations}")
        print(f"Stop triggers: {report.stop_triggers}")

    else:
        print("Commands: authorize <project> <area> <action>, log [project],")
        print("          escalations [project], report <project> [days]")

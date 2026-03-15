#!/usr/bin/env python3
"""
Intent Schema Manager for Mnemosyne Knowledge Vault.

Manages project intent schemas defined in L1 _overview.md files:
  - Objective: What are we trying to achieve?
  - Success criteria: Measurable checkboxes
  - Health metrics: KPIs with alert thresholds
  - Constraints: Budget, safety, scope
  - Decision autonomy: What's autonomous/notify/approve/forbidden
  - Stop rules: Kill switches

Usage:
    from intent import IntentManager

    mgr = IntentManager(vault_path="~/.hermes/memory")
    
    # Load project intent
    intent = mgr.load_intent("eeg")
    
    # Check if an action is allowed
    decision = mgr.check_autonomy("eeg", "research", "explore new ADC chips")
    
    # Update success criteria
    mgr.update_criteria("eeg", "impedance_check", completed=True)
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from vault_utils import read_vault_file, write_frontmatter, parse_frontmatter


# ─── Enums ────────────────────────────────────────────────────────

class AutonomyLevel(Enum):
    """Decision autonomy levels."""
    AUTONOMOUS = "autonomous"   # Agent decides freely
    NOTIFY = "notify"           # Agent decides, reports after
    APPROVE = "approve"         # Agent proposes, user must approve
    FORBIDDEN = "forbidden"     # Not allowed without explicit instruction


class ProjectHealth(Enum):
    """Project health status."""
    GREEN = "green"     # On track
    YELLOW = "yellow"   # Some concerns
    RED = "red"         # Needs attention


class ProjectPhase(Enum):
    """Project lifecycle phase."""
    PLANNING = "planning"
    RESEARCH = "research"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    MAINTENANCE = "maintenance"
    ARCHIVED = "archived"


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class SuccessCriterion:
    """A single success criterion."""
    id: str
    description: str
    completed: bool
    completed_date: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class HealthMetric:
    """A KPI with alert threshold."""
    name: str
    current_value: Optional[str] = None
    target_value: Optional[str] = None
    threshold: Optional[str] = None  # Alert if exceeded
    status: str = "unknown"  # ok, warning, critical


@dataclass
class AutonomyRule:
    """Autonomy rule for a specific area."""
    area: str  # e.g., "research", "implementation", "spending"
    level: AutonomyLevel
    notes: str = ""


@dataclass
class StopRule:
    """A kill switch condition."""
    condition: str
    action: str  # "stop", "ask", "report"
    triggered: bool = False
    trigger_count: int = 0


@dataclass
class IntentSchema:
    """Complete intent schema for a project."""
    project: str
    objective: str
    success_criteria: List[SuccessCriterion]
    health_metrics: List[HealthMetric]
    constraints: Dict[str, str]  # area -> constraint text
    autonomy_rules: List[AutonomyRule]
    stop_rules: List[StopRule]
    phase: ProjectPhase
    health: ProjectHealth
    last_updated: str

    @property
    def criteria_completion(self) -> float:
        """Percentage of success criteria completed."""
        if not self.success_criteria:
            return 0.0
        completed = sum(1 for c in self.success_criteria if c.completed)
        return completed / len(self.success_criteria)

    @property
    def is_healthy(self) -> bool:
        """Check if project is healthy."""
        return self.health in (ProjectHealth.GREEN, ProjectHealth.YELLOW)

    def get_autonomy(self, area: str) -> AutonomyLevel:
        """Get autonomy level for an area."""
        for rule in self.autonomy_rules:
            if rule.area.lower() == area.lower():
                return rule.level
        return AutonomyLevel.APPROVE  # Default: require approval

    def has_triggered_stops(self) -> bool:
        """Check if any stop rules are triggered."""
        return any(r.triggered for r in self.stop_rules)


# ─── Intent Manager ───────────────────────────────────────────────

class IntentManager:
    """
    Manages project intent schemas.

    Reads intent from L1 _overview.md files and provides
    structured access to objectives, autonomy rules, and stop conditions.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)

    def load_intent(self, project: str) -> Optional[IntentSchema]:
        """
        Load intent schema from project's _overview.md.

        Parses the Intent section and extracts structured data.
        """
        overview_path = (
            Path(self.vault_path) / "projects" / project / "_overview.md"
        )

        if not overview_path.exists():
            return None

        try:
            meta, body = read_vault_file(str(overview_path))
        except Exception:
            return None

        # Parse intent sections
        objective = self._extract_section(body, "Objective")
        criteria = self._parse_success_criteria(body)
        metrics = self._parse_health_metrics(body)
        constraints = self._parse_constraints(body)
        autonomy = self._parse_autonomy(body)
        stop_rules = self._parse_stop_rules(body)

        # Determine phase and health
        phase = self._parse_phase(meta.get("phase", ""), body)
        health = self._parse_health(meta.get("health", ""), body)

        return IntentSchema(
            project=project,
            objective=objective,
            success_criteria=criteria,
            health_metrics=metrics,
            constraints=constraints,
            autonomy_rules=autonomy,
            stop_rules=stop_rules,
            phase=phase,
            health=health,
            last_updated=meta.get("updated", datetime.now().strftime("%Y-%m-%d")),
        )

    def check_autonomy(
        self,
        project: str,
        area: str,
        action: str,
    ) -> Dict:
        """
        Check if an action is allowed under the project's autonomy rules.

        Returns dict with:
          - allowed: bool
          - level: AutonomyLevel
          - requires: str (what's needed: nothing, notification, approval)
          - message: str
        """
        intent = self.load_intent(project)
        if not intent:
            return {
                "allowed": False,
                "level": AutonomyLevel.APPROVE,
                "requires": "approval",
                "message": f"No intent schema found for project '{project}'",
            }

        # Check stop rules first
        if intent.has_triggered_stops():
            return {
                "allowed": False,
                "level": AutonomyLevel.FORBIDDEN,
                "requires": "stop_rule_resolved",
                "message": "Stop rule triggered — resolve before proceeding",
            }

        level = intent.get_autonomy(area)

        if level == AutonomyLevel.AUTONOMOUS:
            return {
                "allowed": True,
                "level": level,
                "requires": "nothing",
                "message": f"Autonomous: '{action}' allowed in {area}",
            }
        elif level == AutonomyLevel.NOTIFY:
            return {
                "allowed": True,
                "level": level,
                "requires": "notification",
                "message": f"Notify: '{action}' allowed in {area}, will report after",
            }
        elif level == AutonomyLevel.APPROVE:
            return {
                "allowed": False,
                "level": level,
                "requires": "approval",
                "message": f"Approve: '{action}' in {area} requires user approval",
            }
        else:  # FORBIDDEN
            return {
                "allowed": False,
                "level": level,
                "requires": "explicit_instruction",
                "message": f"Forbidden: '{action}' not allowed in {area}",
            }

    def update_criterion(
        self,
        project: str,
        criterion_id: str,
        completed: bool = True,
        evidence: Optional[str] = None,
    ) -> bool:
        """
        Mark a success criterion as completed/incomplete.

        Note: This updates the _overview.md file.
        """
        overview_path = (
            Path(self.vault_path) / "projects" / project / "_overview.md"
        )

        if not overview_path.exists():
            return False

        try:
            meta, body = read_vault_file(str(overview_path))
        except Exception:
            return False

        # Find and update the criterion in the body
        # Look for pattern: - [ ] description or - [x] description
        pattern = rf'- \[([ x])\]\s*(.*{re.escape(criterion_id)}.*|.*\b\w+\b.*)'

        if completed:
            # Mark as complete
            body = re.sub(
                r'- \[ \]\s*(.+)',
                lambda m: f'- [x] {m.group(1)}' if criterion_id.lower() in m.group(1).lower() else m.group(0),
                body,
                count=1,
            )
        else:
            # Mark as incomplete
            body = re.sub(
                r'- \[x\]\s*(.+)',
                lambda m: f'- [ ] {m.group(1)}' if criterion_id.lower() in m.group(1).lower() else m.group(0),
                body,
                count=1,
            )

        # Update timestamp
        meta["updated"] = datetime.now().strftime("%Y-%m-%d")

        # Write back
        content = write_frontmatter(meta, body)
        overview_path.write_text(content, encoding="utf-8")

        return True

    def trigger_stop_rule(
        self,
        project: str,
        condition: str,
    ) -> Dict:
        """
        Trigger a stop rule.

        Returns the stop rule action to take.
        """
        intent = self.load_intent(project)
        if not intent:
            return {"action": "ask", "message": "No intent schema found"}

        for rule in intent.stop_rules:
            if condition.lower() in rule.condition.lower():
                rule.triggered = True
                rule.trigger_count += 1
                return {
                    "action": rule.action,
                    "condition": rule.condition,
                    "trigger_count": rule.trigger_count,
                    "message": f"Stop rule triggered: {rule.condition}",
                }

        return {"action": "report", "message": f"No stop rule matched '{condition}'"}

    def get_project_status(self, project: str) -> Dict:
        """Get a quick status summary for a project."""
        intent = self.load_intent(project)
        if not intent:
            return {"error": f"Project '{project}' not found"}

        return {
            "project": project,
            "objective": intent.objective[:100],
            "phase": intent.phase.value,
            "health": intent.health.value,
            "criteria_completion": f"{intent.criteria_completion:.0%}",
            "criteria_total": len(intent.success_criteria),
            "criteria_completed": sum(1 for c in intent.success_criteria if c.completed),
            "stop_rules_triggered": sum(1 for r in intent.stop_rules if r.triggered),
            "last_updated": intent.last_updated,
        }

    # ─── Parsing ──────────────────────────────────────────────────

    def _extract_section(self, body: str, section_name: str) -> str:
        """Extract content of a ## section."""
        pattern = rf'## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)'
        match = re.search(pattern, body, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _parse_success_criteria(self, body: str) -> List[SuccessCriterion]:
        """Parse success criteria from checkbox list."""
        criteria = []
        # Find Success Criteria section
        section = self._extract_section(body, "Success Criteria")
        if not section:
            return criteria

        # Parse checkboxes
        items = re.findall(r'- \[([ x])\]\s*(.+)', section)
        for i, (checked, desc) in enumerate(items):
            criteria.append(SuccessCriterion(
                id=f"criterion_{i+1}",
                description=desc.strip(),
                completed=(checked == "x"),
            ))

        return criteria

    def _parse_health_metrics(self, body: str) -> List[HealthMetric]:
        """Parse health metrics (currently minimal)."""
        # Look for KPI-style patterns in the body
        metrics = []
        kpi_patterns = re.findall(
            r'(\w[\w\s]+):\s*([<>]?\d+[\w%]*)\s*(?:target|threshold)?',
            body, re.IGNORECASE
        )
        for name, value in kpi_patterns[:5]:
            metrics.append(HealthMetric(
                name=name.strip(),
                target_value=value,
            ))
        return metrics

    def _parse_constraints(self, body: str) -> Dict[str, str]:
        """Parse constraints section."""
        constraints = {}
        section = self._extract_section(body, "Constraints")
        if not section:
            return constraints

        # Parse key: value lines
        items = re.findall(r'-?\s*(\w+):\s*(.+)', section)
        for key, value in items:
            constraints[key.lower()] = value.strip()

        return constraints

    def _parse_autonomy(self, body: str) -> List[AutonomyRule]:
        """Parse decision autonomy table."""
        rules = []
        section = self._extract_section(body, "Decision Autonomy")
        if not section:
            # Default autonomy
            return [
                AutonomyRule("research", AutonomyLevel.AUTONOMOUS, "Agent explores freely"),
                AutonomyRule("implementation", AutonomyLevel.NOTIFY, "Agent reports before executing"),
                AutonomyRule("spending", AutonomyLevel.APPROVE, "User must approve costs"),
            ]

        # Parse table rows
        rows = re.findall(
            r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|',
            section
        )
        for area, level_str, notes in rows:
            area = area.strip()
            level_str = level_str.strip().lower()
            notes = notes.strip()

            if area in ("Area", "------"):
                continue

            # Map level string to enum
            level = AutonomyLevel.APPROVE  # default
            for lv in AutonomyLevel:
                if lv.value in level_str:
                    level = lv
                    break

            rules.append(AutonomyRule(area=area, level=level, notes=notes))

        return rules

    def _parse_stop_rules(self, body: str) -> List[StopRule]:
        """Parse stop rules section."""
        rules = []
        section = self._extract_section(body, "Stop Rules")
        if not section:
            return []

        # Parse bullet points
        items = re.findall(r'- (?:If\s+)?(.+?)(?:\s*→|->)\s*(\w+)', section, re.IGNORECASE)
        for condition, action in items:
            action = action.strip().lower()
            if action not in ("stop", "ask", "report"):
                action = "ask"
            rules.append(StopRule(condition=condition.strip(), action=action))

        return rules

    def _parse_phase(self, phase_str: str, body: str) -> ProjectPhase:
        """Parse project phase."""
        phase_str = phase_str.lower()
        for phase in ProjectPhase:
            if phase.value in phase_str:
                return phase

        # Try to detect from body
        body_lower = body.lower()
        if "planning" in body_lower:
            return ProjectPhase.PLANNING
        elif "research" in body_lower:
            return ProjectPhase.RESEARCH
        elif "implement" in body_lower:
            return ProjectPhase.IMPLEMENTATION
        elif "review" in body_lower:
            return ProjectPhase.REVIEW

        return ProjectPhase.PLANNING

    def _parse_health(self, health_str: str, body: str) -> ProjectHealth:
        """Parse project health."""
        health_str = health_str.lower()
        if "green" in health_str:
            return ProjectHealth.GREEN
        elif "yellow" in health_str:
            return ProjectHealth.YELLOW
        elif "red" in health_str:
            return ProjectHealth.RED
        return ProjectHealth.GREEN  # Default optimistic


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    mgr = IntentManager(vault)

    if cmd == "intent":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: intent.py intent <project>")
            sys.exit(1)
        intent = mgr.load_intent(project)
        if intent:
            print(f"Project: {intent.project}")
            print(f"Objective: {intent.objective[:100]}")
            print(f"Phase: {intent.phase.value}, Health: {intent.health.value}")
            print(f"Criteria: {intent.criteria_completion:.0%} complete")
            print(f"Autonomy rules: {len(intent.autonomy_rules)}")
            print(f"Stop rules: {len(intent.stop_rules)}")
        else:
            print(f"Project '{project}' not found")

    elif cmd == "check":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        area = sys.argv[3] if len(sys.argv) > 3 else "research"
        action = sys.argv[4] if len(sys.argv) > 4 else "explore"
        if not project:
            print("Usage: intent.py check <project> <area> <action>")
            sys.exit(1)
        result = mgr.check_autonomy(project, area, action)
        print(f"Allowed: {result['allowed']}")
        print(f"Level: {result['level'].value}")
        print(f"Requires: {result['requires']}")
        print(f"Message: {result['message']}")

    elif cmd == "status":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: intent.py status <project>")
            sys.exit(1)
        status = mgr.get_project_status(project)
        for k, v in status.items():
            print(f"  {k}: {v}")

    else:
        print("Commands: intent <project>, check <project> <area> <action>, status <project>")
